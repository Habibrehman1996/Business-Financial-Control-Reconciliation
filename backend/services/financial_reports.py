
from datetime import date
from decimal import Decimal, ROUND_HALF_UP

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.models import Account, JournalEntry, JournalLine


ZERO = Decimal("0.00")
CENT = Decimal("0.01")


def _decimal(value) -> Decimal:
    if value is None:
        return ZERO
    return Decimal(str(value))


def _money(value) -> Decimal:
    return _decimal(value).quantize(
        CENT,
        rounding=ROUND_HALF_UP,
    )


def _get_posted_lines(
    db: Session,
    start_date: date | None = None,
    end_date: date | None = None,
):
    query = (
        select(JournalLine, Account, JournalEntry)
        .join(Account, Account.id == JournalLine.account_id)
        .join(
            JournalEntry,
            JournalEntry.id == JournalLine.journal_entry_id,
        )
        .where(JournalEntry.status == "posted")
    )

    if start_date is not None:
        query = query.where(JournalEntry.entry_date >= start_date)

    if end_date is not None:
        query = query.where(JournalEntry.entry_date <= end_date)

    return db.execute(query).all()


def _account_totals(rows):
    totals = {}

    for line, account, entry in rows:
        if account.id not in totals:
            totals[account.id] = {
                "account": account,
                "debit": ZERO,
                "credit": ZERO,
            }

        totals[account.id]["debit"] += _money(line.debit)
        totals[account.id]["credit"] += _money(line.credit)

    return totals


def _normal_balance(account_type: str) -> str:
    return (
        "debit"
        if account_type in {"asset", "expense"}
        else "credit"
    )


def _closing_balance(account_type: str, debit, credit) -> Decimal:
    debit = _money(debit)
    credit = _money(credit)

    if _normal_balance(account_type) == "debit":
        return _money(debit - credit)

    return _money(credit - debit)


def _actual_balance_sides(debit, credit):
    """
    Return the actual closing debit and credit balances.

    Abnormal balances are moved to the opposite side.
    """
    net_balance = _money(_money(debit) - _money(credit))

    if net_balance > ZERO:
        return net_balance, ZERO

    if net_balance < ZERO:
        return ZERO, _money(abs(net_balance))

    return ZERO, ZERO


def _balance_totals(
    db: Session,
    end_date: date | None = None,
):
    rows = _get_posted_lines(db, end_date=end_date)
    return _account_totals(rows)


def get_trial_balance(
    db: Session,
    start_date: date | None = None,
    end_date: date | None = None,
):
    if start_date and end_date and start_date > end_date:
        raise ValueError("Start date cannot be after end date.")

    accounts = db.scalars(
        select(Account).order_by(Account.code)
    ).all()

    # Closing balances include all posted entries through end_date.
    closing_totals = _balance_totals(db, end_date)

    rows = []
    total_debit = ZERO
    total_credit = ZERO

    for account in accounts:
        totals = closing_totals.get(account.id)

        debit = totals["debit"] if totals else ZERO
        credit = totals["credit"] if totals else ZERO

        balance = _closing_balance(
            account.account_type,
            debit,
            credit,
        )

        if balance == ZERO and not account.is_active:
            continue

        # Actual debit/credit sides, independent of account type.
        debit_balance, credit_balance = _actual_balance_sides(
            debit,
            credit,
        )

        total_debit += debit_balance
        total_credit += credit_balance

        rows.append(
            {
                "account_id": account.id,
                "code": account.code,
                "name": account.name,
                "account_type": account.account_type,
                "debit": _money(debit),
                "credit": _money(credit),
                "balance": _money(balance),
                "debit_balance": _money(debit_balance),
                "credit_balance": _money(credit_balance),
            }
        )

    return {
        "start_date": start_date,
        "end_date": end_date,
        "accounts": rows,
        "total_debit_balance": _money(total_debit),
        "total_credit_balance": _money(total_credit),
        "is_balanced": _money(total_debit) == _money(total_credit),
    }


def get_profit_loss(
    db: Session,
    start_date: date | None = None,
    end_date: date | None = None,
):
    if start_date and end_date and start_date > end_date:
        raise ValueError("Start date cannot be after end date.")

    rows = _get_posted_lines(db, start_date, end_date)
    totals = _account_totals(rows)

    revenue_rows = []
    expense_rows = []

    total_revenue = ZERO
    total_expenses = ZERO

    for account_id, item in totals.items():
        account = item["account"]

        balance = _closing_balance(
            account.account_type,
            item["debit"],
            item["credit"],
        )

        if account.account_type == "revenue":
            total_revenue += balance

            revenue_rows.append(
                {
                    "account_id": account.id,
                    "code": account.code,
                    "name": account.name,
                    "amount": _money(balance),
                }
            )

        elif account.account_type == "expense":
            total_expenses += balance

            expense_rows.append(
                {
                    "account_id": account.id,
                    "code": account.code,
                    "name": account.name,
                    "amount": _money(balance),
                }
            )

    net_profit = _money(total_revenue - total_expenses)

    return {
        "start_date": start_date,
        "end_date": end_date,
        "revenue": revenue_rows,
        "expenses": expense_rows,
        "total_revenue": _money(total_revenue),
        "total_expenses": _money(total_expenses),
        "net_profit": net_profit,
    }


def get_dashboard_summary(
    db: Session,
    start_date: date | None = None,
    end_date: date | None = None,
):
    if start_date and end_date and start_date > end_date:
        raise ValueError("Start date cannot be after end date.")

    profit_loss = get_profit_loss(
        db,
        start_date,
        end_date,
    )

    # Balance sheet values are cumulative through end_date.
    balance_totals = _balance_totals(db, end_date)

    accounts = db.scalars(
        select(Account)
        .where(Account.is_active.is_(True))
        .order_by(Account.code)
    ).all()

    total_assets = ZERO
    total_liabilities = ZERO
    total_equity = ZERO
    account_balances = []

    for account in accounts:
        item = balance_totals.get(account.id)

        debit = item["debit"] if item else ZERO
        credit = item["credit"] if item else ZERO

        balance = _closing_balance(
            account.account_type,
            debit,
            credit,
        )

        debit_balance, credit_balance = _actual_balance_sides(
            debit,
            credit,
        )

        account_balances.append(
            {
                "account_id": account.id,
                "code": account.code,
                "name": account.name,
                "account_type": account.account_type,
                "balance": _money(balance),
                "debit_balance": _money(debit_balance),
                "credit_balance": _money(credit_balance),
            }
        )

        # Abnormal asset credit balances are classified as liabilities.
        if account.account_type == "asset":
            total_assets += debit_balance
            total_liabilities += credit_balance

        # Abnormal liability debit balances are classified as assets.
        elif account.account_type == "liability":
            total_liabilities += credit_balance
            total_assets += debit_balance

        elif account.account_type == "equity":
            total_equity += balance

    # Include current-period profit in equity for dashboard purposes.
    total_equity += profit_loss["net_profit"]

    return {
        "start_date": start_date,
        "end_date": end_date,
        "total_assets": _money(total_assets),
        "total_liabilities": _money(total_liabilities),
        "total_equity": _money(total_equity),
        "total_revenue": profit_loss["total_revenue"],
        "total_expenses": profit_loss["total_expenses"],
        "net_profit": profit_loss["net_profit"],
        "account_balances": account_balances,
    }

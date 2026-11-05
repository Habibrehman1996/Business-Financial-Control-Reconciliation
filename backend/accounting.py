from datetime import date
from decimal import Decimal, ROUND_HALF_UP

from sqlalchemy.orm import Session

from backend.models import Account, JournalEntry, JournalLine


ZERO = Decimal("0.00")
CENT = Decimal("0.01")
THREE_PLACES = Decimal("0.001")

ACCOUNT_TYPES = {
    "asset",
    "liability",
    "equity",
    "revenue",
    "expense",
}

STANDARD_ACCOUNTS = [
    ("1000", "Assets", "asset"),
    ("1010", "Cash", "asset"),
    ("1020", "Bank", "asset"),
    ("1100", "Accounts Receivable", "asset"),
    ("1200", "Inventory", "asset"),
    ("1300", "Input Tax", "asset"),
    ("2000", "Liabilities", "liability"),
    ("2010", "Accounts Payable", "liability"),
    ("2020", "Output Tax Payable", "liability"),
    ("3000", "Owner's Equity", "equity"),
    ("3010", "Opening Balance Equity", "equity"),
    ("4000", "Sales Revenue", "revenue"),
    ("5000", "Cost of Goods Sold", "expense"),
    ("6000", "Operating Expenses", "expense"),
    ("6010", "Inventory Adjustment Expense", "expense"),
    ("7000", "Other Income", "revenue"),
]


def to_decimal(value) -> Decimal:
    try:
        if value is None:
            return ZERO
        return Decimal(str(value))
    except Exception as exc:
        raise ValueError("Invalid decimal value.") from exc


def money(value) -> Decimal:
    return to_decimal(value).quantize(
        CENT,
        rounding=ROUND_HALF_UP,
    )


def quantity(value) -> Decimal:
    return to_decimal(value).quantize(
        THREE_PLACES,
        rounding=ROUND_HALF_UP,
    )


def validate_account_type(account_type: str) -> str:
    normalized = account_type.strip().lower()

    if normalized not in ACCOUNT_TYPES:
        raise ValueError("Invalid account type.")

    return normalized


def validate_journal_totals(lines: list[dict]):
    total_debit = ZERO
    total_credit = ZERO

    for line in lines:
        debit = money(line.get("debit", ZERO))
        credit = money(line.get("credit", ZERO))

        if debit < ZERO or credit < ZERO:
            raise ValueError("Debit and credit cannot be negative.")

        if (debit > ZERO) == (credit > ZERO):
            raise ValueError(
                "Every journal line must contain either debit or credit."
            )

        total_debit += debit
        total_credit += credit

    return money(total_debit), money(total_credit)


def normal_balance(account_type: str) -> str:
    if account_type in {"asset", "expense"}:
        return "debit"

    return "credit"


def calculate_account_balance(
    account_type: str,
    debit_total,
    credit_total,
) -> Decimal:
    debit = money(debit_total)
    credit = money(credit_total)

    if normal_balance(account_type) == "debit":
        return money(debit - credit)

    return money(credit - debit)


def initialize_standard_accounts(db: Session):
    created = []

    for code, name, account_type in STANDARD_ACCOUNTS:
        account = (
            db.query(Account)
            .filter(Account.code == code)
            .first()
        )

        if account is None:
            account = Account(
                code=code,
                name=name,
                account_type=account_type,
                is_active=True,
            )
            db.add(account)
            created.append(account)

    db.flush()
    return created


def get_account_by_code(
    db: Session,
    code: str,
) -> Account | None:
    return (
        db.query(Account)
        .filter(Account.code == code)
        .first()
    )


def get_account_balance(
    db: Session,
    account_id: int,
    as_of_date: date | None = None,
    start_date: date | None = None,
) -> Decimal:
    """
    Calculate an account's ledger balance.

    as_of_date:
        Include posted journal entries up to this date.

    start_date:
        Optional beginning date. When supplied, this function
        returns movement during the selected period rather than
        the opening balance.

    Without start_date, the result is the cumulative balance
    from the beginning of the ledger through as_of_date.
    """

    query = (
        db.query(
            JournalLine.debit,
            JournalLine.credit,
        )
        .join(
            JournalEntry,
            JournalEntry.id == JournalLine.journal_entry_id,
        )
        .filter(
            JournalLine.account_id == account_id,
            JournalEntry.status == "posted",
        )
    )

    if start_date is not None:
        query = query.filter(
            JournalEntry.entry_date >= start_date
        )

    if as_of_date is not None:
        query = query.filter(
            JournalEntry.entry_date <= as_of_date
        )

    rows = query.all()

    total_debit = sum(
        (money(row.debit) for row in rows),
        ZERO,
    )

    total_credit = sum(
        (money(row.credit) for row in rows),
        ZERO,
    )

    account = db.get(Account, account_id)

    if account is None:
        raise ValueError("Account not found.")

    return calculate_account_balance(
        account.account_type,
        total_debit,
        total_credit,
    )
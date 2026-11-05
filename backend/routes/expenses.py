
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.models import (
    Account,
    Expense,
    BankAccount,
    CashAccount,
)
from backend.schemas import ExpenseCreate
from backend.accounting import (
    initialize_standard_accounts,
    money,
)
from backend.ledger_posting import post_journal_entry


router = APIRouter(
    prefix="/api/expenses",
    tags=["Expenses"],
)


def get_active_expense_account(
    db: Session,
    account_id: int,
) -> Account:
    account = (
        db.query(Account)
        .filter(
            Account.id == account_id,
            Account.is_active.is_(True),
        )
        .first()
    )

    if account is None:
        raise ValueError(
            "Selected expense account does not exist or is inactive."
        )

    if account.account_type != "expense":
        raise ValueError(
            "Selected ledger account must be an expense account."
        )

    return account


def get_payment_ledger_account(
    db: Session,
    payment_method: str,
    cash_account_id: int | None,
    bank_account_id: int | None,
) -> Account:
    if payment_method == "cash":
        if cash_account_id is None:
            raise ValueError(
                "Cash account is required for cash expenses."
            )

        if bank_account_id is not None:
            raise ValueError(
                "Do not provide a bank account for a cash expense."
            )

        cash_account = (
            db.query(CashAccount)
            .filter(
                CashAccount.id == cash_account_id,
                CashAccount.is_active.is_(True),
            )
            .first()
        )

        if cash_account is None:
            raise ValueError(
                "Cash account does not exist or is inactive."
            )

        ledger_account_id = cash_account.ledger_account_id

    elif payment_method == "bank":
        if bank_account_id is None:
            raise ValueError(
                "Bank account is required for bank expenses."
            )

        if cash_account_id is not None:
            raise ValueError(
                "Do not provide a cash account for a bank expense."
            )

        bank_account = (
            db.query(BankAccount)
            .filter(
                BankAccount.id == bank_account_id,
                BankAccount.is_active.is_(True),
            )
            .first()
        )

        if bank_account is None:
            raise ValueError(
                "Bank account does not exist or is inactive."
            )

        ledger_account_id = bank_account.ledger_account_id

    else:
        raise ValueError(
            "Payment method must be 'cash' or 'bank'."
        )

    if ledger_account_id is None:
        raise ValueError(
            "Selected payment account has no linked ledger account."
        )

    ledger_account = (
        db.query(Account)
        .filter(
            Account.id == ledger_account_id,
            Account.is_active.is_(True),
        )
        .first()
    )

    if ledger_account is None:
        raise ValueError(
            "Payment ledger account is missing or inactive."
        )

    if ledger_account.account_type != "asset":
        raise ValueError(
            "Cash or bank payment must be linked to an asset account."
        )

    return ledger_account


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
)
def create_expense(
    payload: ExpenseCreate,
    db: Session = Depends(get_db),
):
    try:
        initialize_standard_accounts(db)

        amount = money(payload.amount)

        if amount <= 0:
            raise HTTPException(
                status_code=400,
                detail="Expense amount must be greater than zero.",
            )

        description = payload.description.strip()

        if not description:
            raise HTTPException(
                status_code=400,
                detail="Expense description is required.",
            )

        payment_method = (
            payload.payment_method or ""
        ).strip().lower()

        if payment_method not in {"cash", "bank"}:
            raise HTTPException(
                status_code=400,
                detail="Payment method must be cash or bank.",
            )

        expense_account = get_active_expense_account(
            db,
            payload.account_id,
        )

        payment_account = get_payment_ledger_account(
            db,
            payment_method,
            payload.cash_account_id,
            payload.bank_account_id,
        )

        expense = Expense(
            account_id=expense_account.id,
            payment_method=payment_method,
            bank_account_id=payload.bank_account_id,
            cash_account_id=payload.cash_account_id,
            description=description,
            amount=amount,
            expense_date=payload.expense_date,
            reference=payload.reference,
        )

        db.add(expense)
        db.flush()

        post_journal_entry(
            db,
            entry_date=payload.expense_date,
            description=description,
            reference=payload.reference or f"EXPENSE-{expense.id}",
            lines=[
                {
                    "account_id": expense_account.id,
                    "debit": amount,
                    "credit": 0,
                    "description": description,
                },
                {
                    "account_id": payment_account.id,
                    "debit": 0,
                    "credit": amount,
                    "description": f"Paid through {payment_method}",
                },
            ],
        )

        db.commit()
        db.refresh(expense)

        return {
            "message": "Expense recorded successfully.",
            "expense": expense,
        }

    except HTTPException:
        db.rollback()
        raise

    except ValueError as exc:
        db.rollback()
        raise HTTPException(
            status_code=400,
            detail=str(exc),
        )

    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=400,
            detail=(
                "Could not record expense. "
                "Check the submitted information."
            ),
        )


@router.get("")
def list_expenses(
    account_id: int | None = None,
    payment_method: str | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
):
    query = db.query(Expense)

    if account_id is not None:
        query = query.filter(
            Expense.account_id == account_id
        )

    if payment_method:
        query = query.filter(
            Expense.payment_method == payment_method.strip().lower()
        )

    return (
        query.order_by(
            Expense.expense_date.desc(),
            Expense.id.desc(),
        )
        .limit(limit)
        .all()
    )


@router.get("/{expense_id}")
def get_expense(
    expense_id: int,
    db: Session = Depends(get_db),
):
    expense = (
        db.query(Expense)
        .filter(Expense.id == expense_id)
        .first()
    )

    if expense is None:
        raise HTTPException(
            status_code=404,
            detail="Expense not found.",
        )

    return expense

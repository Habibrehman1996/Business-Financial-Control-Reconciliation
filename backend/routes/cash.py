
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.models import Account, CashAccount, CashTransaction
from backend.schemas import (
    CashAccountCreate,
    CashAccountRead,
    CashTransactionCreate,
    CashTransactionRead,
)
from backend.accounting import (
    get_account_by_code,
    initialize_standard_accounts,
    money,
)
from backend.ledger_posting import post_journal_entry


router = APIRouter(
    prefix="/api/cash",
    tags=["Cash Management"],
)


def create_cash_ledger_account(
    db: Session,
    account_name: str,
) -> Account:
    """Create a separate ledger account for each cash account."""
    parent = get_account_by_code(db, "1010")

    if parent is None:
        raise ValueError("Standard Cash account is missing.")

    latest = (
        db.query(Account.id)
        .filter(Account.code.like("1010-%"))
        .order_by(Account.id.desc())
        .first()
    )

    sequence = (latest[0] if latest else 0) + 1
    code = f"1010-{sequence:08d}"

    ledger = Account(
        code=code,
        name=f"Cash - {account_name}",
        account_type="asset",
        parent_id=parent.id,
        is_active=True,
    )

    db.add(ledger)
    db.flush()

    return ledger


@router.post(
    "/accounts",
    response_model=CashAccountRead,
    status_code=status.HTTP_201_CREATED,
)
def create_cash_account(
    payload: CashAccountCreate,
    db: Session = Depends(get_db),
):
    try:
        initialize_standard_accounts(db)

        ledger = create_cash_ledger_account(
            db,
            payload.name.strip(),
        )

        cash_account = CashAccount(
            name=payload.name.strip(),
            ledger_account_id=ledger.id,
            opening_balance=money(payload.opening_balance),
            is_active=True,
        )

        db.add(cash_account)
        db.flush()

        opening_balance = money(payload.opening_balance)

        if opening_balance > 0:
            equity = get_account_by_code(db, "3010")

            if equity is None:
                raise ValueError("Opening Balance Equity account is missing.")

            post_journal_entry(
                db,
                entry_date=date.today(),
                description=f"Opening cash balance - {payload.name}",
                reference=f"CASH-OPEN-{cash_account.id}",
                lines=[
                    {
                        "account_id": ledger.id,
                        "debit": opening_balance,
                        "credit": 0,
                        "description": "Cash opening balance",
                    },
                    {
                        "account_id": equity.id,
                        "debit": 0,
                        "credit": opening_balance,
                        "description": "Opening balance equity",
                    },
                ],
            )

        db.commit()
        db.refresh(cash_account)

        return cash_account

    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc))

    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=400,
            detail="Could not create cash account.",
        )


@router.get("/accounts", response_model=list[CashAccountRead])
def list_cash_accounts(
    active_only: bool = True,
    db: Session = Depends(get_db),
):
    query = db.query(CashAccount)

    if active_only:
        query = query.filter(CashAccount.is_active.is_(True))

    return query.order_by(CashAccount.id.desc()).all()


@router.get("/accounts/{account_id}", response_model=CashAccountRead)
def get_cash_account(
    account_id: int,
    db: Session = Depends(get_db),
):
    account = (
        db.query(CashAccount)
        .filter(CashAccount.id == account_id)
        .first()
    )

    if account is None:
        raise HTTPException(
            status_code=404,
            detail="Cash account not found.",
        )

    return account


@router.post(
    "/transactions",
    response_model=CashTransactionRead,
    status_code=status.HTTP_201_CREATED,
)
def create_cash_transaction(
    payload: CashTransactionCreate,
    db: Session = Depends(get_db),
):
    cash_account = (
        db.query(CashAccount)
        .filter(
            CashAccount.id == payload.cash_account_id,
            CashAccount.is_active.is_(True),
        )
        .first()
    )

    if cash_account is None:
        raise HTTPException(
            status_code=404,
            detail="Active cash account not found.",
        )

    counter_account = (
        db.query(Account)
        .filter(
            Account.id == payload.counter_account_id,
            Account.is_active.is_(True),
        )
        .first()
    )

    if counter_account is None:
        raise HTTPException(
            status_code=404,
            detail="Counter account not found or inactive.",
        )

    if counter_account.id == cash_account.ledger_account_id:
        raise HTTPException(
            status_code=400,
            detail="Cash account cannot be its own counter account.",
        )

    amount = money(payload.amount)

    try:
        transaction = CashTransaction(
            cash_account_id=cash_account.id,
            transaction_date=payload.transaction_date,
            description=payload.description.strip(),
            amount=amount,
            direction=payload.direction,
            reference=payload.reference,
            is_reconciled=False,
        )

        db.add(transaction)
        db.flush()

        if payload.direction == "in":
            lines = [
                {
                    "account_id": cash_account.ledger_account_id,
                    "debit": amount,
                    "credit": 0,
                    "description": payload.description,
                },
                {
                    "account_id": counter_account.id,
                    "debit": 0,
                    "credit": amount,
                    "description": payload.description,
                },
            ]
        else:
            lines = [
                {
                    "account_id": counter_account.id,
                    "debit": amount,
                    "credit": 0,
                    "description": payload.description,
                },
                {
                    "account_id": cash_account.ledger_account_id,
                    "debit": 0,
                    "credit": amount,
                    "description": payload.description,
                },
            ]

        post_journal_entry(
            db,
            entry_date=payload.transaction_date,
            description=payload.description,
            reference=payload.reference or f"CASH-TXN-{transaction.id}",
            lines=lines,
        )

        db.commit()
        db.refresh(transaction)

        return transaction

    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc))

    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=400,
            detail="Could not save cash transaction.",
        )


@router.get(
    "/transactions",
    response_model=list[CashTransactionRead],
)
def list_cash_transactions(
    cash_account_id: int | None = None,
    unreconciled_only: bool = False,
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
):
    query = db.query(CashTransaction)

    if cash_account_id is not None:
        query = query.filter(
            CashTransaction.cash_account_id == cash_account_id
        )

    if unreconciled_only:
        query = query.filter(
            CashTransaction.is_reconciled.is_(False)
        )

    return (
        query.order_by(
            CashTransaction.transaction_date.desc(),
            CashTransaction.id.desc(),
        )
        .limit(limit)
        .all()
    )

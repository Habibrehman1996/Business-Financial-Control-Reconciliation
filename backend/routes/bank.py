import csv
import hashlib
import io

from fastapi import File, UploadFile
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.schemas import (
    BankAccountCreate,
    BankAccountRead,
    BankTransactionCreate,
    BankTransactionRead,
    BankStatementImportResponse,
    BankStatementLineRead,
)
from backend.schemas import (
    BankAccountCreate,
    BankAccountRead,
    BankTransactionCreate,
    BankTransactionRead,
)
from backend.accounting import (
    get_account_by_code,
    initialize_standard_accounts,
    money,
)
from backend.ledger_posting import post_journal_entry


router = APIRouter(
    prefix="/api/bank",
    tags=["Bank Management"],
)


def create_bank_ledger_account(
    db: Session,
    bank_name: str,
    account_name: str,
) -> Account:
    """Create a separate ledger account for each bank account."""

    base_account = get_account_by_code(db, "1020")

    if base_account is None:
        raise ValueError("Standard Bank account is missing.")

    latest = (
        db.query(Account.id)
        .filter(Account.code.like("1020-%"))
        .order_by(Account.id.desc())
        .first()
    )

    sequence = (latest[0] if latest else 0) + 1
    code = f"1020-{sequence:08d}"

    ledger = Account(
        code=code,
        name=f"{bank_name} - {account_name}",
        account_type="asset",
        parent_id=base_account.id,
        is_active=True,
    )

    db.add(ledger)
    db.flush()

    return ledger


# --------------------------------------------------
# BANK ACCOUNTS
# --------------------------------------------------

@router.post(
    "/accounts",
    response_model=BankAccountRead,
    status_code=status.HTTP_201_CREATED,
)
def create_bank_account(
    payload: BankAccountCreate,
    db: Session = Depends(get_db),
):
    name = payload.name.strip()
    bank_name = payload.bank_name.strip()
    account_number = payload.account_number.strip()

    # Input validation
    if not name or len(name) < 2:
        raise HTTPException(
            status_code=400,
            detail="Valid bank account name is required.",
        )

    if not bank_name or len(bank_name) < 2:
        raise HTTPException(
            status_code=400,
            detail="Valid bank name is required.",
        )

    if not account_number or len(account_number) < 3:
        raise HTTPException(
            status_code=400,
            detail="Valid bank account number is required.",
        )

    if payload.opening_balance < 0:
        raise HTTPException(
            status_code=400,
            detail="Bank opening balance cannot be negative.",
        )

    # Duplicate account number check
    existing = (
        db.query(BankAccount)
        .filter(
            BankAccount.account_number == account_number
        )
        .first()
    )

    if existing:
        raise HTTPException(
            status_code=409,
            detail="This bank account number already exists.",
        )

    try:
        initialize_standard_accounts(db)

        ledger = create_bank_ledger_account(
            db,
            bank_name,
            name,
        )

        bank_account = BankAccount(
            name=name,
            bank_name=bank_name,
            account_number=account_number,
            ledger_account_id=ledger.id,
            opening_balance=money(payload.opening_balance),
            is_active=True,
        )

        db.add(bank_account)
        db.flush()

        opening_balance = money(payload.opening_balance)

        if opening_balance > 0:
            opening_equity = get_account_by_code(db, "3010")

            if opening_equity is None:
                raise ValueError(
                    "Opening Balance Equity account is missing."
                )

            post_journal_entry(
                db,
                entry_date=date.today(),
                description=f"Opening balance - {bank_name}",
                reference=f"BANK-OPEN-{bank_account.id}",
                lines=[
                    {
                        "account_id": ledger.id,
                        "debit": opening_balance,
                        "credit": 0,
                        "description": "Bank opening balance",
                    },
                    {
                        "account_id": opening_equity.id,
                        "debit": 0,
                        "credit": opening_balance,
                        "description": "Opening balance equity",
                    },
                ],
            )

        db.commit()
        db.refresh(bank_account)

        return bank_account

    except ValueError as exc:
        db.rollback()
        raise HTTPException(
            status_code=400,
            detail=str(exc),
        )

    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="Bank account could not be created because of duplicate data.",
        )


@router.get(
    "/accounts",
    response_model=list[BankAccountRead],
)
def list_bank_accounts(
    active_only: bool = True,
    db: Session = Depends(get_db),
):
    query = db.query(BankAccount)

    if active_only:
        query = query.filter(
            BankAccount.is_active.is_(True)
        )

    return query.order_by(
        BankAccount.id.desc()
    ).all()


@router.get(
    "/accounts/{account_id}",
    response_model=BankAccountRead,
)
def get_bank_account(
    account_id: int,
    db: Session = Depends(get_db),
):
    account = (
        db.query(BankAccount)
        .filter(BankAccount.id == account_id)
        .first()
    )

    if account is None:
        raise HTTPException(
            status_code=404,
            detail="Bank account not found.",
        )

    return account


# --------------------------------------------------
# BANK TRANSACTIONS
# --------------------------------------------------

@router.post(
    "/transactions",
    response_model=BankTransactionRead,
    status_code=status.HTTP_201_CREATED,
)
def create_bank_transaction(
    payload: BankTransactionCreate,
    db: Session = Depends(get_db),
):
    bank_account = (
        db.query(BankAccount)
        .filter(
            BankAccount.id == payload.bank_account_id,
            BankAccount.is_active.is_(True),
        )
        .first()
    )

    if bank_account is None:
        raise HTTPException(
            status_code=404,
            detail="Active bank account not found.",
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

    if counter_account.id == bank_account.ledger_account_id:
        raise HTTPException(
            status_code=400,
            detail="Bank account cannot be its own counter account.",
        )

    description = payload.description.strip()

    if len(description) < 2:
        raise HTTPException(
            status_code=400,
            detail="Transaction description is required.",
        )

    amount = money(payload.amount)

    if amount <= 0:
        raise HTTPException(
            status_code=400,
            detail="Transaction amount must be greater than zero.",
        )

    reference = (
        payload.reference.strip()
        if payload.reference and payload.reference.strip()
        else None
    )

    try:
        transaction = BankTransaction(
            bank_account_id=bank_account.id,
            transaction_date=payload.transaction_date,
            description=description,
            reference=reference,
            amount=amount,
            direction=payload.direction,
            source="book",
            is_reconciled=False,
        )

        db.add(transaction)
        db.flush()

        if payload.direction == "in":
            lines = [
                {
                    "account_id": bank_account.ledger_account_id,
                    "debit": amount,
                    "credit": 0,
                    "description": description,
                },
                {
                    "account_id": counter_account.id,
                    "debit": 0,
                    "credit": amount,
                    "description": description,
                },
            ]

        else:
            lines = [
                {
                    "account_id": counter_account.id,
                    "debit": amount,
                    "credit": 0,
                    "description": description,
                },
                {
                    "account_id": bank_account.ledger_account_id,
                    "debit": 0,
                    "credit": amount,
                    "description": description,
                },
            ]

        post_journal_entry(
            db,
            entry_date=payload.transaction_date,
            description=description,
            reference=reference or f"BANK-TXN-{transaction.id}",
            lines=lines,
        )

        db.commit()
        db.refresh(transaction)

        return transaction

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
            detail="Could not save bank transaction.",
        )


@router.get(
    "/transactions",
    response_model=list[BankTransactionRead],
)
def list_bank_transactions(
    bank_account_id: int | None = None,
    unreconciled_only: bool = False,
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
):
    query = db.query(BankTransaction)

    if bank_account_id is not None:
        query = query.filter(
            BankTransaction.bank_account_id == bank_account_id
        )

    if unreconciled_only:
        query = query.filter(
            BankTransaction.is_reconciled.is_(False)
        )

    return (
        query.order_by(
            BankTransaction.transaction_date.desc(),
            BankTransaction.id.desc(),
        )
        .limit(limit)
        .all()
    )

from datetime import date
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.models import (
    BankAccount,
    CashAccount,
    ReconciliationRun,
)
from backend.schemas import ReconciliationCreate
from backend.accounting import get_account_balance, money


router = APIRouter(
    prefix="/api/reconciliation",
    tags=["Reconciliation"],
)


def calculate_reconciliation(
    db: Session,
    account_type: str,
    account_id: int,
    statement_closing_balance,
    statement_date: date,
):
    if account_type == "bank":
        account = (
            db.query(BankAccount)
            .filter(
                BankAccount.id == account_id,
                BankAccount.is_active.is_(True),
            )
            .first()
        )
    elif account_type == "cash":
        account = (
            db.query(CashAccount)
            .filter(
                CashAccount.id == account_id,
                CashAccount.is_active.is_(True),
            )
            .first()
        )
    else:
        raise ValueError("Account type must be 'bank' or 'cash'.")

    if account is None:
        raise ValueError(f"{account_type.title()} account not found or inactive.")

    book_balance = get_account_balance(
    db,
    account.ledger_account_id,
    as_of_date=statement_date,
)

    statement_balance = money(statement_closing_balance)
    difference = money(statement_balance - book_balance)

    reconciliation_status = (
        "matched" if difference == 0 else "unmatched"
    )

    return account, book_balance, statement_balance, difference, reconciliation_status


@router.post(
    "/bank",
    status_code=status.HTTP_201_CREATED,
)
def reconcile_bank(
    payload: ReconciliationCreate,
    db: Session = Depends(get_db),
):
    try:
        account, book_balance, statement_balance, difference, result = (
            calculate_reconciliation(
                db=db,
                account_type="bank",
                account_id=payload.account_id,
                statement_closing_balance=payload.statement_closing_balance,
                statement_date=payload.statement_date,
            )
        )

        reconciliation = ReconciliationRun(
            account_type="bank",
            account_id=account.id,
            statement_date=payload.statement_date,
            statement_closing_balance=statement_balance,
            book_closing_balance=book_balance,
            difference=difference,
            status=result,
            notes=payload.notes,
        )

        db.add(reconciliation)
        db.commit()
        db.refresh(reconciliation)

        return {
            "message": "Bank reconciliation completed.",
            "reconciliation": reconciliation,
            "account_name": account.name,
        }

    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc))


@router.post(
    "/cash",
    status_code=status.HTTP_201_CREATED,
)
def reconcile_cash(
    payload: ReconciliationCreate,
    db: Session = Depends(get_db),
):
    try:
        account, book_balance, statement_balance, difference, result = (
            calculate_reconciliation(
                db=db,
                account_type="cash",
                account_id=payload.account_id,
                statement_date=payload.statement_date,
                statement_closing_balance=payload.statement_closing_balance,
            )
        )

        reconciliation = ReconciliationRun(
            account_type="cash",
            account_id=account.id,
            statement_date=payload.statement_date,
            statement_closing_balance=statement_balance,
            book_closing_balance=book_balance,
            difference=difference,
            status=result,
            notes=payload.notes,
        )

        db.add(reconciliation)
        db.commit()
        db.refresh(reconciliation)

        return {
            "message": "Cash reconciliation completed.",
            "reconciliation": reconciliation,
            "account_name": account.name,
        }

    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("")
def list_reconciliations(
    account_type: str | None = None,
    reconciliation_status: str | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
):
    query = db.query(ReconciliationRun)

    if account_type:
        if account_type not in ("bank", "cash"):
            raise HTTPException(
                status_code=400,
                detail="Account type must be 'bank' or 'cash'.",
            )
        query = query.filter(
            ReconciliationRun.account_type == account_type
        )

    if reconciliation_status:
        query = query.filter(
            ReconciliationRun.status == reconciliation_status
        )

    return (
        query.order_by(
            ReconciliationRun.statement_date.desc(),
            ReconciliationRun.id.desc(),
        )
        .limit(limit)
        .all()
    )


@router.get("/{reconciliation_id}")
def get_reconciliation(
    reconciliation_id: int,
    db: Session = Depends(get_db),
):
    reconciliation = (
        db.query(ReconciliationRun)
        .filter(ReconciliationRun.id == reconciliation_id)
        .first()
    )

    if reconciliation is None:
        raise HTTPException(
            status_code=404,
            detail="Reconciliation record not found.",
        )

    return reconciliation

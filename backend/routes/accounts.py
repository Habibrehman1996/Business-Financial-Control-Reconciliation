
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.models import Account
from backend.schemas import AccountCreate, AccountRead
from backend.accounting import (
    initialize_standard_accounts,
    get_account_balance,
    validate_account_type,
)


router = APIRouter(
    prefix="/api/accounts",
    tags=["Chart of Accounts"],
)


@router.post(
    "",
    response_model=AccountRead,
    status_code=status.HTTP_201_CREATED,
)
def create_account(
    payload: AccountCreate,
    db: Session = Depends(get_db),
):
    existing = (
    db.query(Account)
    .filter(
        (Account.code == payload.code.strip())
        | (Account.name == payload.name.strip())
    )
    .first()
)

    if existing:
        raise HTTPException(
        status_code=409,
        detail={
            "message": "Duplicate account detected",
            "existing_id": existing.id,
            "existing_code": existing.code,
            "existing_name": existing.name,
        },
    )

    account_type = validate_account_type(payload.account_type)

    if payload.parent_id is not None:
        parent = db.query(Account).filter(
            Account.id == payload.parent_id
        ).first()

        if parent is None:
            raise HTTPException(status_code=404, detail="Parent account not found.")

    account = Account(
        code=payload.code.strip(),
        name=payload.name.strip(),
        account_type=account_type,
        parent_id=payload.parent_id,
        is_active=True,
    )

    try:
        db.add(account)
        db.commit()
        db.refresh(account)
        return account
    except IntegrityError as exc:
        db.rollback()
        print("ACTUAL ACCOUNT ERROR:", repr(exc.orig))
        raise HTTPException(
            status_code=409,
            detail=f"Database constraint error: {exc.orig}",
    )


@router.get("", response_model=list[AccountRead])
def list_accounts(
    active_only: bool = True,
    db: Session = Depends(get_db),
):
    query = db.query(Account)

    if active_only:
        query = query.filter(Account.is_active.is_(True))

    return query.order_by(Account.code.asc()).all()


@router.get("/{account_id}", response_model=AccountRead)
def get_account(
    account_id: int,
    db: Session = Depends(get_db),
):
    account = db.query(Account).filter(Account.id == account_id).first()

    if account is None:
        raise HTTPException(status_code=404, detail="Account not found.")

    return account


@router.get("/{account_id}/balance")
def account_balance(
    account_id: int,
    db: Session = Depends(get_db),
):
    try:
        balance = get_account_balance(db, account_id)
        return {
            "account_id": account_id,
            "balance": balance,
        }
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.post("/initialize-standard")
def initialize_accounts(
    db: Session = Depends(get_db),
):
    try:
        created = initialize_standard_accounts(db)
        db.commit()

        return {
            "message": "Standard chart of accounts initialized.",
            "created_count": len(created),
            "accounts": [
                {
                    "id": account.id,
                    "code": account.code,
                    "name": account.name,
                    "account_type": account.account_type,
                }
                for account in created
            ],
        }
    except Exception:
        db.rollback()
        raise

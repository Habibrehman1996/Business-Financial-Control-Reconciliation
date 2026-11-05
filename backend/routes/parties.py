
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.models import Customer, Supplier
from backend.schemas import PartyCreate, CustomerRead, SupplierRead
from backend.accounting import (
    get_account_by_code,
    initialize_standard_accounts,
    money,
)
from backend.ledger_posting import post_journal_entry


router = APIRouter(
    prefix="/api/parties",
    tags=["Customers & Suppliers"],
)


def post_customer_opening_balance(
    db: Session,
    customer: Customer,
    opening_balance,
) -> None:
    amount = money(abs(opening_balance))

    if amount == 0:
        return

    receivable = get_account_by_code(db, "1100")
    opening_equity = get_account_by_code(db, "3010")

    if receivable is None or opening_equity is None:
        raise ValueError("Required Accounts Receivable or Opening Equity account is missing.")

    if opening_balance > 0:
        lines = [
            {
                "account_id": receivable.id,
                "debit": amount,
                "credit": 0,
                "description": f"Opening receivable - {customer.name}",
            },
            {
                "account_id": opening_equity.id,
                "debit": 0,
                "credit": amount,
                "description": "Customer opening balance",
            },
        ]
    else:
        lines = [
            {
                "account_id": opening_equity.id,
                "debit": amount,
                "credit": 0,
                "description": "Customer credit opening balance",
            },
            {
                "account_id": receivable.id,
                "debit": 0,
                "credit": amount,
                "description": f"Customer advance - {customer.name}",
            },
        ]

    post_journal_entry(
        db,
        entry_date=date.today(),
        description=f"Opening balance - Customer {customer.name}",
        reference=f"CUSTOMER-OPEN-{customer.id}",
        lines=lines,
    )


def post_supplier_opening_balance(
    db: Session,
    supplier: Supplier,
    opening_balance,
) -> None:
    amount = money(abs(opening_balance))

    if amount == 0:
        return

    payable = get_account_by_code(db, "2010")
    opening_equity = get_account_by_code(db, "3010")

    if payable is None or opening_equity is None:
        raise ValueError("Required Accounts Payable or Opening Equity account is missing.")

    if opening_balance > 0:
        lines = [
            {
                "account_id": opening_equity.id,
                "debit": amount,
                "credit": 0,
                "description": "Supplier opening balance",
            },
            {
                "account_id": payable.id,
                "debit": 0,
                "credit": amount,
                "description": f"Opening payable - {supplier.name}",
            },
        ]
    else:
        lines = [
            {
                "account_id": payable.id,
                "debit": amount,
                "credit": 0,
                "description": f"Supplier advance - {supplier.name}",
            },
            {
                "account_id": opening_equity.id,
                "debit": 0,
                "credit": amount,
                "description": "Supplier debit opening balance",
            },
        ]

    post_journal_entry(
        db,
        entry_date=date.today(),
        description=f"Opening balance - Supplier {supplier.name}",
        reference=f"SUPPLIER-OPEN-{supplier.id}",
        lines=lines,
    )


@router.post(
    "/customers",
    response_model=CustomerRead,
    status_code=status.HTTP_201_CREATED,
)
def create_customer(
    payload: PartyCreate,
    db: Session = Depends(get_db),
):
    try:
        initialize_standard_accounts(db)

        opening_balance = money(payload.opening_balance)

        customer = Customer(
            name=payload.name.strip(),
            phone=payload.phone,
            email=payload.email,
            address=payload.address,
            opening_balance=opening_balance,
            is_active=True,
        )

        db.add(customer)
        db.flush()

        post_customer_opening_balance(
            db,
            customer,
            opening_balance,
        )

        db.commit()
        db.refresh(customer)

        return customer

    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc))

    except IntegrityError as exc:
        db.rollback()
        print("ACTUAL CUSTOMER ERROR:", repr(exc.orig))
        raise HTTPException(
            status_code=400,
            detail=f"Database constraint error: {exc.orig}",
        )


@router.get("/customers", response_model=list[CustomerRead])
def list_customers(
    active_only: bool = True,
    search: str | None = None,
    limit: int = 100,
    db: Session = Depends(get_db),
):
    if limit < 1 or limit > 500:
        raise HTTPException(
            status_code=400,
            detail="limit must be between 1 and 500.",
        )

    query = db.query(Customer)

    if active_only:
        query = query.filter(Customer.is_active.is_(True))

    if search:
        query = query.filter(
            Customer.name.ilike(f"%{search.strip()}%")
        )

    return (
        query.order_by(Customer.name.asc())
        .limit(limit)
        .all()
    )


@router.get("/customers/{customer_id}", response_model=CustomerRead)
def get_customer(
    customer_id: int,
    db: Session = Depends(get_db),
):
    customer = (
        db.query(Customer)
        .filter(Customer.id == customer_id)
        .first()
    )

    if customer is None:
        raise HTTPException(
            status_code=404,
            detail="Customer not found.",
        )

    return customer


@router.post(
    "/suppliers",
    response_model=SupplierRead,
    status_code=status.HTTP_201_CREATED,
)
def create_supplier(
    payload: PartyCreate,
    db: Session = Depends(get_db),
):
    try:
        initialize_standard_accounts(db)

        opening_balance = money(payload.opening_balance)

        supplier = Supplier(
            name=payload.name.strip(),
            phone=payload.phone,
            email=payload.email,
            address=payload.address,
            opening_balance=opening_balance,
            is_active=True,
        )

        db.add(supplier)
        db.flush()

        post_supplier_opening_balance(
            db,
            supplier,
            opening_balance,
        )

        db.commit()
        db.refresh(supplier)

        return supplier

    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc))

    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=400,
            detail="Could not create supplier. Check the submitted information.",
        )


@router.get("/suppliers", response_model=list[SupplierRead])
def list_suppliers(
    active_only: bool = True,
    search: str | None = None,
    limit: int = 100,
    db: Session = Depends(get_db),
):
    if limit < 1 or limit > 500:
        raise HTTPException(
            status_code=400,
            detail="limit must be between 1 and 500.",
        )

    query = db.query(Supplier)

    if active_only:
        query = query.filter(Supplier.is_active.is_(True))

    if search:
        query = query.filter(
            Supplier.name.ilike(f"%{search.strip()}%")
        )

    return (
        query.order_by(Supplier.name.asc())
        .limit(limit)
        .all()
    )


@router.get("/suppliers/{supplier_id}", response_model=SupplierRead)
def get_supplier(
    supplier_id: int,
    db: Session = Depends(get_db),
):
    supplier = (
        db.query(Supplier)
        .filter(Supplier.id == supplier_id)
        .first()
    )

    if supplier is None:
        raise HTTPException(
            status_code=404,
            detail="Supplier not found.",
        )

    return supplier

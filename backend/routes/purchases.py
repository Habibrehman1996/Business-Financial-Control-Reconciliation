
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload

from backend.database import get_db
from backend.models import (
    Account,
    Supplier,
    Product,
    PurchaseBill,
    PurchaseBillItem,
    SupplierPayment,
    BankAccount,
    CashAccount,
    StockMovement,
)
from backend.schemas import PurchaseBillCreate, SupplierPaymentCreate
from backend.accounting import (
    get_account_by_code,
    initialize_standard_accounts,
    money,
    quantity,
)
from backend.ledger_posting import post_journal_entry


router = APIRouter(
    prefix="/api/purchases",
    tags=["Purchases"],
)


def get_required_account(db: Session, code: str) -> Account:
    account = get_account_by_code(db, code)

    if account is None or not account.is_active:
        raise ValueError(
            f"Required ledger account {code} is missing or inactive."
        )

    return account


def update_bill_status(db: Session, bill: PurchaseBill) -> None:
    payments = (
        db.query(SupplierPayment.amount)
        .filter(SupplierPayment.bill_id == bill.id)
        .all()
    )

    total_paid = money(
        sum(
            (money(row[0]) for row in payments),
            Decimal("0.00"),
        )
    )

    bill_total = money(bill.total_amount)

    if total_paid <= 0:
        bill.status = "posted"
    elif total_paid < bill_total:
        bill.status = "partial"
    else:
        bill.status = "paid"


@router.post(
    "/bills",
    status_code=status.HTTP_201_CREATED,
)
def create_purchase_bill(
    payload: PurchaseBillCreate,
    db: Session = Depends(get_db),
):
    try:
        initialize_standard_accounts(db)

        bill_number = payload.bill_number.strip()

        if not bill_number:
            raise HTTPException(
                status_code=400,
                detail="Purchase bill number is required.",
            )

        duplicate = (
            db.query(PurchaseBill)
            .filter(PurchaseBill.bill_number == bill_number)
            .first()
        )

        if duplicate:
            raise HTTPException(
                status_code=409,
                detail="Purchase bill number already exists.",
            )

        if not payload.items:
            raise HTTPException(
                status_code=400,
                detail="Purchase bill must contain at least one item.",
            )

        if (
            payload.due_date is not None
            and payload.due_date < payload.bill_date
        ):
            raise HTTPException(
                status_code=400,
                detail="Due date cannot be earlier than bill date.",
            )

        supplier = (
            db.query(Supplier)
            .filter(
                Supplier.id == payload.supplier_id,
                Supplier.is_active.is_(True),
            )
            .first()
        )

        if supplier is None:
            raise HTTPException(
                status_code=404,
                detail="Active supplier not found.",
            )

        inventory_account = get_required_account(db, "1200")
        input_tax_account = get_required_account(db, "1300")
        payable_account = get_required_account(db, "2010")

        prepared_items = []
        product_cache = {}
        product_totals = {}

        subtotal = Decimal("0.00")

        # Validate items and lock each product once.
        for item in payload.items:
            item_quantity = quantity(item.quantity)
            unit_cost = money(item.unit_cost)

            if item_quantity <= 0:
                raise HTTPException(
                    status_code=400,
                    detail="Purchase quantity must be greater than zero.",
                )

            if unit_cost < 0:
                raise HTTPException(
                    status_code=400,
                    detail="Unit cost cannot be negative.",
                )

            product = product_cache.get(item.product_id)

            if product is None:
                product = (
                    db.query(Product)
                    .filter(
                        Product.id == item.product_id,
                        Product.is_active.is_(True),
                    )
                    .with_for_update()
                    .first()
                )

                if product is None:
                    raise HTTPException(
                        status_code=404,
                        detail=f"Active product {item.product_id} not found.",
                    )

                product_cache[item.product_id] = product

                product_totals[item.product_id] = {
                    "quantity": Decimal("0"),
                    "purchase_value": Decimal("0.00"),
                }

            line_total = money(item_quantity * unit_cost)

            subtotal += line_total

            product_totals[item.product_id]["quantity"] += item_quantity
            product_totals[item.product_id]["purchase_value"] += line_total

            prepared_items.append(
                {
                    "product": product,
                    "quantity": item_quantity,
                    "unit_cost": unit_cost,
                    "line_total": line_total,
                }
            )

        subtotal = money(subtotal)
        tax_amount = money(payload.tax_amount)

        if subtotal <= 0:
            raise HTTPException(
                status_code=400,
                detail="Purchase subtotal must be greater than zero.",
            )

        if tax_amount < 0:
            raise HTTPException(
                status_code=400,
                detail="Tax amount cannot be negative.",
            )

        total_amount = money(subtotal + tax_amount)

        if total_amount <= 0:
            raise HTTPException(
                status_code=400,
                detail="Purchase bill total must be greater than zero.",
            )

        bill = PurchaseBill(
            bill_number=bill_number,
            supplier_id=supplier.id,
            bill_date=payload.bill_date,
            due_date=payload.due_date,
            subtotal=subtotal,
            tax_amount=tax_amount,
            total_amount=total_amount,
            status="posted",
            notes=payload.notes,
        )

        db.add(bill)
        db.flush()

        # Update weighted average once per product, even if
        # the same product appears on multiple bill lines.
        for product_id, totals in product_totals.items():
            product = product_cache[product_id]

            old_quantity = quantity(product.current_stock)
            old_average_cost = money(
                product.average_cost or product.purchase_price
            )

            if old_quantity < 0 or old_average_cost < 0:
                raise ValueError(
                    f"Invalid existing stock or cost for {product.name}."
                )

            received_quantity = quantity(totals["quantity"])
            received_value = money(totals["purchase_value"])

            new_quantity = quantity(old_quantity + received_quantity)

            if new_quantity <= 0:
                raise ValueError(
                    f"Invalid resulting stock quantity for {product.name}."
                )

            old_stock_value = old_quantity * old_average_cost

            new_average_cost = money(
                (old_stock_value + received_value) / new_quantity
            )

            product.current_stock = new_quantity
            product.average_cost = new_average_cost

        # Save bill lines and stock movement history.
        for item in prepared_items:
            product = item["product"]

            db.add(
                PurchaseBillItem(
                    bill_id=bill.id,
                    product_id=product.id,
                    quantity=item["quantity"],
                    unit_cost=item["unit_cost"],
                    line_total=item["line_total"],
                )
            )

            db.add(
                StockMovement(
                    product_id=product.id,
                    movement_date=payload.bill_date,
                    movement_type="purchase",
                    quantity=item["quantity"],
                    unit_cost=item["unit_cost"],
                    reference=bill_number,
                    notes=f"Stock received against bill {bill_number}",
                )
            )

        db.flush()

        purchase_lines = [
            {
                "account_id": inventory_account.id,
                "debit": subtotal,
                "credit": 0,
                "description": f"Inventory purchase - {bill_number}",
            },
            {
                "account_id": payable_account.id,
                "debit": 0,
                "credit": total_amount,
                "description": f"Supplier payable - {supplier.name}",
            },
        ]

        if tax_amount > 0:
            purchase_lines.insert(
                1,
                {
                    "account_id": input_tax_account.id,
                    "debit": tax_amount,
                    "credit": 0,
                    "description": "Input tax on purchases",
                },
            )

        post_journal_entry(
            db,
            entry_date=payload.bill_date,
            description=f"Purchase bill {bill_number}",
            reference=bill_number,
            lines=purchase_lines,
        )

        db.commit()

        saved_bill = (
            db.query(PurchaseBill)
            .options(joinedload(PurchaseBill.items))
            .filter(PurchaseBill.id == bill.id)
            .first()
        )

        return {
            "message": "Purchase bill created successfully.",
            "bill": saved_bill,
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
            status_code=409,
            detail=(
                "Could not save purchase bill. "
                "Check duplicate or related records."
            ),
        )


@router.get("/bills")
def list_purchase_bills(
    supplier_id: int | None = None,
    bill_status: str | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
):
    query = (
        db.query(PurchaseBill)
        .options(joinedload(PurchaseBill.items))
    )

    if supplier_id is not None:
        query = query.filter(
            PurchaseBill.supplier_id == supplier_id
        )

    if bill_status:
        query = query.filter(
            PurchaseBill.status == bill_status
        )

    return (
        query.order_by(
            PurchaseBill.bill_date.desc(),
            PurchaseBill.id.desc(),
        )
        .limit(limit)
        .all()
    )


@router.get("/bills/{bill_id}")
def get_purchase_bill(
    bill_id: int,
    db: Session = Depends(get_db),
):
    bill = (
        db.query(PurchaseBill)
        .options(
            joinedload(PurchaseBill.items),
            joinedload(PurchaseBill.payments),
        )
        .filter(PurchaseBill.id == bill_id)
        .first()
    )

    if bill is None:
        raise HTTPException(
            status_code=404,
            detail="Purchase bill not found.",
        )

    return bill


@router.post(
    "/payments",
    status_code=status.HTTP_201_CREATED,
)
def make_supplier_payment(
    payload: SupplierPaymentCreate,
    db: Session = Depends(get_db),
):
    try:
        bill = (
            db.query(PurchaseBill)
            .filter(PurchaseBill.id == payload.bill_id)
            .with_for_update()
            .first()
        )

        if bill is None:
            raise HTTPException(
                status_code=404,
                detail="Purchase bill not found.",
            )

        if bill.status == "cancelled":
            raise HTTPException(
                status_code=400,
                detail="Payment cannot be made against a cancelled bill.",
            )

        amount = money(payload.amount)

        if amount <= 0:
            raise HTTPException(
                status_code=400,
                detail="Payment amount must be greater than zero.",
            )

        payment_method = (
            payload.payment_method or ""
        ).strip().lower()

        if payment_method not in {"cash", "bank"}:
            raise HTTPException(
                status_code=400,
                detail="Payment method must be cash or bank.",
            )

        if payment_method == "cash":
            if payload.bank_account_id is not None:
                raise HTTPException(
                    status_code=400,
                    detail="Bank account must not be provided for cash payment.",
                )

            if payload.cash_account_id is None:
                raise HTTPException(
                    status_code=400,
                    detail="Cash account is required for cash payment.",
                )

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

            payment_ledger_id = cash_account.ledger_account_id

        else:
            if payload.cash_account_id is not None:
                raise HTTPException(
                    status_code=400,
                    detail="Cash account must not be provided for bank payment.",
                )

            if payload.bank_account_id is None:
                raise HTTPException(
                    status_code=400,
                    detail="Bank account is required for bank payment.",
                )

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

            payment_ledger_id = bank_account.ledger_account_id

        if payment_ledger_id is None:
            raise HTTPException(
                status_code=400,
                detail="Selected payment account has no linked ledger account.",
            )

        payment_ledger_account = (
            db.query(Account)
            .filter(
                Account.id == payment_ledger_id,
                Account.is_active.is_(True),
            )
            .first()
        )

        if payment_ledger_account is None:
            raise HTTPException(
                status_code=400,
                detail="Linked payment ledger account is missing or inactive.",
            )

        payable_account = get_required_account(db, "2010")

        existing_payments = (
            db.query(SupplierPayment.amount)
            .filter(SupplierPayment.bill_id == bill.id)
            .all()
        )

        already_paid = money(
            sum(
                (money(row[0]) for row in existing_payments),
                Decimal("0.00"),
            )
        )

        outstanding = money(
            money(bill.total_amount) - already_paid
        )

        if outstanding <= 0:
            raise HTTPException(
                status_code=400,
                detail="This purchase bill has no outstanding balance.",
            )

        if amount > outstanding:
            raise HTTPException(
                status_code=400,
                detail=f"Payment exceeds outstanding balance of {outstanding}.",
            )

        payment = SupplierPayment(
            bill_id=bill.id,
            payment_date=payload.payment_date,
            amount=amount,
            payment_method=payment_method,
            bank_account_id=payload.bank_account_id,
            cash_account_id=payload.cash_account_id,
            reference=payload.reference,
        )

        db.add(payment)
        db.flush()

        post_journal_entry(
            db,
            entry_date=payload.payment_date,
            description=f"Supplier payment for bill {bill.bill_number}",
            reference=payload.reference or f"PAYMENT-{payment.id}",
            lines=[
                {
                    "account_id": payable_account.id,
                    "debit": amount,
                    "credit": 0,
                    "description": (
                        f"Supplier payable reduced - {bill.bill_number}"
                    ),
                },
                {
                    "account_id": payment_ledger_account.id,
                    "debit": 0,
                    "credit": amount,
                    "description": "Cash or bank payment",
                },
            ],
        )

        update_bill_status(db, bill)

        db.commit()
        db.refresh(payment)

        new_total_paid = money(already_paid + amount)
        new_outstanding = money(
            money(bill.total_amount) - new_total_paid
        )

        return {
            "message": "Supplier payment recorded successfully.",
            "payment": payment,
            "bill_status": bill.status,
            "total_paid": new_total_paid,
            "outstanding_balance": new_outstanding,
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
            detail="Could not record supplier payment.",
        )


@router.get("/payments")
def list_supplier_payments(
    bill_id: int | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
):
    query = db.query(SupplierPayment)

    if bill_id is not None:
        query = query.filter(
            SupplierPayment.bill_id == bill_id
        )

    return (
        query.order_by(
            SupplierPayment.payment_date.desc(),
            SupplierPayment.id.desc(),
        )
        .limit(limit)
        .all()
    )

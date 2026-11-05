
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload

from backend.database import get_db
from backend.models import (
    Account,
    Customer,
    Product,
    SalesInvoice,
    SalesInvoiceItem,
    CustomerPayment,
    BankAccount,
    CashAccount,
    StockMovement,
)
from backend.schemas import (
    SalesInvoiceCreate,
    CustomerPaymentCreate,
)
from backend.accounting import (
    get_account_by_code,
    initialize_standard_accounts,
    money,
    quantity,
)
from backend.ledger_posting import post_journal_entry


router = APIRouter(
    prefix="/api/sales",
    tags=["Sales"],
)


def get_required_account(db: Session, code: str) -> Account:
    account = get_account_by_code(db, code)

    if account is None or not account.is_active:
        raise ValueError(
            f"Required ledger account {code} is missing or inactive."
        )

    return account


def update_invoice_status(db: Session, invoice: SalesInvoice) -> None:
    payment_rows = (
        db.query(CustomerPayment.amount)
        .filter(CustomerPayment.invoice_id == invoice.id)
        .all()
    )

    total_paid = money(
        sum(
            (money(row[0]) for row in payment_rows),
            Decimal("0.00"),
        )
    )

    invoice_total = money(invoice.total_amount)

    if total_paid <= 0:
        invoice.status = "posted"
    elif total_paid < invoice_total:
        invoice.status = "partial"
    else:
        invoice.status = "paid"


@router.post(
    "/invoices",
    status_code=status.HTTP_201_CREATED,
)
def create_sales_invoice(
    payload: SalesInvoiceCreate,
    db: Session = Depends(get_db),
):
    try:
        initialize_standard_accounts(db)

        invoice_number = payload.invoice_number.strip()

        if not invoice_number:
            raise HTTPException(
                status_code=400,
                detail="Invoice number is required.",
            )

        duplicate = (
            db.query(SalesInvoice)
            .filter(SalesInvoice.invoice_number == invoice_number)
            .first()
        )

        if duplicate:
            raise HTTPException(
                status_code=409,
                detail="Invoice number already exists.",
            )

        customer = (
            db.query(Customer)
            .filter(
                Customer.id == payload.customer_id,
                Customer.is_active.is_(True),
            )
            .first()
        )

        if customer is None:
            raise HTTPException(
                status_code=404,
                detail="Active customer not found.",
            )

        if not payload.items:
            raise HTTPException(
                status_code=400,
                detail="Sales invoice must contain at least one item.",
            )

        if (
            payload.due_date is not None
            and payload.due_date < payload.invoice_date
        ):
            raise HTTPException(
                status_code=400,
                detail="Due date cannot be earlier than invoice date.",
            )

        receivable = get_required_account(db, "1100")
        sales_revenue = get_required_account(db, "4000")
        cogs_account = get_required_account(db, "5000")
        inventory_account = get_required_account(db, "1200")
        output_tax_account = get_required_account(db, "2020")

        prepared_items = []
        product_cache = {}
        required_stock = {}

        subtotal = Decimal("0.00")
        total_cost = Decimal("0.00")

        # First pass: validate products and aggregate required stock.
        for item in payload.items:
            item_quantity = quantity(item.quantity)
            unit_price = money(item.unit_price)

            if item_quantity <= 0:
                raise HTTPException(
                    status_code=400,
                    detail="Product quantity must be greater than zero.",
                )

            if unit_price < 0:
                raise HTTPException(
                    status_code=400,
                    detail="Unit selling price cannot be negative.",
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

            required_stock[item.product_id] = quantity(
                required_stock.get(
                    item.product_id,
                    Decimal("0"),
                ) + item_quantity
            )

            prepared_items.append(
                {
                    "product": product,
                    "quantity": item_quantity,
                    "unit_price": unit_price,
                }
            )

        # Validate total required quantity per product.
        for product_id, required_quantity in required_stock.items():
            product = product_cache[product_id]
            available_quantity = quantity(product.current_stock)

            if available_quantity < required_quantity:
                raise HTTPException(
                    status_code=400,
                    detail=(
                        f"Insufficient stock for {product.name}. "
                        f"Available: {available_quantity}, "
                        f"Required: {required_quantity}"
                    ),
                )

        # Second pass: calculate line values and cost of goods sold.
        for item in prepared_items:
            product = item["product"]

            unit_cost = money(
                product.average_cost or product.purchase_price
            )

            if unit_cost < 0:
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid inventory cost for {product.name}.",
                )

            line_total = money(
                item["quantity"] * item["unit_price"]
            )

            line_cost = money(
                item["quantity"] * unit_cost
            )

            item["unit_cost"] = unit_cost
            item["line_total"] = line_total
            item["line_cost"] = line_cost

            subtotal += line_total
            total_cost += line_cost

        subtotal = money(subtotal)
        total_cost = money(total_cost)
        tax_amount = money(payload.tax_amount)

        if tax_amount < 0:
            raise HTTPException(
                status_code=400,
                detail="Tax amount cannot be negative.",
            )

        if subtotal <= 0:
            raise HTTPException(
                status_code=400,
                detail="Invoice subtotal must be greater than zero.",
            )

        total_amount = money(subtotal + tax_amount)

        if total_amount <= 0:
            raise HTTPException(
                status_code=400,
                detail="Invoice total must be greater than zero.",
            )

        invoice = SalesInvoice(
            invoice_number=invoice_number,
            customer_id=customer.id,
            invoice_date=payload.invoice_date,
            due_date=payload.due_date,
            subtotal=subtotal,
            tax_amount=tax_amount,
            total_amount=total_amount,
            status="posted",
            notes=payload.notes,
        )

        db.add(invoice)
        db.flush()

        for item in prepared_items:
            product = item["product"]

            db.add(
                SalesInvoiceItem(
                    invoice_id=invoice.id,
                    product_id=product.id,
                    quantity=item["quantity"],
                    unit_price=item["unit_price"],
                    unit_cost=item["unit_cost"],
                    line_total=item["line_total"],
                )
            )

            product.current_stock = quantity(
                quantity(product.current_stock) - item["quantity"]
            )

            db.add(
                StockMovement(
                    product_id=product.id,
                    movement_date=payload.invoice_date,
                    movement_type="sale",
                    quantity=-item["quantity"],
                    unit_cost=item["unit_cost"],
                    reference=invoice_number,
                    notes=(
                        f"Stock deducted for sales invoice "
                        f"{invoice_number}"
                    ),
                )
            )

        db.flush()

        sales_lines = [
            {
                "account_id": receivable.id,
                "debit": total_amount,
                "credit": 0,
                "description": f"Receivable - {customer.name}",
            },
            {
                "account_id": sales_revenue.id,
                "debit": 0,
                "credit": subtotal,
                "description": f"Sales - {invoice_number}",
            },
        ]

        if tax_amount > 0:
            sales_lines.append(
                {
                    "account_id": output_tax_account.id,
                    "debit": 0,
                    "credit": tax_amount,
                    "description": "Output tax payable",
                }
            )

        post_journal_entry(
            db,
            entry_date=payload.invoice_date,
            description=f"Sales invoice {invoice_number}",
            reference=invoice_number,
            lines=sales_lines,
        )

        if total_cost > 0:
            post_journal_entry(
                db,
                entry_date=payload.invoice_date,
                description=f"Cost of goods sold - {invoice_number}",
                reference=f"COGS-{invoice_number}",
                lines=[
                    {
                        "account_id": cogs_account.id,
                        "debit": total_cost,
                        "credit": 0,
                        "description": "Cost of goods sold",
                    },
                    {
                        "account_id": inventory_account.id,
                        "debit": 0,
                        "credit": total_cost,
                        "description": "Inventory reduction",
                    },
                ],
            )

        db.commit()

        saved_invoice = (
            db.query(SalesInvoice)
            .options(
                joinedload(SalesInvoice.items),
            )
            .filter(SalesInvoice.id == invoice.id)
            .first()
        )

        return {
            "message": "Sales invoice created successfully.",
            "invoice": saved_invoice,
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
                "Could not save sales invoice. "
                "Check duplicate or related records."
            ),
        )


@router.get("/invoices")
def list_sales_invoices(
    customer_id: int | None = None,
    invoice_status: str | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
):
    query = (
        db.query(SalesInvoice)
        .options(joinedload(SalesInvoice.items))
    )

    if customer_id is not None:
        query = query.filter(
            SalesInvoice.customer_id == customer_id
        )

    if invoice_status:
        query = query.filter(
            SalesInvoice.status == invoice_status
        )

    return (
        query.order_by(
            SalesInvoice.invoice_date.desc(),
            SalesInvoice.id.desc(),
        )
        .limit(limit)
        .all()
    )


@router.get("/invoices/{invoice_id}")
def get_sales_invoice(
    invoice_id: int,
    db: Session = Depends(get_db),
):
    invoice = (
        db.query(SalesInvoice)
        .options(
            joinedload(SalesInvoice.items),
            joinedload(SalesInvoice.payments),
        )
        .filter(SalesInvoice.id == invoice_id)
        .first()
    )

    if invoice is None:
        raise HTTPException(
            status_code=404,
            detail="Sales invoice not found.",
        )

    return invoice


@router.post(
    "/payments",
    status_code=status.HTTP_201_CREATED,
)
def receive_customer_payment(
    payload: CustomerPaymentCreate,
    db: Session = Depends(get_db),
):
    try:
        invoice = (
            db.query(SalesInvoice)
            .filter(SalesInvoice.id == payload.invoice_id)
            .with_for_update()
            .first()
        )

        if invoice is None:
            raise HTTPException(
                status_code=404,
                detail="Invoice not found.",
            )

        if invoice.status == "cancelled":
            raise HTTPException(
                status_code=400,
                detail="Payment cannot be received for a cancelled invoice.",
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

        receivable = get_required_account(db, "1100")

        existing_payments = (
            db.query(CustomerPayment.amount)
            .filter(CustomerPayment.invoice_id == invoice.id)
            .all()
        )

        already_paid = money(
            sum(
                (money(row[0]) for row in existing_payments),
                Decimal("0.00"),
            )
        )

        outstanding_balance = money(
            money(invoice.total_amount) - already_paid
        )

        if outstanding_balance <= 0:
            raise HTTPException(
                status_code=400,
                detail="This invoice has no outstanding balance.",
            )

        if amount > outstanding_balance:
            raise HTTPException(
                status_code=400,
                detail=(
                    "Payment exceeds the outstanding invoice balance. "
                    f"Outstanding: {outstanding_balance}"
                ),
            )

        payment = CustomerPayment(
            invoice_id=invoice.id,
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
            description=(
                f"Customer payment for invoice {invoice.invoice_number}"
            ),
            reference=payload.reference or f"RECEIPT-{payment.id}",
            lines=[
                {
                    "account_id": payment_ledger_id,
                    "debit": amount,
                    "credit": 0,
                    "description": "Customer payment received",
                },
                {
                    "account_id": receivable.id,
                    "debit": 0,
                    "credit": amount,
                    "description": "Accounts receivable reduced",
                },
            ],
        )

        update_invoice_status(db, invoice)

        db.commit()
        db.refresh(payment)

        new_total_paid = money(already_paid + amount)
        new_outstanding = money(
            money(invoice.total_amount) - new_total_paid
        )

        return {
            "message": "Customer payment recorded successfully.",
            "payment": payment,
            "invoice_status": invoice.status,
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
            detail="Could not record customer payment.",
        )


@router.get("/payments")
def list_customer_payments(
    invoice_id: int | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
):
    query = db.query(CustomerPayment)

    if invoice_id is not None:
        query = query.filter(
            CustomerPayment.invoice_id == invoice_id
        )

    return (
        query.order_by(
            CustomerPayment.payment_date.desc(),
            CustomerPayment.id.desc(),
        )
        .limit(limit)
        .all()
    )


from datetime import date
from decimal import Decimal
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload

from backend.database import get_db
from backend.models import (
    Product,
    StockMovement,
    InventoryCount,
    InventoryCountLine,
)
from backend.schemas import (
    ProductCreate,
    ProductUpdate,
    StockAdjustmentCreate,
    InventoryCountCreate,
)
from backend.accounting import (
    get_account_by_code,
    initialize_standard_accounts,
    money,
    quantity,
)
from backend.ledger_posting import post_journal_entry


router = APIRouter(
    prefix="/api/inventory",
    tags=["Inventory"],
)


# ---------------------------------------------------------
# HELPER FUNCTIONS
# ---------------------------------------------------------

def get_required_account(db: Session, code: str):
    account = get_account_by_code(db, code)

    if account is None or not account.is_active:
        raise ValueError(
            f"Required ledger account {code} is missing or inactive."
        )

    return account


def get_product_or_404(
    db: Session,
    product_id: int,
    active_only: bool = False,
):
    query = db.query(Product).filter(Product.id == product_id)

    if active_only:
        query = query.filter(Product.is_active.is_(True))

    product = query.with_for_update().first()

    if product is None:
        raise HTTPException(
            status_code=404,
            detail="Product not found.",
        )

    return product


# ---------------------------------------------------------
# CREATE PRODUCT
# ---------------------------------------------------------

@router.post(
    "/products",
    status_code=status.HTTP_201_CREATED,
)
def create_product(
    payload: ProductCreate,
    db: Session = Depends(get_db),
):
    try:
        initialize_standard_accounts(db)

        sku = payload.sku.strip()
        name = payload.name.strip()
        unit = payload.unit.strip() or "piece"

        if not sku:
            raise HTTPException(
                status_code=400,
                detail="Product SKU is required.",
            )

        if not name:
            raise HTTPException(
                status_code=400,
                detail="Product name is required.",
            )

        if db.query(Product).filter(Product.sku == sku).first():
            raise HTTPException(
                status_code=409,
                detail="Product SKU already exists.",
            )

        purchase_price = money(payload.purchase_price)
        selling_price = money(payload.selling_price)
        opening_quantity = quantity(payload.opening_quantity or 0)

        if purchase_price < 0 or selling_price < 0:
            raise HTTPException(
                status_code=400,
                detail="Product prices cannot be negative.",
            )

        if opening_quantity < 0:
            raise HTTPException(
                status_code=400,
                detail="Opening stock cannot be negative.",
            )

        opening_value = money(opening_quantity * purchase_price)

        product = Product(
            sku=sku,
            name=name,
            description=(
                payload.description.strip()
                if payload.description
                else None
            ),
            unit=unit,
            purchase_price=purchase_price,
            selling_price=selling_price,
            current_stock=opening_quantity,
            average_cost=purchase_price,
            quantity_on_hand=opening_quantity,
            reorder_level=Decimal("0"),
            unit_cost=purchase_price,
            is_active=True,
        )

        db.add(product)
        db.flush()

        if opening_quantity > 0:
            inventory_account = get_required_account(db, "1200")
            opening_equity_account = get_required_account(db, "3010")

            reference = f"OPENING-STOCK-{product.id}"

            db.add(
                StockMovement(
                    product_id=product.id,
                    movement_date=date.today(),
                    movement_type="adjustment_in",
                    quantity=opening_quantity,
                    unit_cost=purchase_price,
                    reference=reference,
                    notes="Initial product stock",
                )
            )

            if opening_value > 0:
                post_journal_entry(
                    db,
                    entry_date=date.today(),
                    description=f"Opening stock for product {sku}",
                    reference=reference,
                    lines=[
                        {
                            "account_id": inventory_account.id,
                            "debit": opening_value,
                            "credit": 0,
                            "description": f"Opening stock: {sku}",
                        },
                        {
                            "account_id": opening_equity_account.id,
                            "debit": 0,
                            "credit": opening_value,
                            "description": f"Opening stock equity: {sku}",
                        },
                    ],
                )

        db.commit()
        db.refresh(product)

        return product

    except HTTPException:
        db.rollback()
        raise

    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc))

    except IntegrityError as exc:
        db.rollback()
        print("ACTUAL PRODUCT ERROR:", repr(exc.orig))
        raise HTTPException(
            status_code=409,
            detail=f"Database constraint error: {exc.orig}",
        )


# ---------------------------------------------------------
# EDIT PRODUCT
# ---------------------------------------------------------

@router.put("/products/{product_id}")
def update_product(
    product_id: int,
    payload: ProductUpdate,
    db: Session = Depends(get_db),
):
    try:
        product = get_product_or_404(db, product_id)

        updates = payload.model_dump(exclude_unset=True)

        if not updates:
            raise HTTPException(
                status_code=400,
                detail="No product information was provided.",
            )

        if "sku" in updates:
            if updates["sku"] is None:
                raise HTTPException(
                    status_code=400,
                    detail="Product SKU cannot be empty.",
                )

            sku = updates["sku"].strip()

            if not sku:
                raise HTTPException(
                    status_code=400,
                    detail="Product SKU cannot be empty.",
                )

            existing = (
                db.query(Product)
                .filter(
                    Product.sku == sku,
                    Product.id != product_id,
                )
                .first()
            )

            if existing:
                raise HTTPException(
                    status_code=409,
                    detail="Another product already uses this SKU.",
                )

            product.sku = sku

        if "name" in updates:
            if updates["name"] is None or not updates["name"].strip():
                raise HTTPException(
                    status_code=400,
                    detail="Product name cannot be empty.",
                )

            product.name = updates["name"].strip()

        if "description" in updates:
            product.description = (
                updates["description"].strip()
                if updates["description"]
                else None
            )

        if "unit" in updates:
            if updates["unit"] is None or not updates["unit"].strip():
                raise HTTPException(
                    status_code=400,
                    detail="Product unit cannot be empty.",
                )

            product.unit = updates["unit"].strip()

        if "purchase_price" in updates:
            if updates["purchase_price"] is None:
                raise HTTPException(
                    status_code=400,
                    detail="Purchase price cannot be empty.",
                )

            new_purchase_price = money(updates["purchase_price"])

            if new_purchase_price < 0:
                raise HTTPException(
                    status_code=400,
                    detail="Purchase price cannot be negative.",
                )

            product.purchase_price = new_purchase_price

            # Update the legacy cost field for future operations.
            # Do not rewrite the average cost of existing stock.
            product.unit_cost = new_purchase_price

        if "selling_price" in updates:
            if updates["selling_price"] is None:
                raise HTTPException(
                    status_code=400,
                    detail="Selling price cannot be empty.",
                )

            new_selling_price = money(updates["selling_price"])

            if new_selling_price < 0:
                raise HTTPException(
                    status_code=400,
                    detail="Selling price cannot be negative.",
                )

            product.selling_price = new_selling_price

        db.commit()
        db.refresh(product)

        return {
            "message": "Product updated successfully.",
            "product": product,
        }

    except HTTPException:
        db.rollback()
        raise

    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc))

    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="Could not update product. Check whether its SKU already exists.",
        )


# ---------------------------------------------------------
# LIST PRODUCTS
# ---------------------------------------------------------

@router.get("/products")
def list_products(
    search: str | None = None,
    active_only: bool = True,
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
):
    query = db.query(Product)

    if active_only:
        query = query.filter(Product.is_active.is_(True))

    if search:
        term = f"%{search.strip()}%"
        query = query.filter(
            (Product.name.ilike(term))
            | (Product.sku.ilike(term))
        )

    return (
        query.order_by(Product.name.asc())
        .limit(limit)
        .all()
    )


# ---------------------------------------------------------
# GET SINGLE PRODUCT
# ---------------------------------------------------------

@router.get("/products/{product_id}")
def get_product(
    product_id: int,
    db: Session = Depends(get_db),
):
    return get_product_or_404(db, product_id)


# ---------------------------------------------------------
# STOCK ADJUSTMENT: INCREASE / DECREASE
# ---------------------------------------------------------

@router.post(
    "/products/{product_id}/adjustments",
    status_code=status.HTTP_201_CREATED,
)
def adjust_product_stock(
    product_id: int,
    payload: StockAdjustmentCreate,
    db: Session = Depends(get_db),
):
    try:
        initialize_standard_accounts(db)

        product = get_product_or_404(
            db,
            product_id,
            active_only=True,
        )

        adjustment_quantity = quantity(payload.quantity)
        current_stock = quantity(product.current_stock or 0)

        if adjustment_quantity <= 0:
            raise HTTPException(
                status_code=400,
                detail="Adjustment quantity must be greater than zero.",
            )

        unit_cost = money(
            product.average_cost or product.purchase_price or 0
        )

        if unit_cost < 0:
            raise HTTPException(
                status_code=400,
                detail="Invalid product average cost.",
            )

        adjustment_value = money(
            adjustment_quantity * unit_cost
        )

        if payload.adjustment_type == "increase":
            new_stock = quantity(
                current_stock + adjustment_quantity
            )
            movement_type = "adjustment_in"

        elif payload.adjustment_type == "decrease":
            if adjustment_quantity > current_stock:
                raise HTTPException(
                    status_code=400,
                    detail=(
                        f"Insufficient stock. Available: "
                        f"{current_stock}, requested: {adjustment_quantity}."
                    ),
                )

            new_stock = quantity(
                current_stock - adjustment_quantity
            )
            movement_type = "adjustment_out"

        else:
            raise HTTPException(
                status_code=400,
                detail="Invalid stock adjustment type.",
            )

        unique_reference = (
            f"STOCK-ADJ-{product.id}-{uuid4().hex[:8].upper()}"
        )

        external_reference = (
            payload.reference.strip()
            if payload.reference and payload.reference.strip()
            else unique_reference
        )

        # Synchronize both stock fields.
        product.current_stock = new_stock
        product.quantity_on_hand = new_stock

        db.add(
            StockMovement(
                product_id=product.id,
                movement_date=payload.adjustment_date,
                movement_type=movement_type,
                quantity=adjustment_quantity,
                unit_cost=unit_cost,
                reference=external_reference,
                notes=payload.notes or "Manual stock adjustment",
            )
        )

        # Create accounting entries only when the adjustment
        # has a positive monetary value.
        if adjustment_value > 0:
            inventory_account = get_required_account(db, "1200")

            if payload.adjustment_type == "increase":
                other_income_account = get_required_account(db, "7000")

                journal_lines = [
                    {
                        "account_id": inventory_account.id,
                        "debit": adjustment_value,
                        "credit": 0,
                        "description": f"Stock increase: {product.sku}",
                    },
                    {
                        "account_id": other_income_account.id,
                        "debit": 0,
                        "credit": adjustment_value,
                        "description": f"Stock adjustment gain: {product.sku}",
                    },
                ]

            else:
                adjustment_expense_account = get_required_account(
                    db, "6010"
                )

                journal_lines = [
                    {
                        "account_id": adjustment_expense_account.id,
                        "debit": adjustment_value,
                        "credit": 0,
                        "description": f"Stock shortage: {product.sku}",
                    },
                    {
                        "account_id": inventory_account.id,
                        "debit": 0,
                        "credit": adjustment_value,
                        "description": f"Stock decrease: {product.sku}",
                    },
                ]

            post_journal_entry(
                db,
                entry_date=payload.adjustment_date,
                description=(
                    f"Stock {payload.adjustment_type} "
                    f"for {product.name}"
                ),
                reference=unique_reference,
                lines=journal_lines,
            )

        db.commit()
        db.refresh(product)

        return {
            "message": "Stock adjusted successfully.",
            "product_id": product.id,
            "sku": product.sku,
            "previous_stock": current_stock,
            "adjustment_type": payload.adjustment_type,
            "adjustment_quantity": adjustment_quantity,
            "new_stock": new_stock,
            "unit_cost": unit_cost,
            "adjustment_value": adjustment_value,
            "reference": external_reference,
        }

    except HTTPException:
        db.rollback()
        raise

    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc))

    except IntegrityError as exc:
        db.rollback()
        print("STOCK ADJUSTMENT ERROR:", repr(exc.orig))
        raise HTTPException(
            status_code=400,
            detail="Could not save stock adjustment.",
        )


# ---------------------------------------------------------
# PRODUCT STOCK MOVEMENT HISTORY
# ---------------------------------------------------------

@router.get("/products/{product_id}/movements")
def list_product_movements(
    product_id: int,
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
):
    get_product_or_404(db, product_id)

    return (
        db.query(StockMovement)
        .filter(StockMovement.product_id == product_id)
        .order_by(
            StockMovement.movement_date.desc(),
            StockMovement.id.desc(),
        )
        .limit(limit)
        .all()
    )


# ---------------------------------------------------------
# PHYSICAL INVENTORY COUNT
# ---------------------------------------------------------

@router.post(
    "/counts",
    status_code=status.HTTP_201_CREATED,
)
def create_inventory_count(
    payload: InventoryCountCreate,
    db: Session = Depends(get_db),
):
    try:
        initialize_standard_accounts(db)

        if not payload.lines:
            raise HTTPException(
                status_code=400,
                detail="Inventory count must contain at least one product.",
            )

        inventory_account = get_required_account(db, "1200")
        adjustment_expense_account = get_required_account(db, "6010")
        other_income_account = get_required_account(db, "7000")

        prepared_lines = []

        total_increase_value = Decimal("0.00")
        total_decrease_value = Decimal("0.00")

        seen_product_ids = set()

        for item in payload.lines:
            if item.product_id in seen_product_ids:
                raise HTTPException(
                    status_code=400,
                    detail=f"Duplicate product ID: {item.product_id}",
                )

            seen_product_ids.add(item.product_id)

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

            counted_quantity = quantity(item.counted_quantity)

            if counted_quantity < 0:
                raise HTTPException(
                    status_code=400,
                    detail="Counted stock cannot be negative.",
                )

            system_quantity = quantity(product.current_stock or 0)

            difference = quantity(
                counted_quantity - system_quantity
            )

            unit_cost = money(
                product.average_cost or product.purchase_price or 0
            )

            if unit_cost < 0:
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid stock cost for product {product.sku}.",
                )

            adjustment_value = money(
                abs(difference) * unit_cost
            )

            if difference > 0:
                total_increase_value += adjustment_value

            elif difference < 0:
                total_decrease_value += adjustment_value

            prepared_lines.append(
                {
                    "product": product,
                    "system_quantity": system_quantity,
                    "counted_quantity": counted_quantity,
                    "difference": difference,
                    "unit_cost": unit_cost,
                    "adjustment_value": adjustment_value,
                }
            )

        total_increase_value = money(total_increase_value)
        total_decrease_value = money(total_decrease_value)

        inventory_count = InventoryCount(
            count_date=payload.count_date,
            notes=payload.notes,
            status="posted",
        )

        db.add(inventory_count)
        db.flush()

        for line in prepared_lines:
            product = line["product"]
            difference = line["difference"]

            # Synchronize stock fields.
            product.current_stock = line["counted_quantity"]
            product.quantity_on_hand = line["counted_quantity"]

            db.add(
                InventoryCountLine(
                    inventory_count_id=inventory_count.id,
                    product_id=product.id,
                    system_quantity=line["system_quantity"],
                    counted_quantity=line["counted_quantity"],
                )
            )

            if difference != 0:
                movement_type = (
                    "adjustment_in"
                    if difference > 0
                    else "adjustment_out"
                )

                db.add(
                    StockMovement(
                        product_id=product.id,
                        movement_date=payload.count_date,
                        movement_type=movement_type,
                        quantity=abs(difference),
                        unit_cost=line["unit_cost"],
                        reference=f"COUNT-{inventory_count.id}",
                        notes=(
                            payload.notes
                            or "Inventory physical count adjustment"
                        ),
                    )
                )

        db.flush()

        # Stock increase: Inventory Dr / Other Income Cr
        if total_increase_value > 0:
            post_journal_entry(
                db,
                entry_date=payload.count_date,
                description=(
                    f"Inventory count increase #{inventory_count.id}"
                ),
                reference=f"COUNT-IN-{inventory_count.id}",
                lines=[
                    {
                        "account_id": inventory_account.id,
                        "debit": total_increase_value,
                        "credit": 0,
                        "description": "Inventory stock increase",
                    },
                    {
                        "account_id": other_income_account.id,
                        "debit": 0,
                        "credit": total_increase_value,
                        "description": "Inventory adjustment gain",
                    },
                ],
            )

        # Stock decrease: Adjustment Expense Dr / Inventory Cr
        if total_decrease_value > 0:
            post_journal_entry(
                db,
                entry_date=payload.count_date,
                description=(
                    f"Inventory count decrease #{inventory_count.id}"
                ),
                reference=f"COUNT-OUT-{inventory_count.id}",
                lines=[
                    {
                        "account_id": adjustment_expense_account.id,
                        "debit": total_decrease_value,
                        "credit": 0,
                        "description": "Inventory shortage expense",
                    },
                    {
                        "account_id": inventory_account.id,
                        "debit": 0,
                        "credit": total_decrease_value,
                        "description": "Inventory stock decrease",
                    },
                ],
            )

        db.commit()

        saved_count = (
            db.query(InventoryCount)
            .options(joinedload(InventoryCount.lines))
            .filter(InventoryCount.id == inventory_count.id)
            .first()
        )

        return {
            "message": "Inventory count recorded successfully.",
            "inventory_count": saved_count,
            "total_increase_value": total_increase_value,
            "total_decrease_value": total_decrease_value,
        }

    except HTTPException:
        db.rollback()
        raise

    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc))

    except IntegrityError as exc:
        db.rollback()
        print("INVENTORY COUNT ERROR:", repr(exc.orig))
        raise HTTPException(
            status_code=400,
            detail="Could not save inventory count. Check the submitted records.",
        )


# ---------------------------------------------------------
# LIST INVENTORY COUNTS
# ---------------------------------------------------------

@router.get("/counts")
def list_inventory_counts(
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
):
    return (
        db.query(InventoryCount)
        .options(joinedload(InventoryCount.lines))
        .order_by(
            InventoryCount.count_date.desc(),
            InventoryCount.id.desc(),
        )
        .limit(limit)
        .all()
    )


# ---------------------------------------------------------
# GET SINGLE INVENTORY COUNT
# ---------------------------------------------------------

@router.get("/counts/{count_id}")
def get_inventory_count(
    count_id: int,
    db: Session = Depends(get_db),
):
    inventory_count = (
        db.query(InventoryCount)
        .options(joinedload(InventoryCount.lines))
        .filter(InventoryCount.id == count_id)
        .first()
    )

    if inventory_count is None:
        raise HTTPException(
            status_code=404,
            detail="Inventory count not found.",
        )

    return inventory_count

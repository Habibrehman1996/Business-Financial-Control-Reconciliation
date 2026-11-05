
from datetime import date
from decimal import Decimal

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
from backend.schemas import ProductCreate, InventoryCountCreate
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


def get_required_account(db: Session, code: str):
    account = get_account_by_code(db, code)

    if account is None or not account.is_active:
        raise ValueError(
            f"Required ledger account {code} is missing or inactive."
        )

    return account


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

        if not sku:
            raise HTTPException(
                status_code=400,
                detail="Product SKU is required.",
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
            name=payload.name.strip(),
            description=payload.description,
            unit=payload.unit,
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

            db.add(
                StockMovement(
                    product_id=product.id,
                    movement_date=date.today(),
                    movement_type="adjustment_in",
                    quantity=opening_quantity,
                    unit_cost=purchase_price,
                    reference=f"OPENING-STOCK-{product.id}",
                    notes="Initial product stock",
                )
            )

            if opening_value > 0:
                post_journal_entry(
                    db,
                    entry_date=date.today(),
                    description=f"Opening stock for product {sku}",
                    reference=f"OPENING-STOCK-{product.id}",
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


@router.get("/products/{product_id}")
def get_product(
    product_id: int,
    db: Session = Depends(get_db),
):
    product = (
        db.query(Product)
        .filter(Product.id == product_id)
        .first()
    )

    if product is None:
        raise HTTPException(
            status_code=404,
            detail="Product not found.",
        )

    return product


@router.get("/products/{product_id}/movements")
def list_product_movements(
    product_id: int,
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
):
    product = (
        db.query(Product)
        .filter(Product.id == product_id)
        .first()
    )

    if product is None:
        raise HTTPException(
            status_code=404,
            detail="Product not found.",
        )

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

        if not payload.items:
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

        for item in payload.items:
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

            system_quantity = quantity(product.current_stock)
            difference = quantity(counted_quantity - system_quantity)

            unit_cost = money(
                product.average_cost or product.purchase_price
            )

            if unit_cost < 0:
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid stock cost for product {product.sku}.",
                )

            adjustment_value = money(abs(difference) * unit_cost)

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

            product.current_stock = line["counted_quantity"]

            # Model fields are limited to system_quantity and counted_quantity.
            db.add(
                InventoryCountLine(
                    inventory_count_id=inventory_count.id,
                    product_id=product.id,
                    system_quantity=line["system_quantity"],
                    counted_quantity=line["counted_quantity"],
                )
            )

            if difference != 0:
                db.add(
                    StockMovement(
                        product_id=product.id,
                        movement_date=payload.count_date,
                        movement_type="adjustment",
                        quantity=difference,
                        unit_cost=line["unit_cost"],
                        reference=f"COUNT-{inventory_count.id}",
                        notes="Inventory physical count adjustment",
                    )
                )

        db.flush()

        if total_increase_value > 0:
            post_journal_entry(
                db,
                entry_date=payload.count_date,
                description=f"Inventory count increase #{inventory_count.id}",
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

        if total_decrease_value > 0:
            post_journal_entry(
                db,
                entry_date=payload.count_date,
                description=f"Inventory count decrease #{inventory_count.id}",
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

    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=400,
            detail="Could not save inventory count. Check the submitted records.",
        )


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

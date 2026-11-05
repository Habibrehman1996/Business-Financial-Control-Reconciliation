
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.accounting import initialize_standard_accounts
from backend.database import SessionLocal
from backend.models import Customer, Product, Supplier


def seed_demo_data(db: Session) -> dict:
    """
    Add basic demo records without duplicating existing data.
    Does not create fake sales, payments, or journal entries.
    """

    initialize_standard_accounts(db)

    created = {
        "customers": 0,
        "suppliers": 0,
        "products": 0,
    }

    customer_names = [
        "ABC Retail Store",
        "City General Store",
        "Al Madina Traders",
    ]

    for name in customer_names:
        existing = db.scalar(
            select(Customer).where(Customer.name == name)
        )

        if existing is None:
            db.add(
                Customer(
                    name=name,
                    phone=None,
                    email=None,
                    address=None,
                    opening_balance=Decimal("0.00"),
                    is_active=True,
                )
            )
            created["customers"] += 1

    supplier_names = [
        "Pakistan Wholesale Traders",
        "National Distributors",
    ]

    for name in supplier_names:
        existing = db.scalar(
            select(Supplier).where(Supplier.name == name)
        )

        if existing is None:
            db.add(
                Supplier(
                    name=name,
                    phone=None,
                    email=None,
                    address=None,
                    opening_balance=Decimal("0.00"),
                    is_active=True,
                )
            )
            created["suppliers"] += 1

    demo_products = [
        {
            "sku": "DEMO-001",
            "name": "Notebook",
            "description": "Demo stationery product",
            "unit": "piece",
            "purchase_price": Decimal("80.00"),
            "selling_price": Decimal("120.00"),
        },
        {
            "sku": "DEMO-002",
            "name": "Ball Pen",
            "description": "Demo stationery product",
            "unit": "piece",
            "purchase_price": Decimal("20.00"),
            "selling_price": Decimal("35.00"),
        },
        {
            "sku": "DEMO-003",
            "name": "A4 Paper Pack",
            "description": "Demo office paper pack",
            "unit": "pack",
            "purchase_price": Decimal("450.00"),
            "selling_price": Decimal("550.00"),
        },
    ]

    for item in demo_products:
        existing = db.scalar(
            select(Product).where(Product.sku == item["sku"])
        )

        if existing is None:
            db.add(
                Product(
                    **item,
                    current_stock=Decimal("0.000"),
                    average_cost=item["purchase_price"],
                    is_active=True,
                )
            )
            created["products"] += 1

    db.commit()

    return {
        "success": True,
        "created": created,
        "message": "Demo master data initialized.",
    }


def main():
    db = SessionLocal()

    try:
        result = seed_demo_data(db)
        print(result)
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()

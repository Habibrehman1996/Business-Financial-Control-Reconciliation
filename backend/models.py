
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.database import Base


MONEY = Numeric(14, 2)
QUANTITY = Numeric(14, 3)


class Account(Base):
    __tablename__ = "accounts"

    id: Mapped[int] = mapped_column(
        Integer, primary_key=True, index=True
    )
    code: Mapped[str] = mapped_column(
        String(20), unique=True, nullable=False
    )
    name: Mapped[str] = mapped_column(
        String(120), nullable=False
    )
    account_type: Mapped[str] = mapped_column(
        String(20), nullable=False
    )
    parent_id: Mapped[int | None] = mapped_column(
        ForeignKey("accounts.id"), nullable=True
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, nullable=False
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )

    parent = relationship(
        "Account",
        remote_side=[id],
        backref="children",
    )


class JournalEntry(Base):
    __tablename__ = "journal_entries"

    id: Mapped[int] = mapped_column(
        Integer, primary_key=True, index=True
    )
    entry_number: Mapped[str] = mapped_column(
        String(40), unique=True, nullable=False
    )
    entry_date: Mapped[date] = mapped_column(
        Date, default=date.today, nullable=False
    )
    description: Mapped[str] = mapped_column(
        String(255), nullable=False
    )
    reference: Mapped[str | None] = mapped_column(
        String(100), nullable=True
    )
    status: Mapped[str] = mapped_column(
        String(20), default="posted", nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )

    lines = relationship(
        "JournalLine",
        back_populates="journal_entry",
        cascade="all, delete-orphan",
    )


class JournalLine(Base):
    __tablename__ = "journal_lines"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    journal_entry_id: Mapped[int] = mapped_column(
        ForeignKey("journal_entries.id"), nullable=False
    )
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id"), nullable=False)
    debit: Mapped[Decimal] = mapped_column(MONEY, default=Decimal("0.00"))
    credit: Mapped[Decimal] = mapped_column(MONEY, default=Decimal("0.00"))
    description: Mapped[str | None] = mapped_column(String(255), nullable=True)

    journal_entry = relationship("JournalEntry", back_populates="lines")
    account = relationship("Account")


class BankAccount(Base):
    __tablename__ = "bank_accounts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    bank_name: Mapped[str] = mapped_column(String(100), nullable=False)
    account_number: Mapped[str] = mapped_column(String(50), nullable=False)
    ledger_account_id: Mapped[int] = mapped_column(
        ForeignKey("accounts.id"), nullable=False
    )
    opening_balance: Mapped[Decimal] = mapped_column(MONEY, default=Decimal("0.00"))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    ledger_account = relationship("Account")
    transactions = relationship(
        "BankTransaction",
        back_populates="bank_account",
        cascade="all, delete-orphan",
    )


class BankTransaction(Base):
    __tablename__ = "bank_transactions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    bank_account_id: Mapped[int] = mapped_column(
        ForeignKey("bank_accounts.id"), nullable=False
    )
    transaction_date: Mapped[date] = mapped_column(Date, nullable=False)
    description: Mapped[str] = mapped_column(String(255), nullable=False)
    reference: Mapped[str | None] = mapped_column(String(100), nullable=True)
    amount: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    direction: Mapped[str] = mapped_column(String(10), nullable=False)
    source: Mapped[str] = mapped_column(String(20), default="book", nullable=False)
    is_reconciled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )

    bank_account = relationship("BankAccount", back_populates="transactions")


class CashAccount(Base):
    __tablename__ = "cash_accounts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    ledger_account_id: Mapped[int] = mapped_column(
        ForeignKey("accounts.id"), nullable=False
    )
    opening_balance: Mapped[Decimal] = mapped_column(MONEY, default=Decimal("0.00"))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    ledger_account = relationship("Account")
    transactions = relationship(
        "CashTransaction",
        back_populates="cash_account",
        cascade="all, delete-orphan",
    )


class CashTransaction(Base):
    __tablename__ = "cash_transactions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    cash_account_id: Mapped[int] = mapped_column(
        ForeignKey("cash_accounts.id"), nullable=False
    )
    transaction_date: Mapped[date] = mapped_column(Date, nullable=False)
    description: Mapped[str] = mapped_column(String(255), nullable=False)
    amount: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    direction: Mapped[str] = mapped_column(String(10), nullable=False)
    reference: Mapped[str | None] = mapped_column(String(100), nullable=True)
    is_reconciled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    cash_account = relationship("CashAccount", back_populates="transactions")


class Customer(Base):
    __tablename__ = "customers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    phone: Mapped[str | None] = mapped_column(String(30), nullable=True)
    email: Mapped[str | None] = mapped_column(String(120), nullable=True)
    address: Mapped[str | None] = mapped_column(Text, nullable=True)
    opening_balance: Mapped[Decimal] = mapped_column(
        MONEY, default=Decimal("0.00")
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )


class Supplier(Base):
    __tablename__ = "suppliers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    phone: Mapped[str | None] = mapped_column(String(30), nullable=True)
    email: Mapped[str | None] = mapped_column(String(120), nullable=True)
    address: Mapped[str | None] = mapped_column(Text, nullable=True)
    opening_balance: Mapped[Decimal] = mapped_column(MONEY, default=Decimal("0.00"))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )


class Product(Base):
    __tablename__ = "products"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    sku: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    unit: Mapped[str] = mapped_column(String(20), default="piece", nullable=False)

    purchase_price: Mapped[Decimal] = mapped_column(
        MONEY, default=Decimal("0.00")
    )
    selling_price: Mapped[Decimal] = mapped_column(
        MONEY, default=Decimal("0.00")
    )
    current_stock: Mapped[Decimal] = mapped_column(
        QUANTITY, default=Decimal("0")
    )
    average_cost: Mapped[Decimal] = mapped_column(
        MONEY, default=Decimal("0.00")
    )

    # Existing database compatibility
    quantity_on_hand: Mapped[Decimal] = mapped_column(
        QUANTITY, default=Decimal("0"), nullable=False
    )
    reorder_level: Mapped[Decimal] = mapped_column(
        QUANTITY, default=Decimal("0"), nullable=False
    )
    unit_cost: Mapped[Decimal] = mapped_column(
        MONEY, default=Decimal("0.00"), nullable=False
    )

    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, nullable=False
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )


class SalesInvoice(Base):
    __tablename__ = "sales_invoices"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    invoice_number: Mapped[str] = mapped_column(String(40), unique=True, nullable=False)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id"), nullable=False)
    invoice_date: Mapped[date] = mapped_column(Date, default=date.today, nullable=False)
    due_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    subtotal: Mapped[Decimal] = mapped_column(MONEY, default=Decimal("0.00"))
    tax_amount: Mapped[Decimal] = mapped_column(MONEY, default=Decimal("0.00"))
    total_amount: Mapped[Decimal] = mapped_column(MONEY, default=Decimal("0.00"))
    status: Mapped[str] = mapped_column(String(20), default="posted", nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )

    customer = relationship("Customer")
    items = relationship(
        "SalesInvoiceItem",
        back_populates="invoice",
        cascade="all, delete-orphan",
    )
    payments = relationship(
        "CustomerPayment",
        back_populates="invoice",
        cascade="all, delete-orphan",
    )


class SalesInvoiceItem(Base):
    __tablename__ = "sales_invoice_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    invoice_id: Mapped[int] = mapped_column(
        ForeignKey("sales_invoices.id"), nullable=False
    )
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), nullable=False)
    quantity: Mapped[Decimal] = mapped_column(QUANTITY, nullable=False)
    unit_price: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    unit_cost: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    line_total: Mapped[Decimal] = mapped_column(MONEY, nullable=False)

    invoice = relationship("SalesInvoice", back_populates="items")
    product = relationship("Product")


class CustomerPayment(Base):
    __tablename__ = "customer_payments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    invoice_id: Mapped[int] = mapped_column(
        ForeignKey("sales_invoices.id"), nullable=False
    )
    payment_date: Mapped[date] = mapped_column(Date, default=date.today, nullable=False)
    amount: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    payment_method: Mapped[str] = mapped_column(String(20), nullable=False)
    bank_account_id: Mapped[int | None] = mapped_column(
        ForeignKey("bank_accounts.id"), nullable=True
    )
    cash_account_id: Mapped[int | None] = mapped_column(
        ForeignKey("cash_accounts.id"), nullable=True
    )
    reference: Mapped[str | None] = mapped_column(String(100), nullable=True)

    invoice = relationship("SalesInvoice", back_populates="payments")


class PurchaseBill(Base):
    __tablename__ = "purchase_bills"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    bill_number: Mapped[str] = mapped_column(String(40), unique=True, nullable=False)
    supplier_id: Mapped[int] = mapped_column(ForeignKey("suppliers.id"), nullable=False)
    bill_date: Mapped[date] = mapped_column(Date, default=date.today, nullable=False)
    due_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    subtotal: Mapped[Decimal] = mapped_column(MONEY, default=Decimal("0.00"))
    tax_amount: Mapped[Decimal] = mapped_column(MONEY, default=Decimal("0.00"))
    total_amount: Mapped[Decimal] = mapped_column(MONEY, default=Decimal("0.00"))
    status: Mapped[str] = mapped_column(String(20), default="posted", nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    supplier = relationship("Supplier")
    items = relationship(
        "PurchaseBillItem",
        back_populates="bill",
        cascade="all, delete-orphan",
    )
    payments = relationship(
        "SupplierPayment",
        back_populates="bill",
        cascade="all, delete-orphan",
    )


class PurchaseBillItem(Base):
    __tablename__ = "purchase_bill_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    bill_id: Mapped[int] = mapped_column(ForeignKey("purchase_bills.id"), nullable=False)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), nullable=False)
    quantity: Mapped[Decimal] = mapped_column(QUANTITY, nullable=False)
    unit_cost: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    line_total: Mapped[Decimal] = mapped_column(MONEY, nullable=False)

    bill = relationship("PurchaseBill", back_populates="items")
    product = relationship("Product")


class SupplierPayment(Base):
    __tablename__ = "supplier_payments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    bill_id: Mapped[int] = mapped_column(
        ForeignKey("purchase_bills.id"), nullable=False
    )
    payment_date: Mapped[date] = mapped_column(Date, default=date.today, nullable=False)
    amount: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    payment_method: Mapped[str] = mapped_column(String(20), nullable=False)
    bank_account_id: Mapped[int | None] = mapped_column(
        ForeignKey("bank_accounts.id"), nullable=True
    )
    cash_account_id: Mapped[int | None] = mapped_column(
        ForeignKey("cash_accounts.id"), nullable=True
    )
    reference: Mapped[str | None] = mapped_column(String(100), nullable=True)

    bill = relationship("PurchaseBill", back_populates="payments")


class StockMovement(Base):
    __tablename__ = "stock_movements"

    id: Mapped[int] = mapped_column(
        Integer, primary_key=True, index=True
    )
    product_id: Mapped[int] = mapped_column(
        ForeignKey("products.id"), nullable=False
    )
    movement_date: Mapped[date] = mapped_column(
        Date, default=date.today, nullable=False
    )
    movement_type: Mapped[str] = mapped_column(
        String(30), nullable=False
    )
    quantity: Mapped[Decimal] = mapped_column(
        QUANTITY, nullable=False
    )
    unit_cost: Mapped[Decimal] = mapped_column(
        MONEY, default=Decimal("0.00"), nullable=False
    )
    reference: Mapped[str | None] = mapped_column(
        String(100), nullable=True
    )
    notes: Mapped[str | None] = mapped_column(
        Text, nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )

    product = relationship("Product")


class InventoryCount(Base):
    __tablename__ = "inventory_counts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    count_date: Mapped[date] = mapped_column(Date, default=date.today, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="draft", nullable=False)

    lines = relationship(
        "InventoryCountLine",
        back_populates="inventory_count",
        cascade="all, delete-orphan",
    )


class InventoryCountLine(Base):
    __tablename__ = "inventory_count_lines"
    __table_args__ = (
        UniqueConstraint("inventory_count_id", "product_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    inventory_count_id: Mapped[int] = mapped_column(
        ForeignKey("inventory_counts.id"), nullable=False
    )
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), nullable=False)
    system_quantity: Mapped[Decimal] = mapped_column(QUANTITY, nullable=False)
    counted_quantity: Mapped[Decimal] = mapped_column(QUANTITY, nullable=False)

    inventory_count = relationship("InventoryCount", back_populates="lines")
    product = relationship("Product")


class Expense(Base):
    __tablename__ = "expenses"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    expense_number: Mapped[str] = mapped_column(String(40), unique=True, nullable=False)
    expense_date: Mapped[date] = mapped_column(Date, default=date.today, nullable=False)
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id"), nullable=False)
    description: Mapped[str] = mapped_column(String(255), nullable=False)
    amount: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    payment_method: Mapped[str] = mapped_column(String(20), nullable=False)
    bank_account_id: Mapped[int | None] = mapped_column(
        ForeignKey("bank_accounts.id"), nullable=True
    )
    cash_account_id: Mapped[int | None] = mapped_column(
        ForeignKey("cash_accounts.id"), nullable=True
    )
    reference: Mapped[str | None] = mapped_column(String(100), nullable=True)

    expense_account = relationship("Account")


class ReconciliationRun(Base):
    __tablename__ = "reconciliation_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    account_type: Mapped[str] = mapped_column(String(20), nullable=False)
    account_id: Mapped[int] = mapped_column(Integer, nullable=False)
    statement_date: Mapped[date] = mapped_column(Date, nullable=False)
    statement_closing_balance: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    book_closing_balance: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    difference: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    action: Mapped[str] = mapped_column(String(50), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(50), nullable=False)
    entity_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    details: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )

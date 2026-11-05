
from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


ZERO = Decimal("0.00")


class ORMBase(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class MessageResponse(BaseModel):
    message: str


# ACCOUNTS

class AccountCreate(BaseModel):
    code: str = Field(min_length=1, max_length=20)
    name: str = Field(min_length=2, max_length=120)
    account_type: Literal[
        "asset", "liability", "equity", "revenue", "expense"
    ]
    parent_id: int | None = None


class AccountRead(ORMBase):
    id: int
    code: str
    name: str
    account_type: str
    parent_id: int | None
    is_active: bool


# JOURNAL

class JournalLineInput(BaseModel):
    account_id: int = Field(gt=0)
    debit: Decimal = Field(default=ZERO, ge=0)
    credit: Decimal = Field(default=ZERO, ge=0)
    description: str | None = None

    @model_validator(mode="after")
    def validate_one_side(self):
        if (self.debit > 0) == (self.credit > 0):
            raise ValueError(
                "Har journal line mein debit ya credit mein se sirf ek amount ho."
            )
        return self


class JournalEntryCreate(BaseModel):
    entry_date: date
    description: str = Field(min_length=2, max_length=255)
    reference: str | None = None
    lines: list[JournalLineInput] = Field(min_length=2)

    @model_validator(mode="after")
    def validate_balanced_entry(self):
        total_debit = sum(
            (line.debit for line in self.lines), ZERO
        )
        total_credit = sum(
            (line.credit for line in self.lines), ZERO
        )

        if total_debit != total_credit:
            raise ValueError(
                "Journal entry ka total debit aur credit barabar hona chahiye."
            )

        return self


class JournalLineRead(ORMBase):
    id: int
    account_id: int
    debit: Decimal
    credit: Decimal
    description: str | None


class JournalEntryRead(ORMBase):
    id: int
    entry_number: str
    entry_date: date
    description: str
    reference: str | None
    status: str
    lines: list[JournalLineRead]


# BANK

class BankAccountCreate(BaseModel):
    name: str = Field(min_length=2, max_length=100)
    bank_name: str = Field(min_length=2, max_length=100)
    account_number: str = Field(min_length=3, max_length=50)
    opening_balance: Decimal = Field(default=ZERO, ge=0)


class BankAccountRead(ORMBase):
    id: int
    name: str
    bank_name: str
    account_number: str
    ledger_account_id: int
    opening_balance: Decimal
    is_active: bool


class BankTransactionCreate(BaseModel):
    bank_account_id: int = Field(gt=0)
    transaction_date: date
    description: str = Field(min_length=2, max_length=255)
    reference: str | None = None
    amount: Decimal = Field(gt=0)
    direction: Literal["in", "out"]

    # Money received/paid ka opposite ledger account.
    # Example: Sales Revenue, Rent Expense, Accounts Receivable.
    counter_account_id: int = Field(gt=0)


class BankTransactionRead(ORMBase):
    id: int
    bank_account_id: int
    transaction_date: date
    description: str
    reference: str | None
    amount: Decimal
    direction: str
    source: str
    is_reconciled: bool


# CASH

class CashAccountCreate(BaseModel):
    name: str = Field(min_length=2, max_length=100)
    opening_balance: Decimal = Field(default=ZERO, ge=0)


class CashAccountRead(ORMBase):
    id: int
    name: str
    ledger_account_id: int
    opening_balance: Decimal
    is_active: bool


class CashTransactionCreate(BaseModel):
    cash_account_id: int = Field(gt=0)
    transaction_date: date
    description: str = Field(min_length=2, max_length=255)
    amount: Decimal = Field(gt=0)
    direction: Literal["in", "out"]
    reference: str | None = None
    counter_account_id: int = Field(gt=0)


class CashTransactionRead(ORMBase):
    id: int
    cash_account_id: int
    transaction_date: date
    description: str
    amount: Decimal
    direction: str
    reference: str | None
    is_reconciled: bool


# CUSTOMERS AND SUPPLIERS

class PartyCreate(BaseModel):
    name: str = Field(min_length=2, max_length=150)
    phone: str | None = None
    email: str | None = None
    address: str | None = None
    opening_balance: Decimal = ZERO


class CustomerRead(ORMBase):
    id: int
    name: str
    phone: str | None
    email: str | None
    address: str | None
    opening_balance: Decimal
    is_active: bool


class SupplierRead(ORMBase):
    id: int
    name: str
    phone: str | None
    email: str | None
    address: str | None
    opening_balance: Decimal
    is_active: bool


# INVENTORY / PRODUCTS

class ProductCreate(BaseModel):
    sku: str = Field(min_length=1, max_length=50)
    name: str = Field(min_length=2, max_length=150)
    description: str | None = None
    unit: str = "piece"
    purchase_price: Decimal = Field(default=ZERO, ge=0)
    selling_price: Decimal = Field(default=ZERO, ge=0)
    opening_quantity: Decimal = Field(default=Decimal("0.000"), ge=0)

class ProductUpdate(BaseModel):
    sku: str | None = Field(default=None, min_length=1, max_length=50)
    name: str | None = Field(default=None, min_length=2, max_length=150)
    description: str | None = None
    unit: str | None = Field(default=None, min_length=1, max_length=20)
    purchase_price: Decimal | None = Field(default=None, ge=0)
    selling_price: Decimal | None = Field(default=None, ge=0)


class StockAdjustmentCreate(BaseModel):
    adjustment_date: date
    adjustment_type: Literal["increase", "decrease"]
    quantity: Decimal = Field(gt=0)
    reference: str | None = Field(default=None, max_length=100)
    notes: str | None = None


class ProductRead(ORMBase):
    id: int
    sku: str
    name: str
    description: str | None
    unit: str
    purchase_price: Decimal
    selling_price: Decimal
    current_stock: Decimal
    average_cost: Decimal
    is_active: bool


class InventoryCountLineInput(BaseModel):
    product_id: int = Field(gt=0)
    counted_quantity: Decimal = Field(ge=0)


class InventoryCountCreate(BaseModel):
    count_date: date
    notes: str | None = None
    lines: list[InventoryCountLineInput] = Field(min_length=1)


# SALES

class InvoiceItemInput(BaseModel):
    product_id: int = Field(gt=0)
    quantity: Decimal = Field(gt=0)
    unit_price: Decimal = Field(ge=0)


class SalesInvoiceCreate(BaseModel):
    invoice_number: str = Field(min_length=1, max_length=40)
    customer_id: int = Field(gt=0)
    invoice_date: date
    due_date: date | None = None
    tax_amount: Decimal = Field(default=ZERO, ge=0)
    notes: str | None = None
    items: list[InvoiceItemInput] = Field(min_length=1)


class CustomerPaymentCreate(BaseModel):
    invoice_id: int = Field(gt=0)
    payment_date: date
    amount: Decimal = Field(gt=0)
    payment_method: Literal["cash", "bank"]
    bank_account_id: int | None = None
    cash_account_id: int | None = None
    reference: str | None = None

    @model_validator(mode="after")
    def validate_payment_account(self):
        if self.payment_method == "cash":
            if self.cash_account_id is None or self.bank_account_id is not None:
                raise ValueError(
                    "Cash payment ke liye sirf cash_account_id dein."
                )
        else:
            if self.bank_account_id is None or self.cash_account_id is not None:
                raise ValueError(
                    "Bank payment ke liye sirf bank_account_id dein."
                )
        return self


# PURCHASES

class PurchaseItemInput(BaseModel):
    product_id: int = Field(gt=0)
    quantity: Decimal = Field(gt=0)
    unit_cost: Decimal = Field(ge=0)


class PurchaseBillCreate(BaseModel):
    bill_number: str = Field(min_length=1, max_length=40)
    supplier_id: int = Field(gt=0)
    bill_date: date
    due_date: date | None = None
    tax_amount: Decimal = Field(default=ZERO, ge=0)
    notes: str | None = None
    items: list[PurchaseItemInput] = Field(min_length=1)


class SupplierPaymentCreate(BaseModel):
    bill_id: int = Field(gt=0)
    payment_date: date
    amount: Decimal = Field(gt=0)
    payment_method: Literal["cash", "bank"]
    bank_account_id: int | None = None
    cash_account_id: int | None = None
    reference: str | None = None

    @model_validator(mode="after")
    def validate_payment_account(self):
        if self.payment_method == "cash":
            if self.cash_account_id is None or self.bank_account_id is not None:
                raise ValueError(
                    "Cash payment ke liye sirf cash_account_id dein."
                )
        else:
            if self.bank_account_id is None or self.cash_account_id is not None:
                raise ValueError(
                    "Bank payment ke liye sirf bank_account_id dein."
                )
        return self


# EXPENSES

class ExpenseCreate(BaseModel):
    expense_number: str = Field(min_length=1, max_length=40)
    expense_date: date
    account_id: int = Field(gt=0)
    description: str = Field(min_length=2, max_length=255)
    amount: Decimal = Field(gt=0)
    payment_method: Literal["cash", "bank"]
    bank_account_id: int | None = None
    cash_account_id: int | None = None
    reference: str | None = None

    @model_validator(mode="after")
    def validate_payment_account(self):
        if self.payment_method == "cash":
            if self.cash_account_id is None or self.bank_account_id is not None:
                raise ValueError(
                    "Cash expense ke liye sirf cash_account_id dein."
                )
        else:
            if self.bank_account_id is None or self.cash_account_id is not None:
                raise ValueError(
                    "Bank expense ke liye sirf bank_account_id dein."
                )
        return self


# RECONCILIATION

class ReconciliationCreate(BaseModel):
    account_type: Literal["bank", "cash"]
    account_id: int = Field(gt=0)
    statement_date: date
    statement_closing_balance: Decimal
    notes: str | None = None


class ReconciliationRead(ORMBase):
    id: int
    account_type: str
    account_id: int
    statement_date: date
    statement_closing_balance: Decimal
    book_closing_balance: Decimal
    difference: Decimal
    status: str
    notes: str | None

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from backend.database import get_db

from backend.models import (
    Account,
    BankAccount,
    CashAccount,
    ReconciliationRun,
    SmartReconciliation as SmartReconciliationModel,
    SmartReconciliationAdjustment as SmartReconciliationAdjustmentModel,
)

from backend.schemas import (
    ReconciliationCreate,
    SmartReconciliationCreate,
    SmartReconciliationPreview,
    SmartReconciliationRead,
)

from backend.accounting import get_account_balance, money
from backend.ledger_posting import post_journal_entry

from backend.services.smart_reconciliation import (
    calculate_smart_reconciliation,
)


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


@router.post(
    "/smart/preview",
    response_model=SmartReconciliationPreview,
)
def preview_smart_reconciliation(
    payload: SmartReconciliationCreate,
    db: Session = Depends(get_db),
):
    bank_account = (
        db.query(BankAccount)
        .filter(
            BankAccount.id == payload.account_id,
            BankAccount.is_active.is_(True),
        )
        .first()
    )

    if bank_account is None:
        raise HTTPException(
            status_code=404,
            detail="Bank account not found or inactive.",
        )

    ledger_account = (
        db.query(Account)
        .filter(
            Account.id == bank_account.ledger_account_id,
            Account.is_active.is_(True),
            Account.account_type == "asset",
        )
        .first()
    )

    if ledger_account is None:
        raise HTTPException(
            status_code=400,
            detail="The bank account must have an active asset ledger account.",
        )

    try:
        return calculate_smart_reconciliation(payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post(
    "/smart",
    response_model=SmartReconciliationRead,
    status_code=status.HTTP_201_CREATED,
)
def create_smart_reconciliation(
    payload: SmartReconciliationCreate,
    db: Session = Depends(get_db),
):
    bank_account = (
        db.query(BankAccount)
        .filter(
            BankAccount.id == payload.account_id,
            BankAccount.is_active.is_(True),
        )
        .first()
    )

    if bank_account is None:
        raise HTTPException(
            status_code=404,
            detail="Bank account not found or inactive.",
        )

    ledger_account = (
        db.query(Account)
        .filter(
            Account.id == bank_account.ledger_account_id,
            Account.is_active.is_(True),
            Account.account_type == "asset",
        )
        .first()
    )

    if ledger_account is None:
        raise HTTPException(
            status_code=400,
            detail="The bank account must have an active asset ledger account.",
        )

    try:
        preview = calculate_smart_reconciliation(payload)

        adjustment_rows = []

        for adjustment in payload.adjustments:
            is_book_adjustment = adjustment.effect in (
                "book_increase",
                "book_decrease",
            )

            if is_book_adjustment and adjustment.counter_account_id is None:
                raise ValueError(
                    f"Select a counter account for: {adjustment.description}"
                )

            if not is_book_adjustment and adjustment.counter_account_id is not None:
                raise ValueError(
                    f"Timing adjustment '{adjustment.description}' "
                    "must not have a counter account."
                )

            counter_account = None

            if adjustment.counter_account_id is not None:
                counter_account = (
                    db.query(Account)
                    .filter(
                        Account.id == adjustment.counter_account_id,
                        Account.is_active.is_(True),
                    )
                    .first()
                )

                if counter_account is None:
                    raise ValueError(
                        f"Counter account {adjustment.counter_account_id} "
                        "does not exist or is inactive."
                    )

                if counter_account.id == bank_account.ledger_account_id:
                    raise ValueError(
                        "The counter account cannot be the bank ledger account."
                    )

            adjustment_rows.append(
                SmartReconciliationAdjustmentModel(
                    adjustment_type=adjustment.adjustment_type,
                    description=adjustment.description,
                    amount=money(adjustment.amount),
                    effect=adjustment.effect,
                    counter_account_id=adjustment.counter_account_id,
                )
            )

        reconciliation = SmartReconciliationModel(
            bank_account_id=bank_account.id,
            statement_date=payload.statement_date,
            original_cash_book_balance=preview.original_cash_book_balance,
            adjusted_cash_book_balance=preview.adjusted_cash_book_balance,
            original_bank_statement_balance=(
                preview.original_bank_statement_balance
            ),
            adjusted_bank_statement_balance=(
                preview.adjusted_bank_statement_balance
            ),
            difference=preview.difference,
            status=preview.status,
            notes=payload.notes,
            adjustments=adjustment_rows,
        )

        db.add(reconciliation)
        db.commit()
        db.refresh(reconciliation)

        return reconciliation

    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc))

    except Exception:
        db.rollback()
        raise


@router.post(
    "/smart/{reconciliation_id}/approve",
    status_code=status.HTTP_200_OK,
)
def approve_smart_reconciliation(
    reconciliation_id: int,
    db: Session = Depends(get_db),
):
    reconciliation = (
        db.query(SmartReconciliationModel)
        .filter(SmartReconciliationModel.id == reconciliation_id)
        .with_for_update()
        .first()
    )

    if reconciliation is None:
        raise HTTPException(
            status_code=404,
            detail="Smart reconciliation record not found.",
        )

    # Prevent duplicate journal posting.
    if reconciliation.posted_journal_entry_id is not None:
        raise HTTPException(
            status_code=409,
            detail="This reconciliation has already been approved and posted.",
        )

    adjustments = list(reconciliation.adjustments)

    if any(item.journal_entry_id is not None for item in adjustments):
        raise HTTPException(
            status_code=409,
            detail="One or more adjustments have already been posted.",
        )

    bank_account = (
        db.query(BankAccount)
        .filter(
            BankAccount.id == reconciliation.bank_account_id,
            BankAccount.is_active.is_(True),
        )
        .first()
    )

    if bank_account is None:
        raise HTTPException(
            status_code=400,
            detail="The associated bank account is missing or inactive.",
        )

    bank_ledger = (
        db.query(Account)
        .filter(
            Account.id == bank_account.ledger_account_id,
            Account.is_active.is_(True),
            Account.account_type == "asset",
        )
        .first()
    )

    if bank_ledger is None:
        raise HTTPException(
            status_code=400,
            detail="The bank ledger account is missing or inactive.",
        )

    book_adjustments = [
        item
        for item in adjustments
        if item.effect in ("book_increase", "book_decrease")
    ]

    if not book_adjustments:
        raise HTTPException(
            status_code=400,
            detail="There are no book adjustments requiring journal posting.",
        )

    posted_entries = []

    try:
        for adjustment in book_adjustments:
            if adjustment.counter_account_id is None:
                raise ValueError(
                    f"Counter account is required for: {adjustment.description}"
                )

            counter_account = (
                db.query(Account)
                .filter(
                    Account.id == adjustment.counter_account_id,
                    Account.is_active.is_(True),
                )
                .first()
            )

            if counter_account is None:
                raise ValueError(
                    f"Counter account for '{adjustment.description}' "
                    "does not exist or is inactive."
                )

            if counter_account.id == bank_ledger.id:
                raise ValueError(
                    "The counter account cannot be the bank ledger account."
                )

            adjustment_type = adjustment.adjustment_type
            account_type = counter_account.account_type

            # Validate account types for known adjustment categories.
            if adjustment_type == "bank_charges":
                if account_type != "expense":
                    raise ValueError(
                        "Bank charges must use an expense account."
                    )

            elif adjustment_type in (
                "bank_interest",
                "dividend_collected",
            ):
                if account_type != "revenue":
                    raise ValueError(
                        f"{adjustment_type} must use a revenue account."
                    )

            elif adjustment_type == "dishonoured_cheque":
                if account_type != "asset":
                    raise ValueError(
                        "A dishonoured cheque must use an asset account, "
                        "such as Accounts Receivable."
                    )

            elif adjustment_type == "direct_debit":
                if account_type not in ("expense", "liability"):
                    raise ValueError(
                        "A direct debit must use an expense or liability account."
                    )

            elif adjustment_type not in (
                "cash_book_error",
                "other",
            ):
                raise ValueError(
                    f"Unsupported book adjustment type: {adjustment_type}"
                )

            amount = money(adjustment.amount)

            if amount <= 0:
                raise ValueError(
                    f"Invalid amount for: {adjustment.description}"
                )

            # Construct balanced double-entry journal lines.
            if adjustment.effect == "book_decrease":
                lines = [
                    {
                        "account_id": counter_account.id,
                        "debit": amount,
                        "credit": 0,
                        "description": adjustment.description,
                    },
                    {
                        "account_id": bank_ledger.id,
                        "debit": 0,
                        "credit": amount,
                        "description": adjustment.description,
                    },
                ]

            elif adjustment.effect == "book_increase":
                lines = [
                    {
                        "account_id": bank_ledger.id,
                        "debit": amount,
                        "credit": 0,
                        "description": adjustment.description,
                    },
                    {
                        "account_id": counter_account.id,
                        "debit": 0,
                        "credit": amount,
                        "description": adjustment.description,
                    },
                ]

            else:
                raise ValueError(
                    f"Unsupported book adjustment effect: {adjustment.effect}"
                )

            journal_entry = post_journal_entry(
                db,
                entry_date=reconciliation.statement_date,
                description=(
                    f"Smart BRS #{reconciliation.id}: "
                    f"{adjustment.description}"
                ),
                reference=(
                    f"SMART-BRS-{reconciliation.id}-ADJ-{adjustment.id}"
                ),
                source_type="smart_reconciliation",
                lines=lines,
            )

            adjustment.journal_entry_id = journal_entry.id
            posted_entries.append(journal_entry)

        # Store the first journal entry as the reconciliation's primary reference.
        reconciliation.posted_journal_entry_id = posted_entries[0].id

        db.commit()

        return {
            "message": "Smart bank reconciliation approved successfully.",
            "reconciliation_id": reconciliation.id,
            "reconciliation_status": reconciliation.status,
            "posting_status": "posted",
            "primary_journal_entry_id": reconciliation.posted_journal_entry_id,
            "posted_journal_entries": [
                {
                    "adjustment_id": adjustment.id,
                    "adjustment_type": adjustment.adjustment_type,
                    "description": adjustment.description,
                    "journal_entry_id": adjustment.journal_entry_id,
                    "amount": str(adjustment.amount),
                }
                for adjustment in book_adjustments
            ],
            "timing_adjustments_posted": 0,
        }

    except ValueError as exc:
        db.rollback()
        raise HTTPException(
            status_code=400,
            detail=str(exc),
        )

    except Exception:
        db.rollback()
        raise

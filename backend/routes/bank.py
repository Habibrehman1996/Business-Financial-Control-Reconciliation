import csv
import hashlib
import io

from datetime import date, timedelta
from decimal import Decimal, InvalidOperation

from fastapi import (
    APIRouter,
    Depends,
    File,
    HTTPException,
    Query,
    UploadFile,
    status,
)
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.models import (
    Account,
    BankAccount,
    BankTransaction,
    BankStatementLine,
    BankStatementImport,
)
from backend.schemas import (
    BankAccountCreate,
    BankAccountRead,
    BankTransactionCreate,
    BankTransactionRead,
    BankStatementImportResponse,
    BankStatementLineRead,
    BankStatementMatchCandidate,
    BankStatementMatchPreview,
    BankStatementManualMatch,
)
from backend.accounting import (
    get_account_by_code,
    initialize_standard_accounts,
    money,
)
from backend.ledger_posting import post_journal_entry


router = APIRouter(
    prefix="/api/bank",
    tags=["Bank Management"],
)


def create_bank_ledger_account(
    db: Session,
    bank_name: str,
    account_name: str,
) -> Account:
    """Create a separate ledger account for each bank account."""

    base_account = get_account_by_code(db, "1020")

    if base_account is None:
        raise ValueError("Standard Bank account is missing.")

    latest = (
        db.query(Account.id)
        .filter(Account.code.like("1020-%"))
        .order_by(Account.id.desc())
        .first()
    )

    sequence = (latest[0] if latest else 0) + 1
    code = f"1020-{sequence:08d}"

    ledger = Account(
        code=code,
        name=f"{bank_name} - {account_name}",
        account_type="asset",
        parent_id=base_account.id,
        is_active=True,
    )

    db.add(ledger)
    db.flush()

    return ledger


# --------------------------------------------------
# BANK ACCOUNTS
# --------------------------------------------------

@router.post(
    "/accounts",
    response_model=BankAccountRead,
    status_code=status.HTTP_201_CREATED,
)
def create_bank_account(
    payload: BankAccountCreate,
    db: Session = Depends(get_db),
):
    name = payload.name.strip()
    bank_name = payload.bank_name.strip()
    account_number = payload.account_number.strip()

    # Input validation
    if not name or len(name) < 2:
        raise HTTPException(
            status_code=400,
            detail="Valid bank account name is required.",
        )

    if not bank_name or len(bank_name) < 2:
        raise HTTPException(
            status_code=400,
            detail="Valid bank name is required.",
        )

    if not account_number or len(account_number) < 3:
        raise HTTPException(
            status_code=400,
            detail="Valid bank account number is required.",
        )

    if payload.opening_balance < 0:
        raise HTTPException(
            status_code=400,
            detail="Bank opening balance cannot be negative.",
        )

    # Duplicate account number check
    existing = (
        db.query(BankAccount)
        .filter(
            BankAccount.account_number == account_number
        )
        .first()
    )

    if existing:
        raise HTTPException(
            status_code=409,
            detail="This bank account number already exists.",
        )

    try:
        initialize_standard_accounts(db)

        ledger = create_bank_ledger_account(
            db,
            bank_name,
            name,
        )

        bank_account = BankAccount(
            name=name,
            bank_name=bank_name,
            account_number=account_number,
            ledger_account_id=ledger.id,
            opening_balance=money(payload.opening_balance),
            is_active=True,
        )

        db.add(bank_account)
        db.flush()

        opening_balance = money(payload.opening_balance)

        if opening_balance > 0:
            opening_equity = get_account_by_code(db, "3010")

            if opening_equity is None:
                raise ValueError(
                    "Opening Balance Equity account is missing."
                )

            post_journal_entry(
                db,
                entry_date=date.today(),
                description=f"Opening balance - {bank_name}",
                reference=f"BANK-OPEN-{bank_account.id}",
                lines=[
                    {
                        "account_id": ledger.id,
                        "debit": opening_balance,
                        "credit": 0,
                        "description": "Bank opening balance",
                    },
                    {
                        "account_id": opening_equity.id,
                        "debit": 0,
                        "credit": opening_balance,
                        "description": "Opening balance equity",
                    },
                ],
            )

        db.commit()
        db.refresh(bank_account)

        return bank_account

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
            detail="Bank account could not be created because of duplicate data.",
        )


@router.get(
    "/accounts",
    response_model=list[BankAccountRead],
)
def list_bank_accounts(
    active_only: bool = True,
    db: Session = Depends(get_db),
):
    query = db.query(BankAccount)

    if active_only:
        query = query.filter(
            BankAccount.is_active.is_(True)
        )

    return query.order_by(
        BankAccount.id.desc()
    ).all()


@router.get(
    "/accounts/{account_id}",
    response_model=BankAccountRead,
)
def get_bank_account(
    account_id: int,
    db: Session = Depends(get_db),
):
    account = (
        db.query(BankAccount)
        .filter(BankAccount.id == account_id)
        .first()
    )

    if account is None:
        raise HTTPException(
            status_code=404,
            detail="Bank account not found.",
        )

    return account


# --------------------------------------------------
# BANK TRANSACTIONS
# --------------------------------------------------

@router.post(
    "/transactions",
    response_model=BankTransactionRead,
    status_code=status.HTTP_201_CREATED,
)
def create_bank_transaction(
    payload: BankTransactionCreate,
    db: Session = Depends(get_db),
):
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

    counter_account = (
        db.query(Account)
        .filter(
            Account.id == payload.counter_account_id,
            Account.is_active.is_(True),
        )
        .first()
    )

    if counter_account is None:
        raise HTTPException(
            status_code=404,
            detail="Counter account not found or inactive.",
        )

    if counter_account.id == bank_account.ledger_account_id:
        raise HTTPException(
            status_code=400,
            detail="Bank account cannot be its own counter account.",
        )

    description = payload.description.strip()

    if len(description) < 2:
        raise HTTPException(
            status_code=400,
            detail="Transaction description is required.",
        )

    amount = money(payload.amount)

    if amount <= 0:
        raise HTTPException(
            status_code=400,
            detail="Transaction amount must be greater than zero.",
        )

    reference = (
        payload.reference.strip()
        if payload.reference and payload.reference.strip()
        else None
    )

    try:
        transaction = BankTransaction(
            bank_account_id=bank_account.id,
            transaction_date=payload.transaction_date,
            description=description,
            reference=reference,
            amount=amount,
            direction=payload.direction,
            source="book",
            is_reconciled=False,
        )

        db.add(transaction)
        db.flush()

        if payload.direction == "in":
            lines = [
                {
                    "account_id": bank_account.ledger_account_id,
                    "debit": amount,
                    "credit": 0,
                    "description": description,
                },
                {
                    "account_id": counter_account.id,
                    "debit": 0,
                    "credit": amount,
                    "description": description,
                },
            ]

        else:
            lines = [
                {
                    "account_id": counter_account.id,
                    "debit": amount,
                    "credit": 0,
                    "description": description,
                },
                {
                    "account_id": bank_account.ledger_account_id,
                    "debit": 0,
                    "credit": amount,
                    "description": description,
                },
            ]

        post_journal_entry(
            db,
            entry_date=payload.transaction_date,
            description=description,
            reference=reference or f"BANK-TXN-{transaction.id}",
            lines=lines,
        )

        db.commit()
        db.refresh(transaction)

        return transaction

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
            detail="Could not save bank transaction.",
        )


@router.get(
    "/transactions",
    response_model=list[BankTransactionRead],
)
def list_bank_transactions(
    bank_account_id: int | None = None,
    unreconciled_only: bool = False,
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
):
    query = db.query(BankTransaction)

    if bank_account_id is not None:
        query = query.filter(
            BankTransaction.bank_account_id == bank_account_id
        )

    if unreconciled_only:
        query = query.filter(
            BankTransaction.is_reconciled.is_(False)
        )

    return (
        query.order_by(
            BankTransaction.transaction_date.desc(),
            BankTransaction.id.desc(),
        )
        .limit(limit)
        .all()
    )


# --------------------------------------------------
# BANK STATEMENT CSV IMPORT
# --------------------------------------------------

@router.post(
    "/accounts/{account_id}/statement/import",
    response_model=BankStatementImportResponse,
    status_code=status.HTTP_201_CREATED,
)
async def import_bank_statement(
    account_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    # Validate file extension
    if not file.filename or not file.filename.lower().endswith(".csv"):
        raise HTTPException(
            status_code=400,
            detail="Please upload a CSV file.",
        )

    # Read file and enforce 10 MB limit
    content = await file.read()

    if not content:
        raise HTTPException(
            status_code=400,
            detail="The uploaded CSV file is empty.",
        )

    if len(content) > 10 * 1024 * 1024:
        raise HTTPException(
            status_code=413,
            detail="CSV file cannot exceed 10 MB.",
        )

    # Verify bank account
    bank_account = (
        db.query(BankAccount)
        .filter(
            BankAccount.id == account_id,
            BankAccount.is_active.is_(True),
        )
        .first()
    )

    if bank_account is None:
        raise HTTPException(
            status_code=404,
            detail="Active bank account not found.",
        )

    # Generate SHA-256 fingerprint
    file_hash = hashlib.sha256(content).hexdigest()

    existing_import = (
        db.query(BankStatementImport)
        .filter(
            BankStatementImport.bank_account_id == account_id,
            BankStatementImport.file_hash == file_hash,
        )
        .first()
    )

    if existing_import:
        raise HTTPException(
            status_code=409,
            detail="This CSV file has already been imported for this bank account.",
        )

    # Decode CSV
    try:
        decoded = content.decode("utf-8-sig")
        reader = csv.DictReader(io.StringIO(decoded))

    except UnicodeDecodeError:
        raise HTTPException(
            status_code=400,
            detail="CSV must use UTF-8 encoding.",
        )

    if not reader.fieldnames:
        raise HTTPException(
            status_code=400,
            detail="CSV column headers are missing.",
        )

    # Normalize column names
    normalized_headers = [
        header.strip().lower() if header else ""
        for header in reader.fieldnames
    ]

    if len(normalized_headers) != len(set(normalized_headers)):
        raise HTTPException(
            status_code=400,
            detail="CSV contains duplicate column headers.",
        )

    reader.fieldnames = normalized_headers

    required_columns = {
        "date",
        "description",
        "amount",
        "direction",
    }

    missing_columns = required_columns - set(normalized_headers)

    if missing_columns:
        raise HTTPException(
            status_code=400,
            detail=f"Missing CSV columns: {', '.join(sorted(missing_columns))}",
        )

    # Validate all rows before saving
    statement_lines = []
    skipped_count = 0

    try:
        for row_number, row in enumerate(reader, start=2):

            if not any(
                str(value or "").strip()
                for value in row.values()
            ):
                skipped_count += 1
                continue

            transaction_date_text = (
                row.get("date") or ""
            ).strip()

            description = (
                row.get("description") or ""
            ).strip()

            amount_text = (
                row.get("amount") or ""
            ).strip()

            direction = (
                row.get("direction") or ""
            ).strip().lower()

            reference = (
                row.get("reference") or ""
            ).strip() or None

            balance_text = (
                row.get("balance") or ""
            ).strip()

            if not transaction_date_text:
                raise ValueError(
                    f"Row {row_number}: transaction date is required."
                )

            try:
                transaction_date = date.fromisoformat(
                    transaction_date_text
                )
            except ValueError:
                raise ValueError(
                    f"Row {row_number}: date must use YYYY-MM-DD format."
                )

            if not description or len(description) > 255:
                raise ValueError(
                    f"Row {row_number}: description must contain 1-255 characters."
                )

            try:
                amount = Decimal(amount_text)
            except InvalidOperation:
                raise ValueError(
                    f"Row {row_number}: invalid transaction amount."
                )

            if not amount.is_finite() or amount <= 0:
                raise ValueError(
                    f"Row {row_number}: amount must be greater than zero."
                )

            if direction not in {"in", "out"}:
                raise ValueError(
                    f"Row {row_number}: direction must be 'in' or 'out'."
                )

            if reference and len(reference) > 100:
                raise ValueError(
                    f"Row {row_number}: reference cannot exceed 100 characters."
                )

            statement_balance = None

            if balance_text:
                try:
                    statement_balance = Decimal(balance_text)
                except InvalidOperation:
                    raise ValueError(
                        f"Row {row_number}: invalid running balance."
                    )

                if not statement_balance.is_finite():
                    raise ValueError(
                        f"Row {row_number}: running balance must be a valid number."
                    )

            statement_lines.append(
                BankStatementLine(
                    bank_account_id=account_id,
                    transaction_date=transaction_date,
                    description=description,
                    reference=reference,
                    amount=money(amount),
                    direction=direction,
                    statement_balance=(
                        money(statement_balance)
                        if statement_balance is not None
                        else None
                    ),
                    match_status="unmatched",
                )
            )

    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=str(exc),
        )

    if not statement_lines:
        raise HTTPException(
            status_code=400,
            detail="CSV contains no valid transaction rows.",
        )

    # Save import and statement lines atomically
    try:
        statement_import = BankStatementImport(
            bank_account_id=account_id,
            filename=file.filename,
            file_hash=file_hash,
        )

        db.add(statement_import)
        db.add_all(statement_lines)
        db.commit()

        return BankStatementImportResponse(
            message="Bank statement imported successfully.",
            bank_account_id=account_id,
            imported_count=len(statement_lines),
            duplicate_count=0,
            skipped_count=skipped_count,
        )

    except IntegrityError:
        db.rollback()

        raise HTTPException(
            status_code=409,
            detail="This statement file has already been imported.",
        )

    except Exception:
        db.rollback()
        raise


# --------------------------------------------------
# BANK STATEMENT LINES
# --------------------------------------------------

@router.get(
    "/accounts/{account_id}/statement/lines",
    response_model=list[BankStatementLineRead],
)
def get_bank_statement_lines(
    account_id: int,
    match_status: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
):
    # Verify bank account
    bank_account = (
        db.query(BankAccount)
        .filter(BankAccount.id == account_id)
        .first()
    )

    if bank_account is None:
        raise HTTPException(
            status_code=404,
            detail="Bank account not found.",
        )

    # Validate optional match status
    allowed_statuses = {"matched", "unmatched"}

    if match_status is not None and match_status not in allowed_statuses:
        raise HTTPException(
            status_code=400,
            detail="match_status must be 'matched' or 'unmatched'.",
        )

    # Retrieve statement lines
    query = db.query(BankStatementLine).filter(
        BankStatementLine.bank_account_id == account_id
    )

    if match_status:
        query = query.filter(
            BankStatementLine.match_status == match_status
        )

    statement_lines = (
        query
        .order_by(
            BankStatementLine.transaction_date.desc(),
            BankStatementLine.id.desc(),
        )
        .limit(limit)
        .all()
    )

    return statement_lines


# --------------------------------------------------
# BANK STATEMENT MATCH PREVIEW
# --------------------------------------------------

@router.get(
    "/accounts/{account_id}/statement/lines/{line_id}/match-preview",
    response_model=BankStatementMatchPreview,
)
def preview_bank_statement_match(
    account_id: int,
    line_id: int,
    date_tolerance_days: int = Query(default=3, ge=0, le=30),
    db: Session = Depends(get_db),
):
    # Find the statement line
    statement_line = (
        db.query(BankStatementLine)
        .filter(
            BankStatementLine.id == line_id,
            BankStatementLine.bank_account_id == account_id,
        )
        .first()
    )

    if statement_line is None:
        raise HTTPException(
            status_code=404,
            detail="Bank statement line not found.",
        )

    # Do not preview an already matched line
    if statement_line.match_status == "matched":
        return BankStatementMatchPreview(
            statement_line_id=line_id,
            match_status="already_matched",
            candidates=[],
        )

    # Calculate the allowed date range
    start_date = (
        statement_line.transaction_date
        - timedelta(days=date_tolerance_days)
    )
    end_date = (
        statement_line.transaction_date
        + timedelta(days=date_tolerance_days)
    )

    # Exclude book transactions already linked to statement lines
    already_linked_ids = (
        db.query(BankStatementLine.matched_bank_transaction_id)
        .filter(
            BankStatementLine.matched_bank_transaction_id.isnot(None)
        )
    )

    # Find possible book transaction matches
    possible_matches = (
        db.query(BankTransaction)
        .filter(
            BankTransaction.bank_account_id == account_id,
            BankTransaction.transaction_date >= start_date,
            BankTransaction.transaction_date <= end_date,
            BankTransaction.amount == statement_line.amount,
            BankTransaction.direction == statement_line.direction,
            BankTransaction.source == "book",
            BankTransaction.is_reconciled.is_(False),
            ~BankTransaction.id.in_(already_linked_ids),
        )
        .all()
    )

    # Prepare candidate responses
    candidates = []

    for transaction in possible_matches:
        reasons = [
            "Amount matches.",
            "Transaction direction matches.",
            "Transaction date is within the allowed tolerance.",
        ]

        if (
            statement_line.reference
            and transaction.reference
            and statement_line.reference.strip().lower()
            == transaction.reference.strip().lower()
        ):
            confidence = "high"
            reasons.append("Reference matches.")
        else:
            confidence = "medium"
            reasons.append(
                "Reference is missing or different; manual confirmation is recommended."
            )

        candidates.append(
            BankStatementMatchCandidate(
                bank_transaction=transaction,
                confidence=confidence,
                match_reasons=reasons,
            )
        )

    # Put the closest transaction dates first
    candidates.sort(
        key=lambda item: (
            abs(
                (
                    item.bank_transaction.transaction_date
                    - statement_line.transaction_date
                ).days
            ),
            item.bank_transaction.id,
        )
    )

    if not candidates:
        result_status = "no_match"
    elif len(candidates) == 1:
        result_status = "single_candidate"
    else:
        result_status = "multiple_candidates"

    return BankStatementMatchPreview(
        statement_line_id=line_id,
        match_status=result_status,
        candidates=candidates,
    )


# --------------------------------------------------
# MANUAL BANK STATEMENT MATCHING
# --------------------------------------------------

@router.post(
    "/accounts/{account_id}/statement/lines/{line_id}/match",
    response_model=BankStatementLineRead,
)
def manually_match_bank_statement_line(
    account_id: int,
    line_id: int,
    payload: BankStatementManualMatch,
    db: Session = Depends(get_db),
):
    # Find the statement line
    statement_line = (
        db.query(BankStatementLine)
        .filter(
            BankStatementLine.id == line_id,
            BankStatementLine.bank_account_id == account_id,
        )
        .with_for_update()
        .first()
    )

    if statement_line is None:
        raise HTTPException(
            status_code=404,
            detail="Bank statement line not found.",
        )

    if statement_line.match_status == "matched":
        raise HTTPException(
            status_code=409,
            detail="This statement line has already been matched.",
        )

    # Find the selected book transaction
    bank_transaction = (
        db.query(BankTransaction)
        .filter(
            BankTransaction.id == payload.bank_transaction_id,
            BankTransaction.bank_account_id == account_id,
            BankTransaction.source == "book",
        )
        .with_for_update()
        .first()
    )

    if bank_transaction is None:
        raise HTTPException(
            status_code=404,
            detail="Book transaction not found for this bank account.",
        )

    if bank_transaction.is_reconciled:
        raise HTTPException(
            status_code=409,
            detail="This book transaction is already reconciled.",
        )

    # Verify amount and direction
    if bank_transaction.amount != statement_line.amount:
        raise HTTPException(
            status_code=400,
            detail="Transaction amount does not match the statement line.",
        )

    if bank_transaction.direction != statement_line.direction:
        raise HTTPException(
            status_code=400,
            detail="Transaction direction does not match the statement line.",
        )

    # Ensure this book transaction is not linked elsewhere
    existing_match = (
        db.query(BankStatementLine)
        .filter(
            BankStatementLine.matched_bank_transaction_id
            == bank_transaction.id
        )
        .first()
    )

    if existing_match is not None:
        raise HTTPException(
            status_code=409,
            detail="This book transaction is already linked to another statement line.",
        )

    # Confirm the match without creating another journal entry
    try:
        statement_line.matched_bank_transaction_id = bank_transaction.id
        statement_line.match_status = "matched"
        bank_transaction.is_reconciled = True

        db.commit()
        db.refresh(statement_line)

        return statement_line

    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="This transaction was matched elsewhere. Please refresh and try again.",
        )

    except Exception:
        db.rollback()
        raise

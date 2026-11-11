from datetime import date
from decimal import Decimal
from uuid import uuid4

from sqlalchemy.orm import Session

from backend.accounting import money, validate_journal_totals
from backend.models import Account, JournalEntry, JournalLine


ZERO = Decimal("0.00")


def post_journal_entry(
    db: Session,
    *,
    entry_date: date,
    description: str,
    lines: list[dict],
    reference: str | None = None,
    source_type: str = "system",
) -> JournalEntry:
    """
    Validate and create a balanced, posted journal entry.

    This function flushes changes but does not commit.
    The calling route must commit or roll back the transaction.
    """

    if not isinstance(entry_date, date):
        raise ValueError("A valid journal entry date is required.")

    if not isinstance(description, str) or len(description.strip()) < 2:
        raise ValueError("Journal description must contain at least 2 characters.")

    if not isinstance(lines, list) or len(lines) < 2:
        raise ValueError("A journal entry requires at least two lines.")

    normalized_lines = []

    for index, line in enumerate(lines, start=1):
        if not isinstance(line, dict):
            raise ValueError(f"Journal line {index} is invalid.")

        account_id = line.get("account_id")

        if (
            isinstance(account_id, bool)
            or not isinstance(account_id, int)
            or account_id <= 0
        ):
            raise ValueError(f"Journal line {index} has an invalid account ID.")

        account = db.get(Account, account_id)

        if account is None or not account.is_active:
            raise ValueError(
                f"Account ID {account_id} does not exist or is inactive."
            )

        debit = money(line.get("debit", ZERO))
        credit = money(line.get("credit", ZERO))

        if debit < ZERO or credit < ZERO:
            raise ValueError("Debit and credit amounts cannot be negative.")

        if (debit > ZERO) == (credit > ZERO):
            raise ValueError(
                f"Journal line {index} must have either debit or credit, not both."
            )

        line_description = line.get("description")

        if line_description is not None:
            if not isinstance(line_description, str):
                raise ValueError(
                    f"Journal line {index} description must be text."
                )

            line_description = line_description.strip() or None

        normalized_lines.append(
            {
                "account_id": account_id,
                "debit": debit,
                "credit": credit,
                "description": line_description,
            }
        )

    total_debit, total_credit = validate_journal_totals(
        normalized_lines
    )

    if total_debit != total_credit:
        raise ValueError(
            "Journal entry debit and credit totals do not match."
        )

    # UUID-based number avoids relying on the latest database ID.
    entry_number = f"JV-{uuid4().hex[:16].upper()}"

    entry = JournalEntry(
        entry_number=entry_number,
        entry_date=entry_date,
        description=description.strip(),
        reference=reference.strip() if reference else None,
        status="posted",
    )

    db.add(entry)
    db.flush()

    for line in normalized_lines:
        db.add(
            JournalLine(
                journal_entry_id=entry.id,
                account_id=line["account_id"],
                debit=line["debit"],
                credit=line["credit"],
                description=line["description"],
            )
        )

    db.flush()

    return entry
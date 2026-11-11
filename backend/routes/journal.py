
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session, joinedload

from backend.database import get_db
from backend.models import JournalEntry
from backend.schemas import JournalEntryCreate, JournalEntryRead
from backend.ledger_posting import post_journal_entry
from sqlalchemy.exc import IntegrityError


router = APIRouter(
    prefix="/api/journal",
    tags=["Journal Entries"],
)


@router.post(
    "",
    response_model=JournalEntryRead,
    status_code=status.HTTP_201_CREATED,
)
def create_journal_entry(
    payload: JournalEntryCreate,
    db: Session = Depends(get_db),
):
    try:
        entry = post_journal_entry(
            db,
            entry_date=payload.entry_date,
            description=payload.description,
            reference=payload.reference,
            source_type="manual",
            lines=[
                line.model_dump()
                for line in payload.lines
            ],
        )

        db.commit()

        return (
            db.query(JournalEntry)
            .options(joinedload(JournalEntry.lines))
            .filter(JournalEntry.id == entry.id)
            .first()
        )

    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc))

    except Exception:
        db.rollback()
        raise

@router.post(
    "/{entry_id}/reverse",
    response_model=JournalEntryRead,
    status_code=status.HTTP_201_CREATED,
)
def reverse_journal_entry(
    entry_id: int,
    db: Session = Depends(get_db),
):
    original = (
        db.query(JournalEntry)
        .options(joinedload(JournalEntry.lines))
        .filter(JournalEntry.id == entry_id)
        .first()
    )

    if original is None:
        raise HTTPException(
            status_code=404,
            detail="Journal entry not found.",
        )

    if original.status != "posted":
        raise HTTPException(
            status_code=400,
            detail="Only posted journal entries can be reversed.",
        )

    if original.source_type != "manual":
        raise HTTPException(
            status_code=400,
            detail="System-generated entries must be reversed through their source module.",
        )

    if original.reversal_of_id is not None:
        raise HTTPException(
            status_code=400,
            detail="A reversal entry cannot be reversed.",
        )

    existing_reversal = (
        db.query(JournalEntry)
        .filter(JournalEntry.reversal_of_id == original.id)
        .first()
    )

    if existing_reversal is not None:
        raise HTTPException(
            status_code=409,
            detail="This journal entry has already been reversed.",
        )

    try:
        reversal = post_journal_entry(
            db,
            entry_date=date.today(),
            description=f"Reversal of {original.entry_number}",
            reference=f"REV-{original.entry_number}",
            source_type="system",
            lines=[
                {
                    "account_id": line.account_id,
                    "debit": line.credit,
                    "credit": line.debit,
                    "description": (
                        f"Reversal - {line.description}"
                        if line.description
                        else "Journal reversal"
                    ),
                }
                for line in original.lines
            ],
        )

        reversal.reversal_of_id = original.id
        db.flush()
        db.commit()

        return (
            db.query(JournalEntry)
            .options(joinedload(JournalEntry.lines))
            .filter(JournalEntry.id == reversal.id)
            .first()
        )

    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="This journal entry has already been reversed.",
        )

    except ValueError as exc:
        db.rollback()
        raise HTTPException(
            status_code=400,
            detail=str(exc),
        )

    except Exception:
        db.rollback()
        raise


@router.get("", response_model=list[JournalEntryRead])
def list_journal_entries(
    start_date: date | None = None,
    end_date: date | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
):
    if start_date and end_date and start_date > end_date:
        raise HTTPException(
            status_code=400,
            detail="start_date cannot be after end_date.",
        )

    query = (
        db.query(JournalEntry)
        .options(joinedload(JournalEntry.lines))
        .filter(JournalEntry.status == "posted")
    )

    if start_date:
        query = query.filter(JournalEntry.entry_date >= start_date)

    if end_date:
        query = query.filter(JournalEntry.entry_date <= end_date)

    return (
        query.order_by(
            JournalEntry.entry_date.desc(),
            JournalEntry.id.desc(),
        )
        .offset(offset)
        .limit(limit)
        .all()
    )


@router.get("/{entry_id}", response_model=JournalEntryRead)
def get_journal_entry(
    entry_id: int,
    db: Session = Depends(get_db),
):
    entry = (
        db.query(JournalEntry)
        .options(joinedload(JournalEntry.lines))
        .filter(JournalEntry.id == entry_id)
        .first()
    )

    if entry is None:
        raise HTTPException(
            status_code=404,
            detail="Journal entry not found.",
        )

    return entry

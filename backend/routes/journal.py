
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session, joinedload

from backend.database import get_db
from backend.models import JournalEntry
from backend.schemas import JournalEntryCreate, JournalEntryRead
from backend.ledger_posting import post_journal_entry


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

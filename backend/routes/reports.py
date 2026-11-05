
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.services.financial_reports import (
    get_dashboard_summary,
    get_profit_loss,
    get_trial_balance,
)


router = APIRouter(
    prefix="/api/reports",
    tags=["Financial Reports"],
)


def validate_date_range(
    start_date: date | None,
    end_date: date | None,
):
    if start_date and end_date and start_date > end_date:
        raise HTTPException(
            status_code=400,
            detail="Start date cannot be after end date.",
        )


@router.get("/dashboard")
def dashboard_report(
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
    db: Session = Depends(get_db),
):
    validate_date_range(start_date, end_date)

    try:
        return get_dashboard_summary(
            db,
            start_date=start_date,
            end_date=end_date,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/trial-balance")
def trial_balance_report(
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
    db: Session = Depends(get_db),
):
    validate_date_range(start_date, end_date)

    try:
        return get_trial_balance(
            db,
            start_date=start_date,
            end_date=end_date,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/profit-loss")
def profit_loss_report(
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
    db: Session = Depends(get_db),
):
    validate_date_range(start_date, end_date)

    try:
        return get_profit_loss(
            db,
            start_date=start_date,
            end_date=end_date,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

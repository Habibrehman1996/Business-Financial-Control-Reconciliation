
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.services.ai_insights import generate_financial_insights

router = APIRouter(prefix="/api/ai", tags=["AI Financial Insights"])


@router.get("/financial-insights")
def financial_insights(
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
    db: Session = Depends(get_db),
):
    if start_date and end_date and start_date > end_date:
        raise HTTPException(
            status_code=400,
            detail="start_date cannot be after end_date.",
        )

    try:
        insights = generate_financial_insights(
            db=db,
            start_date=start_date,
            end_date=end_date,
        )

        return {
            "success": True,
            "period": {
                "start_date": str(start_date) if start_date else None,
                "end_date": str(end_date) if end_date else None,
            },
            "insights": insights,
        }

    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail="Unable to generate financial insights.",
        ) from exc

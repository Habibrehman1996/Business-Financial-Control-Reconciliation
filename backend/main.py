from contextlib import asynccontextmanager

from dotenv import load_dotenv

# Load .env before importing modules that may read environment variables.
load_dotenv()

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from backend.database import engine, init_db
from backend.routes import (
    accounts,
    ai,
    bank,
    cash,
    expenses,
    inventory,
    journal,
    parties,
    purchases,
    reconciliation,
    reports,
    sales,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(
    title="Business Financial Control & Reconciliation Platform",
    description=(
        "Business accounting, double-entry ledger, reconciliation, "
        "inventory, and financial reporting API."
    ),
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(accounts.router)
app.include_router(journal.router)
app.include_router(bank.router)
app.include_router(cash.router)
app.include_router(parties.router)
app.include_router(sales.router)
app.include_router(purchases.router)
app.include_router(inventory.router)
app.include_router(expenses.router)
app.include_router(reconciliation.router)
app.include_router(reports.router)
app.include_router(ai.router)


@app.get("/", tags=["System"])
def root():
    return {
        "name": "Business Financial Control & Reconciliation Platform",
        "status": "running",
        "docs": "/docs",
    }


@app.get("/api/v1/health", tags=["System"])
def health_check():
    return {"status": "ok"}


@app.get("/api/v1/health/ready", tags=["System"])
def readiness_check():
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    except SQLAlchemyError as exc:
        raise HTTPException(
            status_code=503,
            detail={
                "status": "unavailable",
                "database": "unavailable",
                "message": "Database connection check failed.",
            },
        ) from exc

    return {"status": "ready", "database": "connected"}


import os
from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.engine import make_url
from sqlalchemy.orm import DeclarativeBase, sessionmaker


# SQLite database URL
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "sqlite:///./data/financial_control.db",
)


# Create database directory if it does not exist
database_url = make_url(DATABASE_URL)

if database_url.drivername.startswith("sqlite"):
    database_path = database_url.database

    if database_path and database_path != ":memory:":
        Path(database_path).parent.mkdir(parents=True, exist_ok=True)


# SQLAlchemy engine
connect_args = {}

if database_url.drivername.startswith("sqlite"):
    connect_args = {"check_same_thread": False}

engine = create_engine(
    DATABASE_URL,
    connect_args=connect_args,
    pool_pre_ping=True,
)


# Enable SQLite foreign-key constraints
if database_url.drivername.startswith("sqlite"):

    @event.listens_for(engine, "connect")
    def enable_sqlite_foreign_keys(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA busy_timeout=5000")
        cursor.close()


# Database session factory
SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    autocommit=False,
    expire_on_commit=False,
)


# Base class for all database models
class Base(DeclarativeBase):
    pass


# Dependency for FastAPI routes
def get_db():
    db = SessionLocal()

    try:
        yield db
    finally:
        db.close()


# Initialize database tables
def init_db():
    # Import models so SQLAlchemy registers all tables
    from backend import models  # noqa: F401

    Base.metadata.create_all(bind=engine)

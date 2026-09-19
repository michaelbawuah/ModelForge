"""Database engine and session management."""

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from modelforge.core.config import resolve_database_url

DATABASE_URL = resolve_database_url()

# pool_pre_ping checks connections before handing them to the application.
# This prevents stale database connections from surviving unnoticed.
engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,
)

SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    expire_on_commit=False,
)


def get_db() -> Session:
    """Provide one database session for a request."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

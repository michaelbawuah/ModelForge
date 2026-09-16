"""Database engine and session management."""

import os

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

DEFAULT_DATABASE_URL = (
    "mysql+pymysql://modelforge:modelforge_dev@127.0.0.1:3306/modelforge"
)

DATABASE_URL = os.getenv("DATABASE_URL", DEFAULT_DATABASE_URL)

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

"""Shared SQLAlchemy declarative base for ModelForge database models."""

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Base class inherited by every ModelForge ORM model."""

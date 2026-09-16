"""Declarative base for ModelForge database models."""

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Base class for all ModelForge ORM models."""
"""
Database engine/session setup.

Reads ``DATABASE_URL`` from the environment (via python-dotenv), defaulting to
a local SQLite file. The URL is Postgres-wire-compatible so pointing this at a
hosted Postgres (Supabase/Neon) later requires no schema changes -- only an
env var change.
"""

from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from data_layer.config import DATABASE_URL
from data_layer.models.base import Base

# A generous busy-timeout works around transient file locks from OneDrive/antivirus
# scanning the local SQLite file right after it's created or written to.
_connect_args = {"check_same_thread": False, "timeout": 30} if DATABASE_URL.startswith("sqlite") else {}

engine = create_engine(DATABASE_URL, connect_args=_connect_args, future=True)

SessionLocal = sessionmaker(bind=engine, expire_on_commit=False, future=True)


def init_db() -> None:
    """Create all tables that don't already exist. Never drops/alters existing tables."""

    # Ensure model modules are imported so they register on Base.metadata.
    from data_layer.models import drafts, league, reference, transactions  # noqa: F401

    Base.metadata.create_all(engine)


@contextmanager
def get_session() -> Iterator[Session]:
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()

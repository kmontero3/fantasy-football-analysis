"""Shared declarative base and lineage/reproducibility mixin."""

from __future__ import annotations

import datetime as dt

from sqlalchemy import DateTime, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class SourceLineageMixin:
    """
    Reproducibility metadata: where a row came from and when it was ingested.

    ``source`` is a short identifier like "sleeper" or "nflverse_csv".
    ``source_version`` is free-form (e.g. a file hash, API response date, or
    CSV snapshot date) so results can be traced back to the data that
    produced them.
    """

    source: Mapped[str] = mapped_column(String(32), nullable=False)
    source_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    loaded_at: Mapped[dt.datetime] = mapped_column(
        DateTime, default=lambda: dt.datetime.now(dt.timezone.utc), nullable=False
    )

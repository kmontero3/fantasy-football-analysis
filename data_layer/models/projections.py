"""
Vendor (third-party) player projections -- e.g. Sleeper's own projections feed.

These are a benchmark/reference data source ONLY. Per repo rules ("Projection
!= Valuation"), this table must never be silently merged into or confused with
this platform's own future projection-engine output -- every row is tagged
with ``source`` (from ``SourceLineageMixin``) plus the vendor's own player id,
so provenance is always explicit.

``grouping`` disambiguates season-level vs week-level rows:
    "season" -- a single season-aggregate projection; ``week`` is stored as 0
                (a sentinel, since real NFL weeks are 1+) rather than NULL, so
                the uniqueness constraint below is enforced reliably even on
                SQLite (where NULL != NULL for UNIQUE purposes).
    "week"   -- a single week's projection; ``week`` is the real 1+ week number.

Point-in-time versioning: this table is INSERT-ONLY. Every ingestion pull that
detects a vendor-side change (``vendor_last_modified`` advanced, or the
underlying ``stats``/structured fields changed) inserts a NEW row rather than
mutating the existing one, and flips the prior row's ``is_current`` to False.
This preserves the full history of what the vendor projected and when, which
is required for point-in-time reconstruction ("what was knowable as of T").

Only one row per (player_id, source, season, week, grouping) key may have
``is_current = True`` at a time. On SQLite/Postgres this is enforced with a
partial/filtered unique index (``uq_vendor_player_projection_current``) scoped
to ``is_current = 1``; the loader additionally enforces it at the application
layer (flip-then-flush-then-insert) since a partial unique index alone can't
prevent a buggy caller from passing ``is_current=True`` on manual inserts
outside the loader.
"""

from __future__ import annotations

import datetime as dt

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    JSON,
    Numeric,
    String,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from data_layer.models.base import Base, SourceLineageMixin

SEASON_GROUPING_WEEK_SENTINEL = 0

# The only category value this table should ever see -- a different value
# (e.g. a realized/actual-stats row) indicates the vendor feed changed shape.
VALID_CATEGORY = "proj"


class VendorPlayerProjection(Base, SourceLineageMixin):
    __tablename__ = "vendor_player_projections"
    __table_args__ = (
        # Partial unique index: only one "current" row per logical key.
        # SQLite and Postgres both support partial/filtered unique indexes;
        # each dialect uses its own kwarg, so both are supplied.
        Index(
            "uq_vendor_player_projection_current",
            "player_id", "source", "season", "week", "grouping",
            unique=True,
            sqlite_where=text("is_current = 1"),
            postgresql_where=text("is_current = true"),
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # Internal canonical identity, resolved via the player_id_mapping crosswalk --
    # never the vendor's raw id used as identity.
    player_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("player_reference.player_id"), nullable=False, index=True
    )
    vendor_player_id: Mapped[str] = mapped_column(String(16), nullable=False, index=True)

    season: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    week: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    grouping: Mapped[str] = mapped_column(String(8), nullable=False)  # "season" | "week"
    season_type: Mapped[str] = mapped_column(String(16), nullable=False, default="regular")

    # True for exactly one row per (player_id, source, season, week, grouping)
    # key -- the latest known vendor version. False rows are retained history.
    is_current: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)

    # The vendor's own "this projection changed" timestamp (epoch ms in the
    # payload's ``last_modified``/``updated_at`` fields -- identical in every
    # observed sample, so collapsed to one column). Used to decide whether a
    # re-pull represents a real vendor-side update vs. just our own polling.
    vendor_last_modified: Mapped[dt.datetime | None] = mapped_column(DateTime, nullable=True)

    # Vendor payload's own "proj" vs. other category tag -- see VALID_CATEGORY.
    category: Mapped[str | None] = mapped_column(String(16), nullable=True)

    # The underlying data provider behind Sleeper's projections feed (e.g.
    # "rotowire"). Kept distinct from ``source``, which stays "sleeper" (the
    # API we pulled from), since Sleeper could swap/add providers later.
    company: Mapped[str | None] = mapped_column(String(32), nullable=True)

    position: Mapped[str | None] = mapped_column(String(8), nullable=True)
    team: Mapped[str | None] = mapped_column(String(8), nullable=True)

    # Projected games played, from stats.gp.
    gp: Mapped[float | None] = mapped_column(Numeric(4, 2), nullable=True)

    # Week-level only -- always NULL on season-level ("grouping" == "season") rows.
    opponent: Mapped[str | None] = mapped_column(String(8), nullable=True)
    is_away_team: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    game_date: Mapped[dt.date | None] = mapped_column(Date, nullable=True)

    # Fantasy-point projections, when present in the vendor payload.
    pts_ppr: Mapped[float | None] = mapped_column(Numeric(7, 2), nullable=True)
    pts_half_ppr: Mapped[float | None] = mapped_column(Numeric(7, 2), nullable=True)
    pts_std: Mapped[float | None] = mapped_column(Numeric(7, 2), nullable=True)

    # Full raw underlying stat projections, passed through as-is -- the stat
    # set varies by position/vendor (adp_*, pass_*, rush_*, rec_*, bonus_*,
    # etc.), so a structured blob avoids a sparse wide table while still
    # keeping everything queryable via JSON functions.
    stats: Mapped[dict | None] = mapped_column(JSON, nullable=True)

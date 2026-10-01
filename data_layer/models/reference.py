"""
Player reference (nflverse-style dimension data) and cross-source ID mapping.

``PlayerReference.player_id`` is the canonical internal player key used by the
rest of the schema (transactions, draft picks, rosters) instead of hard-coding
any single source's ID.

Re-keying decision (data-quality-auditor blocker #2): ``player_id`` prefers the
stable ``sleeper_player_id`` when a player has one, falling back to ``gsis_id``,
and only to the unstable ``NOID-{name}-{year}`` key when neither source ID is
known yet. Sleeper IDs never change for a player and nflverse's player_ids.csv
gives us a Sleeper ID for the vast majority of rostered players, so preferring
it as the identity key (rather than re-keying FK rows later) avoids orphaning
``TransactionAsset.player_id`` / ``DraftPick.player_id`` when a fallback ID is
eventually resolved to a real source ID. ``gsis_id`` is kept as a secondary,
nullable attribute for nflverse joins. See build_player_id() in
ingestion/player_reference_loader.py.
"""

from __future__ import annotations

from sqlalchemy import ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from data_layer.models.base import Base, SourceLineageMixin


class PlayerReference(Base, SourceLineageMixin):
    __tablename__ = "player_reference"

    player_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    sleeper_player_id: Mapped[str | None] = mapped_column(String(16), unique=True, nullable=True, index=True)
    gsis_id: Mapped[str | None] = mapped_column(String(16), unique=True, nullable=True, index=True)

    full_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    first_name: Mapped[str | None] = mapped_column(String(64), nullable=True)
    last_name: Mapped[str | None] = mapped_column(String(64), nullable=True)

    position: Mapped[str | None] = mapped_column(String(8), nullable=True, index=True)
    position_group: Mapped[str | None] = mapped_column(String(8), nullable=True)

    birth_date: Mapped[str | None] = mapped_column(String(16), nullable=True)
    college: Mapped[str | None] = mapped_column(String(128), nullable=True)

    draft_year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    draft_round: Mapped[int | None] = mapped_column(Integer, nullable=True)
    draft_pick: Mapped[int | None] = mapped_column(Integer, nullable=True)
    draft_team: Mapped[str | None] = mapped_column(String(8), nullable=True)

    height: Mapped[int | None] = mapped_column(Integer, nullable=True)
    weight: Mapped[int | None] = mapped_column(Integer, nullable=True)

    latest_team: Mapped[str | None] = mapped_column(String(8), nullable=True)
    status: Mapped[str | None] = mapped_column(String(16), nullable=True)

    id_mappings: Mapped[list["PlayerIDMapping"]] = relationship(
        back_populates="player", cascade="all, delete-orphan"
    )


class PlayerIDMapping(Base, SourceLineageMixin):
    """
    Cross-source ID crosswalk (nflverse ``player_ids.csv`` + Sleeper's own
    player map). One row per player; lookups by any source ID should go
    through this table rather than hard-coding a source's ID elsewhere.
    """

    __tablename__ = "player_id_mapping"
    __table_args__ = (UniqueConstraint("player_id", name="uq_player_id_mapping_player_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    player_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("player_reference.player_id"), nullable=False, index=True
    )

    sleeper_id: Mapped[str | None] = mapped_column(String(16), unique=True, nullable=True, index=True)
    espn_id: Mapped[str | None] = mapped_column(String(16), nullable=True)
    yahoo_id: Mapped[str | None] = mapped_column(String(16), nullable=True)
    mfl_id: Mapped[str | None] = mapped_column(String(16), nullable=True)
    pfr_id: Mapped[str | None] = mapped_column(String(16), nullable=True)
    pff_id: Mapped[str | None] = mapped_column(String(16), nullable=True)
    sportradar_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    fantasypros_id: Mapped[str | None] = mapped_column(String(16), nullable=True)
    nfl_id: Mapped[str | None] = mapped_column(String(16), nullable=True)
    cbs_id: Mapped[str | None] = mapped_column(String(16), nullable=True)
    rotowire_id: Mapped[str | None] = mapped_column(String(16), nullable=True)
    cfbref_id: Mapped[str | None] = mapped_column(String(32), nullable=True)

    player: Mapped[PlayerReference] = relationship(back_populates="id_mappings")

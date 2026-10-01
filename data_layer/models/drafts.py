"""Draft, draft picks, and traded draft picks."""

from __future__ import annotations

from sqlalchemy import BigInteger, Boolean, ForeignKey, Integer, JSON, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from data_layer.models.base import Base, SourceLineageMixin


class Draft(Base, SourceLineageMixin):
    __tablename__ = "drafts"

    draft_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    league_settings_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("league_settings.id"), nullable=False, index=True
    )

    season: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    type: Mapped[str | None] = mapped_column(String(16), nullable=True)  # snake | linear | auction
    status: Mapped[str | None] = mapped_column(String(16), nullable=True)
    start_time: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    settings_raw: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    picks: Mapped[list["DraftPick"]] = relationship(back_populates="draft", cascade="all, delete-orphan")


class DraftPick(Base, SourceLineageMixin):
    __tablename__ = "draft_picks"
    __table_args__ = (UniqueConstraint("draft_id", "pick_no", name="uq_pick_per_draft"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    draft_id: Mapped[str] = mapped_column(String(32), ForeignKey("drafts.draft_id"), nullable=False, index=True)

    round: Mapped[int | None] = mapped_column(Integer, nullable=True)
    pick_no: Mapped[int] = mapped_column(Integer, nullable=False)
    draft_slot: Mapped[int | None] = mapped_column(Integer, nullable=True)
    roster_id: Mapped[int | None] = mapped_column(Integer, nullable=True)

    sleeper_player_id: Mapped[str | None] = mapped_column(String(16), nullable=True)
    player_id: Mapped[str | None] = mapped_column(
        String(32), ForeignKey("player_reference.player_id"), nullable=True, index=True
    )

    is_keeper: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    metadata_raw: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    draft: Mapped[Draft] = relationship(back_populates="picks")


class DraftTradedPick(Base, SourceLineageMixin):
    """
    A draft pick that changed hands via trade, identified by the original
    season/round/roster slot plus its current owner. Sourced from both the
    league-level and draft-level ``traded_picks`` Sleeper endpoints.
    """

    __tablename__ = "draft_traded_picks"
    __table_args__ = (
        UniqueConstraint(
            "league_settings_id", "season", "round", "roster_id", name="uq_traded_pick_slot"
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    league_settings_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("league_settings.id"), nullable=False, index=True
    )
    draft_id: Mapped[str | None] = mapped_column(String(32), ForeignKey("drafts.draft_id"), nullable=True)

    season: Mapped[int] = mapped_column(Integer, nullable=False)
    round: Mapped[int] = mapped_column(Integer, nullable=False)
    roster_id: Mapped[int] = mapped_column(Integer, nullable=False)  # original owner slot
    previous_owner_roster_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    owner_roster_id: Mapped[int] = mapped_column(Integer, nullable=False)  # current owner

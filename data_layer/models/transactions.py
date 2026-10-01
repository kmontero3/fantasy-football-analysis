"""
Transaction ledger: trades, waivers, free-agent adds/drops, FAAB spend.

Treated as an append-only historical record (point-in-time correctness):
once a transaction row exists it is not rewritten by re-ingestion, only new
transactions are inserted. ``TransactionAsset`` rows capture the individual
player/draft-pick/FAAB movements within a transaction so trades with multiple
assets and participants are fully represented.
"""

from __future__ import annotations

from sqlalchemy import BigInteger, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from data_layer.models.base import Base, SourceLineageMixin


class Transaction(Base, SourceLineageMixin):
    __tablename__ = "transactions"

    transaction_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    league_settings_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("league_settings.id"), nullable=False, index=True
    )

    season: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    week: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    leg: Mapped[int | None] = mapped_column(Integer, nullable=True)

    type: Mapped[str] = mapped_column(String(16), nullable=False)  # trade | waiver | free_agent | commissioner
    status: Mapped[str | None] = mapped_column(String(16), nullable=True)
    created_at_ts: Mapped[int | None] = mapped_column(BigInteger, nullable=True)

    participants: Mapped[list["TransactionRosterParticipant"]] = relationship(
        back_populates="transaction", cascade="all, delete-orphan"
    )
    assets: Mapped[list["TransactionAsset"]] = relationship(
        back_populates="transaction", cascade="all, delete-orphan"
    )


class TransactionRosterParticipant(Base, SourceLineageMixin):
    """Which rosters were party to a transaction (both sides of a trade, the claiming roster for a waiver, etc.)."""

    __tablename__ = "transaction_roster_participants"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    transaction_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("transactions.transaction_id"), nullable=False, index=True
    )
    sleeper_roster_id: Mapped[int] = mapped_column(Integer, nullable=False)

    transaction: Mapped[Transaction] = relationship(back_populates="participants")


class TransactionAsset(Base, SourceLineageMixin):
    """A single asset movement within a transaction: a player, a draft pick, or FAAB."""

    __tablename__ = "transaction_assets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    transaction_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("transactions.transaction_id"), nullable=False, index=True
    )

    asset_type: Mapped[str] = mapped_column(String(16), nullable=False)  # player | draft_pick | faab
    direction: Mapped[str | None] = mapped_column(String(8), nullable=True)  # add | drop
    roster_id: Mapped[int | None] = mapped_column(Integer, nullable=True)

    sleeper_player_id: Mapped[str | None] = mapped_column(String(16), nullable=True)
    player_id: Mapped[str | None] = mapped_column(
        String(32), ForeignKey("player_reference.player_id"), nullable=True, index=True
    )

    faab_amount: Mapped[int | None] = mapped_column(Integer, nullable=True)

    pick_season: Mapped[int | None] = mapped_column(Integer, nullable=True)
    pick_round: Mapped[int | None] = mapped_column(Integer, nullable=True)
    pick_original_roster_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    pick_new_owner_roster_id: Mapped[int | None] = mapped_column(Integer, nullable=True)

    transaction: Mapped[Transaction] = relationship(back_populates="assets")

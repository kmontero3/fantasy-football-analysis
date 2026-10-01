"""
League identity, per-season settings snapshot, membership, and rosters.

``League`` is the stable logical league across years (keyed by the env var
prefix, e.g. "PHINASTY"). ``LeagueSettings`` is one immutable-ish snapshot per
league+season (leagues don't change settings mid-season, per platform
decision), and everything season-scoped (members, rosters, transactions,
drafts) hangs off ``LeagueSettings.id``.
"""

from __future__ import annotations

import datetime as dt

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, JSON, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from data_layer.models.base import Base, SourceLineageMixin


class League(Base):
    __tablename__ = "leagues"

    league_key: Mapped[str] = mapped_column(String(32), primary_key=True)
    platform: Mapped[str] = mapped_column(String(16), default="sleeper", nullable=False)
    name: Mapped[str | None] = mapped_column(String(128), nullable=True)

    seasons: Mapped[list["LeagueSettings"]] = relationship(back_populates="league")


class LeagueSettings(Base, SourceLineageMixin):
    """
    One settings snapshot per league per season. Versioned (not upserted in
    place): a new row is inserted whenever scoring/roster settings change, so
    ``effective_from`` lets point-in-time queries find the settings active as
    of any past timestamp T. ``is_current`` flags the latest row per
    league+season for cheap "current settings" lookups.
    """

    __tablename__ = "league_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    league_key: Mapped[str] = mapped_column(String(32), ForeignKey("leagues.league_key"), nullable=False, index=True)
    season: Mapped[int] = mapped_column(Integer, nullable=False, index=True)

    sleeper_league_id: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    previous_sleeper_league_id: Mapped[str | None] = mapped_column(String(32), nullable=True)

    effective_from: Mapped["dt.datetime"] = mapped_column(
        DateTime, default=lambda: dt.datetime.now(dt.timezone.utc), nullable=False
    )
    is_current: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    total_rosters: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str | None] = mapped_column(String(16), nullable=True)

    roster_positions: Mapped[dict | list | None] = mapped_column(JSON, nullable=True)
    scoring_settings: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    settings_raw: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    league: Mapped[League] = relationship(back_populates="seasons")
    members: Mapped[list["LeagueMember"]] = relationship(back_populates="league_season", cascade="all, delete-orphan")
    rosters: Mapped[list["LeagueRoster"]] = relationship(back_populates="league_season", cascade="all, delete-orphan")


class LeagueMember(Base, SourceLineageMixin):
    __tablename__ = "league_members"
    __table_args__ = (UniqueConstraint("league_settings_id", "sleeper_user_id", name="uq_member_per_season"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    league_settings_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("league_settings.id"), nullable=False, index=True
    )

    sleeper_user_id: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    display_name: Mapped[str | None] = mapped_column(String(64), nullable=True)
    team_name: Mapped[str | None] = mapped_column(String(64), nullable=True)
    is_owner: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    league_season: Mapped[LeagueSettings] = relationship(back_populates="members")


class LeagueRoster(Base, SourceLineageMixin):
    """
    Current roster composition snapshot. Not point-in-time versioned in V0 --
    this reflects roster state as of the last ingestion run. The authoritative
    historical ledger of roster changes is the ``transactions`` table.
    """

    __tablename__ = "league_rosters"
    __table_args__ = (
        UniqueConstraint("league_settings_id", "sleeper_roster_id", name="uq_roster_per_season"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    league_settings_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("league_settings.id"), nullable=False, index=True
    )

    sleeper_roster_id: Mapped[int] = mapped_column(Integer, nullable=False)
    owner_sleeper_user_id: Mapped[str | None] = mapped_column(String(32), nullable=True)

    player_sleeper_ids: Mapped[list | None] = mapped_column(JSON, nullable=True)
    starters_sleeper_ids: Mapped[list | None] = mapped_column(JSON, nullable=True)
    reserve_sleeper_ids: Mapped[list | None] = mapped_column(JSON, nullable=True)
    taxi_sleeper_ids: Mapped[list | None] = mapped_column(JSON, nullable=True)

    wins: Mapped[int | None] = mapped_column(Integer, nullable=True)
    losses: Mapped[int | None] = mapped_column(Integer, nullable=True)
    ties: Mapped[int | None] = mapped_column(Integer, nullable=True)
    fpts: Mapped[float | None] = mapped_column(Float, nullable=True)
    fpts_against: Mapped[float | None] = mapped_column(Float, nullable=True)
    waiver_position: Mapped[int | None] = mapped_column(Integer, nullable=True)
    waiver_budget_used: Mapped[int | None] = mapped_column(Integer, nullable=True)

    settings_raw: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    league_season: Mapped[LeagueSettings] = relationship(back_populates="rosters")

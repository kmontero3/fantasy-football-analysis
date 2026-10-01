"""Ingest league identity, per-season settings snapshot, members, and rosters from Sleeper."""

from __future__ import annotations

import datetime as dt
from typing import Optional

from sqlalchemy.orm import Session

from data_layer.models.league import League, LeagueMember, LeagueRoster, LeagueSettings
from sleeper_api import SleeperAPI

SOURCE = "sleeper"


def _get_or_create_league(session: Session, league_key: str) -> League:
    league = session.get(League, league_key)
    if league is None:
        league = League(league_key=league_key)
        session.add(league)
    return league


def ingest_league_season(
    session: Session,
    sleeper: SleeperAPI,
    league_key: str,
    season: int,
    sleeper_league_id: str,
) -> LeagueSettings:
    """
    Fetch the current Sleeper settings and insert a new LeagueSettings row if
    scoring/roster settings have changed since the last ingested snapshot
    (point-in-time correctness): the previous row is left untouched and only
    flipped out of ``is_current`` so "what rules were active at time T" stays
    reconstructible. Also upserts members and rosters for the resulting
    snapshot.
    """

    now = dt.datetime.now(dt.timezone.utc)

    _get_or_create_league(session, league_key)

    league_data = sleeper.get_league(sleeper_league_id)

    current = (
        session.query(LeagueSettings)
        .filter(
            LeagueSettings.league_key == league_key,
            LeagueSettings.season == season,
            LeagueSettings.is_current.is_(True),
        )
        .one_or_none()
    )

    new_roster_positions = league_data.get("roster_positions")
    new_scoring_settings = league_data.get("scoring_settings")
    settings_changed = current is None or (
        current.roster_positions != new_roster_positions
        or current.scoring_settings != new_scoring_settings
    )

    if settings_changed:
        if current is not None:
            current.is_current = False
        settings = LeagueSettings(league_key=league_key, season=season, effective_from=now)
        session.add(settings)
    else:
        settings = current

    settings.sleeper_league_id = sleeper_league_id
    settings.previous_sleeper_league_id = league_data.get("previous_league_id")
    settings.name = league_data.get("name")
    settings.total_rosters = league_data.get("total_rosters")
    settings.status = league_data.get("status")
    settings.roster_positions = new_roster_positions
    settings.scoring_settings = new_scoring_settings
    settings.settings_raw = league_data.get("settings")
    settings.source = SOURCE
    settings.source_version = None
    settings.loaded_at = now
    settings.is_current = True

    session.flush()  # populate settings.id for child rows

    _ingest_members(session, sleeper, settings, sleeper_league_id, now)
    _ingest_rosters(session, sleeper, settings, sleeper_league_id, now)

    return settings


def _ingest_members(
    session: Session,
    sleeper: SleeperAPI,
    settings: LeagueSettings,
    sleeper_league_id: str,
    now: dt.datetime,
) -> None:
    users = sleeper.get_league_users(sleeper_league_id)

    for user in users:
        sleeper_user_id = user.get("user_id")

        existing = (
            session.query(LeagueMember)
            .filter(
                LeagueMember.league_settings_id == settings.id,
                LeagueMember.sleeper_user_id == sleeper_user_id,
            )
            .one_or_none()
        )
        member = existing or LeagueMember(
            league_settings_id=settings.id, sleeper_user_id=sleeper_user_id
        )

        metadata = user.get("metadata") or {}
        member.display_name = user.get("display_name")
        member.team_name = metadata.get("team_name")
        member.is_owner = bool(user.get("is_owner"))
        member.source = SOURCE
        member.loaded_at = now

        if not existing:
            session.add(member)


def _ingest_rosters(
    session: Session,
    sleeper: SleeperAPI,
    settings: LeagueSettings,
    sleeper_league_id: str,
    now: dt.datetime,
) -> None:
    rosters = sleeper.get_rosters(sleeper_league_id)

    for roster in rosters:
        sleeper_roster_id = roster.get("roster_id")

        existing = (
            session.query(LeagueRoster)
            .filter(
                LeagueRoster.league_settings_id == settings.id,
                LeagueRoster.sleeper_roster_id == sleeper_roster_id,
            )
            .one_or_none()
        )
        league_roster = existing or LeagueRoster(
            league_settings_id=settings.id, sleeper_roster_id=sleeper_roster_id
        )

        roster_settings = roster.get("settings") or {}
        league_roster.owner_sleeper_user_id = roster.get("owner_id")
        league_roster.player_sleeper_ids = roster.get("players")
        league_roster.starters_sleeper_ids = roster.get("starters")
        league_roster.reserve_sleeper_ids = roster.get("reserve")
        league_roster.taxi_sleeper_ids = roster.get("taxi")
        league_roster.wins = roster_settings.get("wins")
        league_roster.losses = roster_settings.get("losses")
        league_roster.ties = roster_settings.get("ties")
        league_roster.fpts = _combine_points(roster_settings, "fpts")
        league_roster.fpts_against = _combine_points(roster_settings, "fpts_against")
        league_roster.waiver_position = roster_settings.get("waiver_position")
        league_roster.waiver_budget_used = roster_settings.get("waiver_budget_used")
        league_roster.settings_raw = roster_settings
        league_roster.source = SOURCE
        league_roster.loaded_at = now

        if not existing:
            session.add(league_roster)


def _combine_points(roster_settings: dict, prefix: str) -> Optional[float]:
    whole = roster_settings.get(prefix)
    decimal = roster_settings.get(f"{prefix}_decimal")
    if whole is None:
        return None
    return float(whole) + (float(decimal) / 100 if decimal else 0.0)

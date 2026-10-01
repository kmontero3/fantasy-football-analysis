"""Ingest drafts, draft picks, and traded picks for a league season."""

from __future__ import annotations

import datetime as dt

from sqlalchemy.orm import Session

from data_layer.ingestion.player_reference_loader import resolve_player_id
from data_layer.models.drafts import Draft, DraftPick, DraftTradedPick
from data_layer.models.league import LeagueSettings
from sleeper_api import SleeperAPI

SOURCE = "sleeper"


def ingest_drafts_for_season(session: Session, sleeper: SleeperAPI, settings: LeagueSettings) -> int:
    now = dt.datetime.now(dt.timezone.utc)
    draft_summaries = sleeper.get_league_drafts(settings.sleeper_league_id)
    count = 0

    for summary in draft_summaries:
        draft_id = summary.get("draft_id")
        draft_data = sleeper.get_draft(draft_id)

        existing = session.get(Draft, draft_id)
        draft = existing or Draft(draft_id=draft_id)
        draft.league_settings_id = settings.id
        draft.season = settings.season
        draft.type = draft_data.get("type")
        draft.status = draft_data.get("status")
        draft.start_time = draft_data.get("start_time")
        draft.settings_raw = draft_data.get("settings")
        draft.source = SOURCE
        draft.loaded_at = now

        if not existing:
            session.add(draft)
        session.flush()

        _ingest_picks(session, sleeper, draft, now)
        count += 1

        _ingest_traded_picks(
            session, sleeper.get_draft_traded_picks(draft_id), settings, draft_id, now
        )

    # League-level traded picks endpoint covers pre-draft-creation trades too.
    _ingest_traded_picks(
        session, sleeper.get_traded_picks(settings.sleeper_league_id), settings, None, now
    )

    return count


def _ingest_picks(session: Session, sleeper: SleeperAPI, draft: Draft, now: dt.datetime) -> None:
    picks = sleeper.get_draft_picks(draft.draft_id)

    for pick in picks:
        pick_no = pick.get("pick_no")

        existing = (
            session.query(DraftPick)
            .filter(DraftPick.draft_id == draft.draft_id, DraftPick.pick_no == pick_no)
            .one_or_none()
        )
        draft_pick = existing or DraftPick(draft_id=draft.draft_id, pick_no=pick_no)

        sleeper_player_id = pick.get("player_id")
        draft_pick.round = pick.get("round")
        draft_pick.draft_slot = pick.get("draft_slot")
        draft_pick.roster_id = pick.get("roster_id")
        draft_pick.sleeper_player_id = sleeper_player_id
        draft_pick.player_id = resolve_player_id(session, sleeper_player_id)
        draft_pick.is_keeper = pick.get("is_keeper")
        draft_pick.metadata_raw = pick.get("metadata")
        draft_pick.source = SOURCE
        draft_pick.loaded_at = now

        if not existing:
            session.add(draft_pick)


def _ingest_traded_picks(
    session: Session,
    traded_picks: list,
    settings: LeagueSettings,
    draft_id: str | None,
    now: dt.datetime,
) -> None:
    for pick in traded_picks:
        season = int(pick["season"])
        round_no = pick.get("round")
        roster_id = pick.get("roster_id")

        existing = (
            session.query(DraftTradedPick)
            .filter(
                DraftTradedPick.league_settings_id == settings.id,
                DraftTradedPick.season == season,
                DraftTradedPick.round == round_no,
                DraftTradedPick.roster_id == roster_id,
            )
            .one_or_none()
        )
        traded_pick = existing or DraftTradedPick(
            league_settings_id=settings.id, season=season, round=round_no, roster_id=roster_id
        )

        traded_pick.draft_id = draft_id
        traded_pick.previous_owner_roster_id = pick.get("previous_owner_id")
        traded_pick.owner_roster_id = pick.get("owner_id")
        traded_pick.source = SOURCE
        traded_pick.loaded_at = now

        if not existing:
            session.add(traded_pick)

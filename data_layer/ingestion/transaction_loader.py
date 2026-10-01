"""
Ingest transactions (trades, waivers, free-agent moves, FAAB) for a league
season. Append-only for the transaction facts themselves: once a
transaction_id exists its assets/participants are never rewritten. The one
exception is ``status`` -- for non-terminal transactions (e.g. a pending
waiver) we allow the status field to be updated in place so the eventual
terminal outcome ("complete"/"failed") gets recorded.
"""

from __future__ import annotations

import datetime as dt

from sqlalchemy.orm import Session

from data_layer.ingestion.player_reference_loader import resolve_player_id
from data_layer.models.league import LeagueSettings
from data_layer.models.transactions import Transaction, TransactionAsset, TransactionRosterParticipant
from sleeper_api import SleeperAPI

SOURCE = "sleeper"

# Sleeper leagues run roughly 18 scoring weeks (regular season + playoffs);
# fetching a fixed superset of weeks and letting empty weeks no-op is simpler
# and more robust than trying to infer the exact week count per league.
MAX_WEEKS = 18

_TERMINAL_STATUSES = {"complete", "failed"}


def ingest_transactions_for_season(
    session: Session,
    sleeper: SleeperAPI,
    settings: LeagueSettings,
) -> int:
    inserted = 0
    now = dt.datetime.now(dt.timezone.utc)

    for week in range(1, MAX_WEEKS + 1):
        transactions = sleeper.get_transactions(settings.sleeper_league_id, week)

        for tx in transactions:
            transaction_id = tx.get("transaction_id")

            existing = session.get(Transaction, transaction_id)
            if existing is not None:
                # Transaction facts (assets/participants) are immutable history;
                # only allow a status-only update while still non-terminal, so
                # pending waivers eventually get their terminal status recorded.
                new_status = tx.get("status")
                if existing.status not in _TERMINAL_STATUSES and new_status != existing.status:
                    existing.status = new_status
                    existing.loaded_at = now
                continue

            transaction = Transaction(
                transaction_id=transaction_id,
                league_settings_id=settings.id,
                season=settings.season,
                week=week,
                leg=tx.get("leg"),
                type=tx.get("type"),
                status=tx.get("status"),
                created_at_ts=tx.get("created"),
                source=SOURCE,
                loaded_at=now,
            )
            session.add(transaction)

            for roster_id in tx.get("roster_ids") or []:
                session.add(
                    TransactionRosterParticipant(
                        transaction_id=transaction_id, sleeper_roster_id=roster_id
                    )
                )

            _add_player_assets(session, transaction_id, tx.get("adds") or {}, direction="add")
            _add_player_assets(session, transaction_id, tx.get("drops") or {}, direction="drop")
            _add_faab_assets(session, transaction_id, tx.get("waiver_budget") or [])
            _add_pick_assets(session, transaction_id, tx.get("draft_picks") or [])

            inserted += 1

    return inserted


def _add_player_assets(session: Session, transaction_id: str, moves: dict, direction: str) -> None:
    for sleeper_player_id, roster_id in moves.items():
        session.add(
            TransactionAsset(
                transaction_id=transaction_id,
                asset_type="player",
                direction=direction,
                roster_id=roster_id,
                sleeper_player_id=sleeper_player_id,
                player_id=resolve_player_id(session, sleeper_player_id),
            )
        )


def _add_faab_assets(session: Session, transaction_id: str, faab_moves: list) -> None:
    for move in faab_moves:
        session.add(
            TransactionAsset(
                transaction_id=transaction_id,
                asset_type="faab",
                roster_id=move.get("receiver"),
                faab_amount=move.get("amount"),
            )
        )


def _add_pick_assets(session: Session, transaction_id: str, picks: list) -> None:
    for pick in picks:
        session.add(
            TransactionAsset(
                transaction_id=transaction_id,
                asset_type="draft_pick",
                roster_id=pick.get("owner_id"),
                pick_season=int(pick["season"]) if pick.get("season") else None,
                pick_round=pick.get("round"),
                pick_original_roster_id=pick.get("roster_id"),
                pick_new_owner_roster_id=pick.get("owner_id"),
            )
        )

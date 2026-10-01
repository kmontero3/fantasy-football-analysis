"""
V0 ingestion entrypoint.

Run from the repo root:

    python -m data_layer.ingestion.run_ingestion

Loads player reference/ID-mapping CSVs, then for every league+season found in
the environment (see data_layer.config.discover_leagues_from_env), ingests
league settings/members/rosters, transactions, and drafts from Sleeper.
"""

from __future__ import annotations

from data_layer.config import PLAYER_IDS_CSV_PATH, PLAYERS_CSV_PATH, discover_leagues_from_env
from data_layer.db import get_session, init_db
from data_layer.ingestion.draft_loader import ingest_drafts_for_season
from data_layer.ingestion.league_loader import ingest_league_season
from data_layer.ingestion.player_reference_loader import (
    backfill_unresolved_player_ids,
    load_player_id_mapping,
    load_player_reference,
)
from data_layer.ingestion.transaction_loader import ingest_transactions_for_season
from sleeper_api import SleeperAPI


def main() -> None:
    init_db()
    sleeper = SleeperAPI()

    with get_session() as session:
        ref_count = load_player_reference(session, PLAYERS_CSV_PATH, PLAYER_IDS_CSV_PATH)
        mapping_count = load_player_id_mapping(session, PLAYER_IDS_CSV_PATH)
        backfilled = backfill_unresolved_player_ids(session)
        print(f"Loaded {ref_count} player_reference rows, {mapping_count} player_id_mapping rows.")
        print(
            f"Backfilled {backfilled['transaction_assets']} transaction_assets, "
            f"{backfilled['draft_picks']} draft_picks with previously-unresolved player_ids."
        )

    league_entries = discover_leagues_from_env()
    if not league_entries:
        print("No leagues found in environment (expected <KEY>_LEAGUE_<SEASON> vars).")
        return

    for entry in league_entries:
        try:
            with get_session() as session:
                settings = ingest_league_season(
                    session, sleeper, entry.league_key, entry.season, entry.sleeper_league_id
                )
                session.flush()

                tx_count = ingest_transactions_for_season(session, sleeper, settings)
                draft_count = ingest_drafts_for_season(session, sleeper, settings)

                print(
                    f"{entry.league_key} {entry.season}: "
                    f"settings ok, {tx_count} new transactions, {draft_count} drafts."
                )
        except Exception as exc:  # noqa: BLE001 - one league's failure must not abort the whole run
            print(f"{entry.league_key} {entry.season}: ingestion failed, skipping -- {exc}")


if __name__ == "__main__":
    main()

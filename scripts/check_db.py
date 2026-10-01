"""
Read-only post-ingestion verification script.

Run after ``data_layer.ingestion.run_ingestion`` to catch duplicate-key
violations and print a per-table row count / freshness summary. Intended for
CI (see ``.github/workflows/ingest.yml``): exits non-zero if any duplicate
violation is found so a bad database is never committed/pushed.

Does not modify any data -- only issues SELECT statements against the
existing engine/session from ``data_layer.db``.
"""

from __future__ import annotations

import sys

from sqlalchemy import func, inspect, select

from data_layer.db import get_session
from data_layer.models.drafts import Draft, DraftPick, DraftTradedPick
from data_layer.models.league import League, LeagueMember, LeagueRoster, LeagueSettings
from data_layer.models.reference import PlayerIDMapping, PlayerReference
from data_layer.models.transactions import (
    Transaction,
    TransactionAsset,
    TransactionRosterParticipant,
)

# Tables with a meaningful uniqueness key to duplicate-check, keyed by
# (model, key_columns). key_columns are the column names that together must
# be unique (mirrors each model's UniqueConstraint / primary key).
DUPLICATE_CHECKS: list[tuple[type, tuple[str, ...]]] = [
    (Transaction, ("transaction_id",)),
    (PlayerReference, ("player_id",)),
    (PlayerReference, ("sleeper_player_id",)),
    (PlayerReference, ("gsis_id",)),
    (PlayerIDMapping, ("player_id",)),
    (PlayerIDMapping, ("sleeper_id",)),
    (DraftPick, ("draft_id", "pick_no")),
    (LeagueMember, ("league_settings_id", "sleeper_user_id")),
    (LeagueRoster, ("league_settings_id", "sleeper_roster_id")),
    (DraftTradedPick, ("league_settings_id", "season", "round", "roster_id")),
]

# All tables to include in the row count / freshness summary.
SUMMARY_MODELS: list[type] = [
    League,
    LeagueSettings,
    LeagueMember,
    LeagueRoster,
    Draft,
    DraftPick,
    DraftTradedPick,
    PlayerReference,
    PlayerIDMapping,
    Transaction,
    TransactionRosterParticipant,
    TransactionAsset,
]


def _has_column(model: type, column_name: str) -> bool:
    return column_name in inspect(model).columns


def find_duplicates(session, model: type, key_columns: tuple[str, ...]) -> list[tuple]:
    """Return the key-value tuples that appear more than once for the given columns."""

    # Columns like sleeper_player_id/gsis_id are nullable unique columns --
    # NULLs are not duplicates, so exclude them before grouping.
    cols = [getattr(model, name) for name in key_columns]
    stmt = select(*cols, func.count().label("n"))
    for col in cols:
        stmt = stmt.where(col.is_not(None))
    stmt = stmt.group_by(*cols).having(func.count() > 1)
    return session.execute(stmt).all()


def summarize_table(session, model: type) -> str:
    table_name = inspect(model).local_table.name
    count = session.execute(select(func.count()).select_from(model)).scalar_one()

    max_loaded_at = None
    if _has_column(model, "loaded_at"):
        max_loaded_at = session.execute(select(func.max(model.loaded_at))).scalar_one()

    freshness = f"max loaded_at={max_loaded_at}" if max_loaded_at is not None else "no loaded_at column"
    return f"  {table_name:<32} rows={count:<8} {freshness}"


def main() -> int:
    violations: list[str] = []
    summary_lines: list[str] = []

    with get_session() as session:
        print("Row count / freshness summary:")
        for model in SUMMARY_MODELS:
            line = summarize_table(session, model)
            print(line)
            summary_lines.append(line)

        print("\nDuplicate key checks:")
        for model, key_columns in DUPLICATE_CHECKS:
            table_name = inspect(model).local_table.name
            key_desc = ", ".join(key_columns)
            dupes = find_duplicates(session, model, key_columns)
            if dupes:
                for row in dupes:
                    violations.append(
                        f"{table_name}: duplicate key ({key_desc}) = {row[:-1]} occurs {row[-1]} times"
                    )
                print(f"  FAIL {table_name:<32} key=({key_desc}) -> {len(dupes)} duplicate value(s)")
            else:
                print(f"  OK   {table_name:<32} key=({key_desc})")

    if violations:
        print("\nDuplicate violations found:", file=sys.stderr)
        for v in violations:
            print(f"  - {v}", file=sys.stderr)
        return 1

    print("\nNo duplicate violations found.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

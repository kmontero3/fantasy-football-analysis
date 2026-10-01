"""
Ingest Sleeper's third-party player projections (benchmark/reference data).

Standalone/exploratory only -- NOT wired into run_ingestion.py yet. Run from
the repo root:

    python -m data_layer.ingestion.projection_loader --season 2026 --week 1
    python -m data_layer.ingestion.projection_loader --season 2026 --week 1 2 3

Each Sleeper player_id is resolved to the internal canonical player_id via the
existing player_id_mapping crosswalk; players that can't be resolved are
logged and skipped rather than failing the whole run.

Insert-only / point-in-time versioning: rows are NEVER updated in place. Each
pull compares the vendor's ``last_modified``/``updated_at`` timestamp (and the
underlying stats) against the current row for that
(player_id, source, season, week, grouping) key. If nothing vendor-side has
changed, the pull is a no-op. If something changed, the existing "current"
row is flipped to ``is_current=False`` and a brand-new row is inserted as the
new "current" version -- preserving full history for point-in-time analysis.

``is_current`` uniqueness is enforced two ways: a partial/filtered unique
index at the DB layer (see ``VendorPlayerProjection.__table_args__``), and
application logic here (flip the old row to False and flush before inserting
the new True row) so the two statements never race within one flush batch.
"""

from __future__ import annotations

import argparse
import datetime as dt
from typing import Any, Dict, Optional

from sqlalchemy.orm import Session

from data_layer.db import get_session, init_db
from data_layer.ingestion.player_reference_loader import resolve_player_id
from data_layer.models.projections import VALID_CATEGORY, VendorPlayerProjection
from sleeper_api import SleeperProjectionsAPI

SOURCE = "sleeper"
GROUPING_WEEK = "week"


def _to_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _to_bool(value: Any) -> Optional[bool]:
    if value is None:
        return None
    return bool(value)


def _epoch_ms_to_datetime(value: Any) -> Optional[dt.datetime]:
    """Returns a naive UTC datetime -- SQLite's DATETIME column drops tzinfo on
    round-trip, so storing/comparing naive values avoids aware/naive mismatches."""
    if value is None:
        return None
    try:
        return dt.datetime.fromtimestamp(float(value) / 1000.0, tz=dt.timezone.utc).replace(tzinfo=None)
    except (TypeError, ValueError, OSError):
        return None


def _parse_date(value: Any) -> Optional[dt.date]:
    if not value:
        return None
    try:
        return dt.date.fromisoformat(str(value))
    except ValueError:
        return None


def _extract_pts(stats: Dict[str, Any]) -> tuple[Optional[float], Optional[float], Optional[float]]:
    return (
        _to_float(stats.get("pts_ppr")),
        _to_float(stats.get("pts_half_ppr")),
        _to_float(stats.get("pts_std")),
    )


def _row_fields(row: Dict[str, Any], stats: Dict[str, Any]) -> Dict[str, Any]:
    """Map a raw vendor payload row to the structured VendorPlayerProjection fields."""

    pts_ppr, pts_half_ppr, pts_std = _extract_pts(stats)
    player_meta = row.get("player") if isinstance(row.get("player"), dict) else None

    return dict(
        position=(player_meta or {}).get("position"),
        team=row.get("team"),
        gp=_to_float(stats.get("gp")),
        opponent=row.get("opponent"),
        is_away_team=_to_bool(row.get("is_away_team")),
        game_date=_parse_date(row.get("date")),
        pts_ppr=pts_ppr,
        pts_half_ppr=pts_half_ppr,
        pts_std=pts_std,
        stats=stats,
        category=row.get("category"),
        company=row.get("company"),
        vendor_last_modified=_epoch_ms_to_datetime(row.get("last_modified") or row.get("updated_at")),
    )


_NUMERIC_KEYS = ("gp", "pts_ppr", "pts_half_ppr", "pts_std")
_DIRECT_KEYS = ("stats", "position", "team", "opponent", "is_away_team", "game_date", "category", "company")


def _has_changed(existing: VendorPlayerProjection, fields: Dict[str, Any]) -> bool:
    """
    Decide whether ``fields`` represents a real vendor-side change relative to
    ``existing``, vs. just our own re-pull returning the same payload.
    """

    existing_vlm = existing.vendor_last_modified
    new_vlm = fields["vendor_last_modified"]
    if new_vlm is not None and (existing_vlm is None or new_vlm > existing_vlm):
        return True

    # Numeric DB columns round-trip as Decimal; compare as float to avoid
    # Decimal-vs-float precision false positives on every re-pull.
    for key in _NUMERIC_KEYS:
        existing_val = getattr(existing, key)
        existing_val = float(existing_val) if existing_val is not None else None
        if existing_val != fields[key]:
            return True

    return any(getattr(existing, key) != fields[key] for key in _DIRECT_KEYS)


def ingest_weekly_projections(
    session: Session,
    sleeper_projections: SleeperProjectionsAPI,
    season: int,
    week: int,
    season_type: str = "regular",
) -> Dict[str, int]:
    """
    Pull bulk weekly vendor projections for a season/week and insert new
    "current" version rows, idempotently, into ``vendor_player_projections``.
    """

    now = dt.datetime.now(dt.timezone.utc)
    rows = sleeper_projections.get_weekly_projections(season, week, season_type=season_type)

    result = {
        "inserted": 0,
        "new_versions": 0,
        "unchanged": 0,
        "skipped_unmapped": 0,
        "skipped_bad_category": 0,
    }

    for row in rows or []:
        vendor_player_id = row.get("player_id")
        if not vendor_player_id:
            continue

        category = row.get("category")
        if category != VALID_CATEGORY:
            print(
                f"Skipping Sleeper player_id={vendor_player_id!r} (season={season}, week={week}): "
                f"unexpected category={category!r} (expected {VALID_CATEGORY!r}) -- "
                "vendor feed may have changed shape."
            )
            result["skipped_bad_category"] += 1
            continue

        player_id = resolve_player_id(session, vendor_player_id)
        if player_id is None:
            print(f"Skipping unmapped Sleeper player_id={vendor_player_id!r} (season={season}, week={week})")
            result["skipped_unmapped"] += 1
            continue

        stats = row.get("stats") or {}
        fields = _row_fields(row, stats)

        existing = (
            session.query(VendorPlayerProjection)
            .filter(
                VendorPlayerProjection.player_id == player_id,
                VendorPlayerProjection.source == SOURCE,
                VendorPlayerProjection.season == season,
                VendorPlayerProjection.week == week,
                VendorPlayerProjection.grouping == GROUPING_WEEK,
                VendorPlayerProjection.is_current.is_(True),
            )
            .one_or_none()
        )

        if existing is None:
            session.add(
                VendorPlayerProjection(
                    player_id=player_id,
                    vendor_player_id=str(vendor_player_id),
                    season=season,
                    week=week,
                    grouping=GROUPING_WEEK,
                    season_type=season_type,
                    is_current=True,
                    source=SOURCE,
                    loaded_at=now,
                    **fields,
                )
            )
            result["inserted"] += 1
            continue

        if not _has_changed(existing, fields):
            result["unchanged"] += 1
            continue

        # Flip the old "current" row to history, flush so the partial unique
        # index never sees two is_current=True rows for this key at once,
        # then insert the new current version.
        existing.is_current = False
        session.flush()

        session.add(
            VendorPlayerProjection(
                player_id=player_id,
                vendor_player_id=str(vendor_player_id),
                season=season,
                week=week,
                grouping=GROUPING_WEEK,
                season_type=season_type,
                is_current=True,
                source=SOURCE,
                loaded_at=now,
                **fields,
            )
        )
        result["new_versions"] += 1

    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Ingest Sleeper vendor player projections (benchmark data only).")
    parser.add_argument("--season", type=int, required=True, help="NFL season, e.g. 2026")
    parser.add_argument("--week", type=int, nargs="+", required=True, help="One or more week numbers, e.g. --week 1 2 3")
    parser.add_argument("--season-type", default="regular", help="Sleeper season_type (default: regular)")
    args = parser.parse_args()

    init_db()
    sleeper_projections = SleeperProjectionsAPI()

    for week in args.week:
        with get_session() as session:
            result = ingest_weekly_projections(session, sleeper_projections, args.season, week, args.season_type)
            print(
                f"season={args.season} week={week}: "
                f"{result['inserted']} inserted, {result['new_versions']} new versions, "
                f"{result['unchanged']} unchanged, {result['skipped_unmapped']} skipped (unmapped), "
                f"{result['skipped_bad_category']} skipped (bad category)."
            )


if __name__ == "__main__":
    main()


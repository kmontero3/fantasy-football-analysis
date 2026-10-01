"""
Load player reference + ID mapping from the nflverse-style CSVs in data/.

These are dimension tables refreshed from the CSV snapshot on each run
(upsert by player_id). They are not treated as an append-only historical
ledger -- the CSV itself is the versioned source of truth (track its
snapshot identity via ``source_version``).

Identity re-keying (data-quality-auditor blocker #2): ``player_id`` prefers
the stable ``sleeper_player_id`` over the unstable ``NOID-{name}-{year}``
fallback, since Sleeper IDs never change for a player and are available for
the vast majority of rows via the player_ids.csv crosswalk. ``players.csv``
itself doesn't carry a sleeper_id column, so ``load_player_reference`` builds
a small gsis_id/name+year -> sleeper_id lookup from ``player_ids.csv`` first
and uses it to compute the same ``player_id`` that ``load_player_id_mapping``
will later compute for the same player.
"""

from __future__ import annotations

import datetime as dt
import re
from typing import Dict, Optional, Tuple

import pandas as pd
from sqlalchemy.orm import Session

from data_layer.models.reference import PlayerIDMapping, PlayerReference


def _clean(value: object) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    if text == "" or text.upper() == "NA" or text.lower() == "nan":
        return None
    return text


def _clean_int(value: object) -> Optional[int]:
    text = _clean(value)
    if text is None:
        return None
    try:
        return int(float(text))
    except ValueError:
        return None


def _slugify(text: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "-", text.strip().lower()).strip("-")


def build_player_id(
    sleeper_id: Optional[str],
    gsis_id: Optional[str],
    fallback_name: str,
    fallback_year: object,
) -> str:
    """
    Canonical player_id: stable ``sleeper_id`` when present, else ``gsis_id``,
    else a deterministic fallback derived from name + draft year. Flagged for
    the data-quality-auditor -- fallback IDs are not guaranteed globally
    stable across re-ingestion if a player's name string changes between CSV
    snapshots, and should be superseded by a sleeper_id/gsis_id as soon as one
    is known.
    """

    if sleeper_id:
        return f"SLP-{sleeper_id}"[:32]

    if gsis_id:
        return gsis_id

    year = _clean(fallback_year) or "unknown"
    return f"NOID-{_slugify(fallback_name)}-{year}"[:32]


def _load_sleeper_crosswalk(csv_path: str) -> Tuple[Dict[str, str], Dict[str, str]]:
    """
    Build lookup tables from player_ids.csv so load_player_reference can
    resolve the same sleeper_id (and therefore the same player_id) that
    load_player_id_mapping will later compute. Returns (by_gsis_id, by_name_year).
    """

    df = pd.read_csv(csv_path, dtype=str)
    by_gsis_id: Dict[str, str] = {}
    by_name_year: Dict[str, str] = {}

    for _, row in df.iterrows():
        sleeper_id = _clean(row.get("sleeper_id"))
        if not sleeper_id:
            continue

        gsis_id = _clean(row.get("gsis_id"))
        if gsis_id:
            by_gsis_id[gsis_id] = sleeper_id

        name = _clean(row.get("name")) or _clean(row.get("merge_name"))
        year = _clean(row.get("draft_year"))
        if name and year:
            by_name_year[f"{_slugify(name)}-{year}"] = sleeper_id

    return by_gsis_id, by_name_year


def load_player_reference(
    session: Session,
    csv_path: str,
    player_ids_csv_path: Optional[str] = None,
    source: str = "nflverse_csv",
    source_version: Optional[str] = None,
) -> int:
    """Upsert PlayerReference rows from data/players.csv. Returns row count processed."""

    df = pd.read_csv(csv_path, dtype=str)
    version = source_version or dt.date.today().isoformat()
    count = 0

    by_gsis_id: Dict[str, str] = {}
    by_name_year: Dict[str, str] = {}
    if player_ids_csv_path:
        by_gsis_id, by_name_year = _load_sleeper_crosswalk(player_ids_csv_path)

    for _, row in df.iterrows():
        gsis_id = _clean(row.get("gsis_id"))
        full_name = _clean(row.get("display_name")) or _clean(row.get("first_name"))
        draft_year = row.get("rookie_season")

        sleeper_id = by_gsis_id.get(gsis_id) if gsis_id else None
        if sleeper_id is None and full_name:
            year = _clean(draft_year)
            if year:
                sleeper_id = by_name_year.get(f"{_slugify(full_name)}-{year}")

        player_id = build_player_id(sleeper_id, gsis_id, full_name or "unknown", draft_year)

        existing = session.get(PlayerReference, player_id)
        target = existing or PlayerReference(player_id=player_id)

        target.sleeper_player_id = sleeper_id
        target.gsis_id = gsis_id
        target.full_name = full_name
        target.first_name = _clean(row.get("first_name"))
        target.last_name = _clean(row.get("last_name"))
        target.position = _clean(row.get("position"))
        target.position_group = _clean(row.get("position_group"))
        target.birth_date = _clean(row.get("birth_date"))
        target.college = _clean(row.get("college_name"))
        target.draft_year = _clean_int(row.get("draft_year"))
        target.draft_round = _clean_int(row.get("draft_round"))
        target.draft_pick = _clean_int(row.get("draft_pick"))
        target.draft_team = _clean(row.get("draft_team"))
        target.height = _clean_int(row.get("height"))
        target.weight = _clean_int(row.get("weight"))
        target.latest_team = _clean(row.get("latest_team"))
        target.status = _clean(row.get("status"))
        target.source = source
        target.source_version = version
        target.loaded_at = dt.datetime.now(dt.timezone.utc)

        if not existing:
            session.add(target)

        count += 1

    return count


def load_player_id_mapping(
    session: Session,
    csv_path: str,
    source: str = "nflverse_csv",
    source_version: Optional[str] = None,
) -> int:
    """
    Upsert PlayerIDMapping rows from data/player_ids.csv, one row per
    player_id (unique). Looks up the existing row by player_id first (the
    stable identity key); sleeper_id is only used as a reconciliation
    fallback for legacy rows created before the player_id was unique. Rows
    without a resolvable player_reference are skipped -- run
    load_player_reference first.
    """

    df = pd.read_csv(csv_path, dtype=str)
    version = source_version or dt.date.today().isoformat()
    count = 0

    for _, row in df.iterrows():
        gsis_id = _clean(row.get("gsis_id"))
        name = _clean(row.get("name")) or _clean(row.get("merge_name")) or "unknown"
        sleeper_id = _clean(row.get("sleeper_id"))
        player_id = build_player_id(sleeper_id, gsis_id, name, row.get("draft_year"))

        if session.get(PlayerReference, player_id) is None:
            # Unresolvable without a matching player_reference row; skip rather
            # than fabricate a dimension row from the ID-mapping CSV alone.
            continue

        existing = (
            session.query(PlayerIDMapping)
            .filter(PlayerIDMapping.player_id == player_id)
            .one_or_none()
        )
        if existing is None and sleeper_id:
            # Reconciliation fallback for rows ingested before this constraint
            # existed, or if the CSV's player_id derivation shifted slightly.
            existing = (
                session.query(PlayerIDMapping)
                .filter(PlayerIDMapping.sleeper_id == sleeper_id)
                .one_or_none()
            )

        target = existing or PlayerIDMapping(player_id=player_id, sleeper_id=sleeper_id)
        target.player_id = player_id
        target.sleeper_id = sleeper_id
        target.espn_id = _clean(row.get("espn_id"))
        target.yahoo_id = _clean(row.get("yahoo_id"))
        target.mfl_id = _clean(row.get("mfl_id"))
        target.pfr_id = _clean(row.get("pfr_id"))
        target.pff_id = _clean(row.get("pff_id"))
        target.sportradar_id = _clean(row.get("sportradar_id"))
        target.fantasypros_id = _clean(row.get("fantasypros_id"))
        target.nfl_id = _clean(row.get("nfl_id"))
        target.cbs_id = _clean(row.get("cbs_id"))
        target.rotowire_id = _clean(row.get("rotowire_id"))
        target.cfbref_id = _clean(row.get("cfbref_id"))
        target.source = source
        target.source_version = version
        target.loaded_at = dt.datetime.now(dt.timezone.utc)

        if not existing:
            session.add(target)

        count += 1

    return count


def resolve_player_id(session: Session, sleeper_player_id: Optional[str]) -> Optional[str]:
    """Look up the canonical player_id for a Sleeper player ID, or None if unmapped."""

    if not sleeper_player_id:
        return None

    mapping = (
        session.query(PlayerIDMapping)
        .filter(PlayerIDMapping.sleeper_id == str(sleeper_player_id))
        .one_or_none()
    )

    return mapping.player_id if mapping else None


def backfill_unresolved_player_ids(session: Session) -> Dict[str, int]:
    """
    Re-resolve TransactionAsset/DraftPick rows with player_id IS NULL, in case
    the player CSV crosswalk has since caught up with a sleeper_player_id it
    didn't previously recognize. Safe to run repeatedly; only touches rows
    currently missing a player_id.
    """

    # Imported locally to avoid a hard import-time dependency between the
    # reference loader and the transaction/draft models.
    from data_layer.models.drafts import DraftPick
    from data_layer.models.transactions import TransactionAsset

    updated = {"transaction_assets": 0, "draft_picks": 0}

    assets = (
        session.query(TransactionAsset)
        .filter(TransactionAsset.player_id.is_(None), TransactionAsset.sleeper_player_id.is_not(None))
        .all()
    )
    for asset in assets:
        resolved = resolve_player_id(session, asset.sleeper_player_id)
        if resolved:
            asset.player_id = resolved
            updated["transaction_assets"] += 1

    picks = (
        session.query(DraftPick)
        .filter(DraftPick.player_id.is_(None), DraftPick.sleeper_player_id.is_not(None))
        .all()
    )
    for pick in picks:
        resolved = resolve_player_id(session, pick.sleeper_player_id)
        if resolved:
            pick.player_id = resolved
            updated["draft_picks"] += 1

    return updated

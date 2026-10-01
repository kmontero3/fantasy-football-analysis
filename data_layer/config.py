"""
Environment-driven configuration.

No league IDs or scoring settings are hard-coded here. League identity/season/
Sleeper league_id triples are discovered from environment variables matching
the pattern ``<LEAGUE_KEY>_LEAGUE_<SEASON>`` (e.g. ``PHINASTY_LEAGUE_2026``),
so adding a league or a season only requires an env var change.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import List

from dotenv import load_dotenv

load_dotenv()

_LEAGUE_ENV_PATTERN = re.compile(r"^(?P<league_key>[A-Za-z0-9]+)_LEAGUE_(?P<season>\d{4})$")


@dataclass(frozen=True)
class LeagueEnvEntry:
    league_key: str
    season: int
    sleeper_league_id: str


def discover_leagues_from_env() -> List[LeagueEnvEntry]:
    """
    Scan environment variables for ``<LEAGUE_KEY>_LEAGUE_<SEASON>=<sleeper_league_id>``
    entries and return them. This is the single source of truth for which
    leagues/seasons get ingested; nothing is hard-coded in source.
    """

    entries: List[LeagueEnvEntry] = []

    for env_key, env_value in os.environ.items():
        match = _LEAGUE_ENV_PATTERN.match(env_key)

        if not match or not env_value:
            continue

        entries.append(
            LeagueEnvEntry(
                league_key=match.group("league_key"),
                season=int(match.group("season")),
                sleeper_league_id=env_value.strip(),
            )
        )

    return sorted(entries, key=lambda e: (e.league_key, e.season))


DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./data/fantasy.db")

PLAYERS_CSV_PATH = os.getenv("PLAYERS_CSV_PATH", "data/players.csv")
PLAYER_IDS_CSV_PATH = os.getenv("PLAYER_IDS_CSV_PATH", "data/player_ids.csv")

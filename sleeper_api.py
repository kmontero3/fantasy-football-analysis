"""
Sleeper API Client
------------------

Base URL:
    https://api.sleeper.app/v1/

Documentation:
    https://docs.sleeper.com/

The Sleeper API is read-only and does not require authentication.

Recommended usage:
    from sleeper_api import SleeperAPI

    sleeper = SleeperAPI()

    user = sleeper.get_user("username")
    leagues = sleeper.get_user_leagues(user["user_id"], season=sleeper.get_nfl_state()["season"])
    league = sleeper.get_league(leagues[0]["league_id"])
    rosters = sleeper.get_rosters(league["league_id"])
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import requests


class SleeperAPIError(Exception):
    """Raised when the Sleeper API returns an error."""

    def __init__(
        self,
        status_code: int,
        message: str,
        url: Optional[str] = None,
    ):
        self.status_code = status_code
        self.message = message
        self.url = url

        super().__init__(
            f"Sleeper API error {status_code}: {message}"
            + (f" | URL: {url}" if url else "")
        )


class SleeperAPI:
    """
    Client for the Sleeper REST API.

    The API is read-only and does not require authentication.
    """

    BASE_URL = "https://api.sleeper.app/v1"

    def __init__(
        self,
        timeout: int = 30,
        session: Optional[requests.Session] = None,
    ):
        self.timeout = timeout
        self.session = session or requests.Session()

        self.session.headers.update(
            {
                "Accept": "application/json",
                "User-Agent": "SleeperAPIClient/1.0",
            }
        )

    # ============================================================
    # Core HTTP functionality
    # ============================================================

    def _get(
        self,
        endpoint: str,
        params: Optional[Dict[str, Any]] = None,
    ) -> Any:
        """
        Execute a GET request against the Sleeper API.

        All endpoint-specific methods should eventually call this
        method so HTTP handling is centralized.
        """

        endpoint = endpoint.lstrip("/")
        url = f"{self.BASE_URL}/{endpoint}"

        try:
            response = self.session.get(
                url,
                params=params,
                timeout=self.timeout,
            )

        except requests.RequestException as exc:
            raise SleeperAPIError(
                status_code=0,
                message=str(exc),
                url=url,
            ) from exc

        if not response.ok:
            try:
                error_body = response.json()
            except ValueError:
                error_body = response.text

            raise SleeperAPIError(
                status_code=response.status_code,
                message=str(error_body),
                url=response.url,
            )

        try:
            return response.json()

        except ValueError as exc:
            raise SleeperAPIError(
                status_code=response.status_code,
                message="Response was not valid JSON.",
                url=response.url,
            ) from exc

    # ============================================================
    # USER ENDPOINTS
    # ============================================================

    def get_user(self, user_id_or_username: str) -> Dict[str, Any]:
        """
        Get a Sleeper user.

        Endpoint:
            GET /user/{user_id_or_username}

        Parameters:
            user_id_or_username: Sleeper username or user ID
        """

        return self._get(
            f"user/{user_id_or_username}"
        )

    def get_user_leagues(
        self,
        user_id: str,
        season: int | str,
        sport: str = "nfl",
    ) -> List[Dict[str, Any]]:
        """
        Get all leagues for a user.

        Endpoint:
            GET /user/{user_id}/leagues/{sport}/{season}

        ``season`` must be passed explicitly -- callers that need "the
        current season" should source it from ``get_nfl_state()`` rather
        than relying on a hard-coded default here.
        """

        return self._get(
            f"user/{user_id}/leagues/{sport}/{season}"
        )

    def get_user_drafts(
        self,
        user_id: str,
        season: int | str,
        sport: str = "nfl",
    ) -> List[Dict[str, Any]]:
        """
        Get all drafts for a user.

        Endpoint:
            GET /user/{user_id}/drafts/{sport}/{season}

        ``season`` must be passed explicitly -- callers that need "the
        current season" should source it from ``get_nfl_state()`` rather
        than relying on a hard-coded default here.
        """

        return self._get(
            f"user/{user_id}/drafts/{sport}/{season}"
        )

    # ============================================================
    # LEAGUE ENDPOINTS
    # ============================================================

    def get_league(
        self,
        league_id: str,
    ) -> Dict[str, Any]:
        """
        Get information about a specific league.

        Endpoint:
            GET /league/{league_id}
        """

        return self._get(
            f"league/{league_id}"
        )

    def get_rosters(
        self,
        league_id: str,
    ) -> List[Dict[str, Any]]:
        """
        Get all rosters in a league.

        Endpoint:
            GET /league/{league_id}/rosters
        """

        return self._get(
            f"league/{league_id}/rosters"
        )

    def get_league_users(
        self,
        league_id: str,
    ) -> List[Dict[str, Any]]:
        """
        Get all users in a league.

        Endpoint:
            GET /league/{league_id}/users
        """

        return self._get(
            f"league/{league_id}/users"
        )

    def get_matchups(
        self,
        league_id: str,
        week: int,
    ) -> List[Dict[str, Any]]:
        """
        Get all matchups for a league week.

        Endpoint:
            GET /league/{league_id}/matchups/{week}
        """

        return self._get(
            f"league/{league_id}/matchups/{week}"
        )

    def get_winners_bracket(
        self,
        league_id: str,
    ) -> List[Dict[str, Any]]:
        """
        Get the winners playoff bracket.

        Endpoint:
            GET /league/{league_id}/winners_bracket
        """

        return self._get(
            f"league/{league_id}/winners_bracket"
        )

    def get_losers_bracket(
        self,
        league_id: str,
    ) -> List[Dict[str, Any]]:
        """
        Get the losers playoff bracket.

        Endpoint:
            GET /league/{league_id}/losers_bracket
        """

        return self._get(
            f"league/{league_id}/losers_bracket"
        )

    def get_transactions(
        self,
        league_id: str,
        week: int,
    ) -> List[Dict[str, Any]]:
        """
        Get transactions for a league week.

        Includes trades, waivers, free-agent transactions, etc.

        Endpoint:
            GET /league/{league_id}/transactions/{round}
        """

        return self._get(
            f"league/{league_id}/transactions/{week}"
        )

    def get_traded_picks(
        self,
        league_id: str,
    ) -> List[Dict[str, Any]]:
        """
        Get all traded picks in a league.

        Endpoint:
            GET /league/{league_id}/traded_picks
        """

        return self._get(
            f"league/{league_id}/traded_picks"
        )

    # ============================================================
    # NFL / SPORT STATE
    # ============================================================

    def get_sport_state(
        self,
        sport: str = "nfl",
    ) -> Dict[str, Any]:
        """
        Get the current state of a sport.

        Endpoint:
            GET /state/{sport}

        Example:
            state = sleeper.get_sport_state("nfl")
        """

        return self._get(
            f"state/{sport}"
        )

    # Convenience alias for NFL
    def get_nfl_state(self) -> Dict[str, Any]:
        """
        Get current NFL state.

        Endpoint:
            GET /state/nfl
        """

        return self.get_sport_state("nfl")

    # ============================================================
    # DRAFT ENDPOINTS
    # ============================================================

    def get_league_drafts(
        self,
        league_id: str,
    ) -> List[Dict[str, Any]]:
        """
        Get all drafts associated with a league.

        Endpoint:
            GET /league/{league_id}/drafts
        """

        return self._get(
            f"league/{league_id}/drafts"
        )

    def get_draft(
        self,
        draft_id: str,
    ) -> Dict[str, Any]:
        """
        Get a specific draft.

        Endpoint:
            GET /draft/{draft_id}
        """

        return self._get(
            f"draft/{draft_id}"
        )

    def get_draft_picks(
        self,
        draft_id: str,
    ) -> List[Dict[str, Any]]:
        """
        Get all picks in a draft.

        Endpoint:
            GET /draft/{draft_id}/picks
        """

        return self._get(
            f"draft/{draft_id}/picks"
        )

    def get_draft_traded_picks(
        self,
        draft_id: str,
    ) -> List[Dict[str, Any]]:
        """
        Get all traded picks in a draft.

        Endpoint:
            GET /draft/{draft_id}/traded_picks
        """

        return self._get(
            f"draft/{draft_id}/traded_picks"
        )

    # ============================================================
    # PLAYER ENDPOINTS
    # ============================================================

    def get_players(
        self,
        sport: str = "nfl",
        position: Optional[str] = None,
        active: Optional[bool] = None,
    ) -> Dict[str, Any]:
        """
        Get the Sleeper player map.

        Endpoint:
            GET /players/{sport}

        Optional filters:
            position = "QB", "RB", "WR", "TE", etc.
            active = True

        IMPORTANT:
            Sleeper states that the complete player map is roughly
            5 MB and should generally only be downloaded once per day.
        """

        params = {}

        if position is not None:
            params["position"] = position

        if active is not None:
            params["active"] = str(active).lower()

        return self._get(
            f"players/{sport}",
            params=params or None,
        )

    def get_trending_players(
        self,
        sport: str = "nfl",
        trend_type: str = "add",
        lookback_hours: int = 24,
        limit: int = 25,
    ) -> List[Dict[str, Any]]:
        """
        Get trending players based on add/drop activity.

        Endpoint:
            GET /players/{sport}/trending/{type}

        trend_type:
            "add" or "drop"
        """

        if trend_type not in {"add", "drop"}:
            raise ValueError(
                "trend_type must be either 'add' or 'drop'."
            )

        params = {
            "lookback_hours": lookback_hours,
            "limit": limit,
        }

        return self._get(
            f"players/{sport}/trending/{trend_type}",
            params=params,
        )


# ================================================================
# Example usage
# ================================================================

if __name__ == "__main__":

    sleeper = SleeperAPI()

    # ------------------------------------------------------------
    # 1. Get user
    # ------------------------------------------------------------

    # user = sleeper.get_user("your_username")
    # print(user)

    # ------------------------------------------------------------
    # 2. Get current NFL state
    # ------------------------------------------------------------

    nfl_state = sleeper.get_nfl_state()

    print("NFL State:")
    print(nfl_state)

    # ------------------------------------------------------------
    # 3. Get leagues
    # ------------------------------------------------------------

    # user_id = user["user_id"]
    # leagues = sleeper.get_user_leagues(
    #     user_id=user_id,
    #     sport="nfl",
    #     season=2026,
    # )
    #
    # for league in leagues:
    #     print(
    #         league["league_id"],
    #         league["name"],
    #         league["season"],
    #     )

    # ------------------------------------------------------------
    # 4. Get league information
    # ------------------------------------------------------------

    # league_id = "YOUR_LEAGUE_ID"
    # league = sleeper.get_league(league_id)
    # print(league)

    # ------------------------------------------------------------
    # 5. Get rosters
    # ------------------------------------------------------------

    # rosters = sleeper.get_rosters(league_id)
    # print(rosters)

    # ------------------------------------------------------------
    # 6. Get a specific week's matchups
    # ------------------------------------------------------------

    # week = 4
    # matchups = sleeper.get_matchups(
    #     league_id,
    #     week,
    # )
    # print(matchups)

    # ------------------------------------------------------------
    # 7. Get players
    # ------------------------------------------------------------

    # IMPORTANT:
    # Don't repeatedly call the full player endpoint.
    #
    # players = sleeper.get_players("nfl")
    #
    # Example lookup:
    #
    # player = players["4046"]
    # print(player)

    # ------------------------------------------------------------
    # 8. Get active QBs only
    # ------------------------------------------------------------

    # qbs = sleeper.get_players(
    #     sport="nfl",
    #     position="QB",
    #     active=True,
    # )
    #
    # for player_id, player in qbs.items():
    #     print(
    #         player_id,
    #         player.get("first_name"),
    #         player.get("last_name"),
    #         player.get("team"),
    #     )

    # ------------------------------------------------------------
    # 9. Trending players
    # ------------------------------------------------------------

    # trending = sleeper.get_trending_players(
    #     sport="nfl",
    #     trend_type="add",
    #     lookback_hours=24,
    #     limit=25,
    # )
    #
    # print(trending)


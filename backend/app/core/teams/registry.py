"""
Team registry for dynamic team loading.
"""
import logging
from typing import Dict, List, Optional

from fastapi import APIRouter

from app.core.teams.base import BaseTeam

logger = logging.getLogger(__name__)


class TeamRegistry:
    """Central registry for all teams. Used by main.py to discover and load teams."""

    REQUIRED_CLASS_ATTRS = ("id", "name", "description", "icon")

    def __init__(self):
        self._teams: Dict[str, BaseTeam] = {}
        self._default_team_id: Optional[str] = None

    def register(self, team: BaseTeam) -> None:
        """Register a team. First registered team becomes the default.

        Validates required class attributes and analysis-phase ordering up front
        so a misconfigured team fails loudly at startup instead of with an
        AttributeError deep in a later request.
        """
        missing = [
            attr
            for attr in self.REQUIRED_CLASS_ATTRS
            if not getattr(team, attr, None)
        ]
        if missing:
            raise TypeError(
                f"Team {type(team).__name__} missing required class attributes: "
                f"{missing}. Set them as class-level values on the subclass."
            )

        phases = team.get_analysis_phases()
        orders = [phase.order for phase in phases]
        if len(set(orders)) != len(orders):
            duplicates = sorted({o for o in orders if orders.count(o) > 1})
            raise ValueError(
                f"Team '{team.id}' has duplicate AnalysisPhase.order values: "
                f"{duplicates}. Phase ordering must be unique so phases render "
                f"deterministically."
            )

        if team.id in self._teams:
            logger.warning(f"Team '{team.id}' already registered, replacing")
        self._teams[team.id] = team
        if self._default_team_id is None:
            self._default_team_id = team.id
        logger.info(f"Registered team: {team.name} ({team.id})")

    def get(self, team_id: str) -> BaseTeam:
        """Get a team by ID. Raises KeyError if not found."""
        if team_id not in self._teams:
            raise KeyError(f"Team '{team_id}' not registered. Available: {list(self._teams.keys())}")
        return self._teams[team_id]

    def get_default(self) -> Optional[BaseTeam]:
        """Get the default team (first registered)."""
        if self._default_team_id:
            return self._teams.get(self._default_team_id)
        return None

    @property
    def default_team_id(self) -> Optional[str]:
        return self._default_team_id

    def list_teams(self) -> List[dict]:
        """Return summary of all registered teams."""
        return [
            {
                "id": t.id,
                "name": t.name,
                "description": t.description,
                "icon": t.icon,
            }
            for t in self._teams.values()
        ]

    def get_all_routes(self) -> List[APIRouter]:
        """Collect team-specific routes from all registered teams."""
        routes = []
        for team in self._teams.values():
            try:
                team_routes = team.get_routes()
                routes.extend(team_routes)
                logger.info(f"Loaded {len(team_routes)} routes from team '{team.id}'")
            except Exception as e:
                logger.error(f"Failed to get routes from team '{team.id}': {e}")
        return routes

    def get_platform_manifest(self) -> dict:
        """Build the full platform manifest for the frontend."""
        teams = []
        for team in self._teams.values():
            try:
                teams.append(team.get_frontend_manifest())
            except Exception as e:
                logger.error(f"Failed to get manifest from team '{team.id}': {e}")
        return {
            "teams": teams,
            "default_team": self._default_team_id,
            "plugins": [],  # Populated later by plugin registry
        }

    async def startup_all(self) -> None:
        """Call on_startup for all registered teams."""
        for team in self._teams.values():
            try:
                await team.on_startup()
                logger.info(f"Team '{team.id}' startup complete")
            except Exception as e:
                logger.error(f"Team '{team.id}' startup failed: {e}")

    async def shutdown_all(self) -> None:
        """Call on_shutdown for all registered teams."""
        for team in self._teams.values():
            try:
                await team.on_shutdown()
            except Exception as e:
                logger.error(f"Team '{team.id}' shutdown failed: {e}")

    def __len__(self) -> int:
        return len(self._teams)

    def __contains__(self, team_id: str) -> bool:
        return team_id in self._teams

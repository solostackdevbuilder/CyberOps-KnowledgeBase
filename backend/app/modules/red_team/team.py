"""
Red Team - first BaseTeam implementation.
Wraps the existing red_team module into the team contract.
"""
from typing import List, Type

from fastapi import APIRouter
from pydantic import BaseModel

from app.core.teams.base import AnalysisPhase, BaseTeam, TeamPrompts
from app.modules.red_team.models import ExpertAnalysis
from app.modules.red_team.prompts_v2 import (
    EXPERT_ANALYSIS_PROMPT_V2,
    FAA_ANALYSIS_PROMPT_V2,
    METADATA_EXTRACTION_PROMPT_V2,
    QUERY_SYSTEM_PROMPT_ALL_V2,
    QUERY_SYSTEM_PROMPT_SINGLE_V2,
)


class RedTeam(BaseTeam):
    """Red Team operations - offensive security, pen testing, adversary simulation."""

    id = "red_team"
    name = "Red Team Operations"
    description = "Offensive security operations, penetration testing, and adversary simulation"
    icon = "Crosshair"

    KILL_CHAIN = [
        AnalysisPhase(name="Reconnaissance", description="Target research and information gathering", order=1),
        AnalysisPhase(name="Initial Access", description="Gaining entry to target systems", order=2),
        AnalysisPhase(name="Execution", description="Running adversary-controlled code", order=3),
        AnalysisPhase(name="Privilege Escalation", description="Gaining higher-level permissions", order=4),
        AnalysisPhase(name="Persistence", description="Maintaining access across restarts", order=5),
        AnalysisPhase(name="Defense Evasion", description="Avoiding detection", order=6),
        AnalysisPhase(name="Credential Access", description="Stealing credentials", order=7),
        AnalysisPhase(name="Discovery", description="Exploring the environment", order=8),
        AnalysisPhase(name="Lateral Movement", description="Moving through the network", order=9),
        AnalysisPhase(name="Collection", description="Gathering target data", order=10),
        AnalysisPhase(name="Exfiltration", description="Stealing data out", order=11),
        AnalysisPhase(name="Impact", description="Disrupting availability or integrity", order=12),
    ]

    def get_analysis_phases(self) -> List[AnalysisPhase]:
        return self.KILL_CHAIN

    def get_prompts(self) -> TeamPrompts:
        return TeamPrompts(
            expert_analysis=EXPERT_ANALYSIS_PROMPT_V2,
            faa_analysis=FAA_ANALYSIS_PROMPT_V2,
            query_single=QUERY_SYSTEM_PROMPT_SINGLE_V2,
            query_all=QUERY_SYSTEM_PROMPT_ALL_V2,
            metadata_extraction=METADATA_EXTRACTION_PROMPT_V2,
        )

    def get_expert_analysis_model(self) -> Type[BaseModel]:
        return ExpertAnalysis

    def get_routes(self) -> List[APIRouter]:
        # Import here to avoid circular imports at module load time
        from app.modules.red_team.routes import detection_strategies_router
        return [detection_strategies_router]

    def get_classifications(self) -> List[str]:
        return ["action", "finding"]

    def get_frontend_manifest(self) -> dict:
        base = super().get_frontend_manifest()
        base["routes"] = [
            {"path": "/", "name": "Sessions", "icon": "Activity"},
            {"path": "/create", "name": "New Session", "icon": "Plus"},
            {"path": "/operations", "name": "Operations", "icon": "FolderOpen"},
            {"path": "/query", "name": "Query", "icon": "Search"},
            {"path": "/insights", "name": "Insights", "icon": "BarChart3"},
            {"path": "/timeline", "name": "Timeline", "icon": "Clock"},
        ]
        base["nav_items"] = [
            {"path": "/", "label": "Sessions", "icon": "Activity", "shortcut": "G+S"},
            {"path": "/operations", "label": "Operations", "icon": "FolderOpen", "shortcut": "G+O"},
            {"path": "/query", "label": "Query", "icon": "Search", "shortcut": "G+Q"},
            {"path": "/insights", "label": "Insights", "icon": "BarChart3", "shortcut": "G+I"},
        ]
        return base

    async def on_startup(self) -> None:
        """Load cached insights on startup."""
        try:
            from app.modules.red_team.routes import _load_cache_from_disk, _invalidate_cache
            await _load_cache_from_disk()
            _invalidate_cache()
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning(f"Failed to load red team cache: {e}")

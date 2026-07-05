"""
BaseTeam abstract class.
Every team (Red Team, CTI, Compliance, Arch Review) must implement this contract.
"""
from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Type

from fastapi import APIRouter
from pydantic import BaseModel


class AnalysisPhase(BaseModel):
    """A phase in a team's analysis framework."""
    name: str
    description: str
    order: int


class TeamPrompts(BaseModel):
    """Prompt templates for a team."""
    expert_analysis: str
    faa_analysis: str
    query_single: str
    query_all: str
    metadata_extraction: str


class BaseTeam(ABC):
    """Contract that every team must implement."""

    # Identity
    id: str
    name: str
    description: str
    icon: str  # Lucide icon name for frontend

    @abstractmethod
    def get_analysis_phases(self) -> List[AnalysisPhase]:
        """Return the ordered phases for this team's analysis framework.

        Examples:
            Red Team: Kill chain (Recon -> Impact)
            CTI: Diamond Model (Adversary -> Victim)
            Compliance: NIST CSF (Identify -> Recover)
        """
        pass

    @abstractmethod
    def get_prompts(self) -> TeamPrompts:
        """Return team-specific prompt templates for LLM interactions."""
        pass

    @abstractmethod
    def get_expert_analysis_model(self) -> Type[BaseModel]:
        """Return the Pydantic model for this team's expert analysis output.

        Red Team returns ExpertAnalysis (kill chain progress).
        CTI would return ThreatAnalysis (diamond model, IOCs).
        """
        pass

    @abstractmethod
    def get_routes(self) -> List[APIRouter]:
        """Return team-specific API routers (beyond standard CRUD).

        These are routes unique to this team, not the shared
        operations/sessions/query/FAA routes.
        """
        pass

    @abstractmethod
    def get_classifications(self) -> List[str]:
        """Return valid FAA classification types for this team.

        Red Team: ["action", "finding"]
        CTI: ["indicator", "ttp", "campaign_link"]
        """
        pass

    def get_frontend_manifest(self) -> dict:
        """Return manifest telling the frontend what this team provides."""
        return {
            "team_id": self.id,
            "name": self.name,
            "description": self.description,
            "icon": self.icon,
            "analysis_phases": [p.model_dump() for p in self.get_analysis_phases()],
            "classifications": self.get_classifications(),
            "routes": [],
            "nav_items": [],
        }

    def enrich_query_context(self, query: str, context: str) -> str:
        """Optionally transform query context before sending to LLM.

        Override to add team-specific context enrichment.
        """
        return context

    def validate_analysis_output(self, raw_output: dict) -> dict:
        """Post-process LLM output for team-specific validation.

        Override to add team-specific output validation/cleanup.
        """
        return raw_output

    async def on_startup(self) -> None:
        """Called during app startup. Override for team-specific initialization."""
        pass

    async def on_shutdown(self) -> None:
        """Called during app shutdown. Override for team-specific cleanup."""
        pass

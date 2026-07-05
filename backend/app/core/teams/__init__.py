"""
Team framework for CyberOps platform.
Teams provide domain-specific lenses (Red Team, CTI, Compliance, etc.)
on top of the shared operation/session/FAA infrastructure.
"""
from app.core.teams.base import BaseTeam, AnalysisPhase, TeamPrompts
from app.core.teams.registry import TeamRegistry

__all__ = ["BaseTeam", "AnalysisPhase", "TeamPrompts", "TeamRegistry"]

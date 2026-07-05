"""
Red team models.

Generic models (Operation, Session, FAA, GeneralInsights) are defined in
app.core.models and re-exported here for backward compatibility.

This file defines only red-team-specific models:
- ExpertAnalysis (kill chain progress, detection strategies)
- InsightsResponse (combines GeneralInsights + ExpertAnalysis)
- CachedInsights (typed version with InsightsResponse)
"""
from datetime import datetime
from typing import Dict, List, Literal, Optional, Union

from pydantic import BaseModel, ConfigDict, Field

# Re-export all core models so existing imports from this file still work
from app.core.models.operation import (  # noqa: F401
    Operation,
    OperationBase,
    OperationCreate,
    OperationUpdate,
)
from app.core.models.session import (  # noqa: F401
    Screenshot,
    ScreenshotExtraction,
    Session,
    SessionBase,
    SessionCreate,
    SessionUpdate,
)
from app.core.models.faa import (  # noqa: F401
    FAAItem,
    FAAItemCreate,
    FAAItemUpdate,
)
from app.core.models.insights import (  # noqa: F401
    GeneralInsights,
    InsightsGenerateRequest,
    NextStep,
)


# ============================================================================
# Red Team Specific: Expert Analysis (Kill Chain)
# ============================================================================

class ExpertAnalysis(BaseModel):
    """Expert analysis model with AI-powered assessment.

    This is red-team-specific: it uses the cyber kill chain framework
    and MITRE ATT&CK detection strategies.
    """
    current_phase: str = Field(
        ...,
        description="Current phase of the cyber kill chain (e.g., 'Post-Exploitation')"
    )
    phase_confidence: str = Field(
        ...,
        description="Confidence level in phase assessment: High, Medium, or Low"
    )
    kill_chain_progress: dict = Field(
        ...,
        description="Kill chain progress mapping (phase name -> 'completed'/'current'/'next')"
    )
    progress_summary: str = Field(
        ...,
        description="2-3 sentence summary of what has been accomplished"
    )
    gaps_identified: List[str] = Field(
        default_factory=list,
        description="List of specific gaps or missing activities"
    )
    recommendations: List[str] = Field(
        default_factory=list,
        description="List of 3-5 prioritized recommendations for next actions"
    )
    next_steps: List[NextStep] = Field(
        default_factory=list,
        description="List of specific next steps with priority and reasoning"
    )
    risk_assessment: str = Field(
        ...,
        description="Assessment of current risk level and exposure"
    )
    detection_risk_assessment: Optional[str] = Field(
        None,
        description="Assessment of how likely the operation is to be detected based on detection strategies"
    )
    recommended_detection_strategies: List[str] = Field(
        default_factory=list,
        description="List of recommended detection strategy IDs (DET####) for defenders"
    )
    detection_coverage_gaps: List[str] = Field(
        default_factory=list,
        description="List of techniques used that have no detection strategies available"
    )
    evidence_sessions: List[str] = Field(
        default_factory=list,
        description="List of session IDs that support the conclusions"
    )
    generated_at: datetime = Field(..., description="When this analysis was generated")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "current_phase": "Lateral Movement",
                "phase_confidence": "High",
                "kill_chain_progress": {
                    "Reconnaissance": "completed",
                    "Initial Access": "completed",
                    "Execution": "completed",
                    "Privilege Escalation": "completed",
                    "Persistence": "current",
                    "Defense Evasion": "next",
                    "Credential Access": "next",
                    "Discovery": "current",
                    "Lateral Movement": "current",
                    "Collection": "next",
                    "Exfiltration": "next",
                    "Impact": "next"
                },
                "progress_summary": "The operation has successfully gained initial access and established persistence. Lateral movement has begun but is limited.",
                "gaps_identified": [
                    "No persistence established",
                    "Limited lateral movement",
                    "No credential harvesting attempted"
                ],
                "recommendations": [
                    "Establish persistence mechanisms",
                    "Expand lateral movement to additional systems",
                    "Begin credential harvesting"
                ],
                "next_steps": [
                    {
                        "step": "Establish scheduled task persistence",
                        "priority": "High",
                        "reasoning": "Current access is temporary and may be lost"
                    }
                ],
                "risk_assessment": "Medium risk - access established but not fully persistent",
                "evidence_sessions": ["session-123", "session-456"],
                "generated_at": "2024-01-17T10:30:00"
            }
        }
    )


# ============================================================================
# Red Team Specific: Insights Response (combines general + expert)
# ============================================================================

class InsightsResponse(BaseModel):
    """Response model combining general insights and expert analysis."""
    general_insights: GeneralInsights = Field(..., description="General statistics and insights")
    expert_analysis: ExpertAnalysis = Field(..., description="AI-powered expert analysis")
    scope: Union[str, List[str]] = Field(
        ...,
        description="Operation ID(s) or 'all' that these insights cover"
    )
    generated_at: datetime = Field(..., description="When these insights were generated")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "general_insights": {
                    "total_sessions": 15,
                    "total_targets": 8,
                    "total_findings": 12,
                    "total_tools": 5,
                    "top_tools": [{"name": "nmap", "count": 10}],
                    "targets_list": ["192.168.1.100"],
                    "findings_summary": [{"finding": "Open port 22", "count": 3}],
                    "operators": ["John Doe"],
                    "timeline_data": [{"date": "2024-01-15", "session_count": 5}],
                    "generated_at": "2024-01-17T10:30:00"
                },
                "expert_analysis": {
                    "current_phase": "Lateral Movement",
                    "phase_confidence": "High",
                    "kill_chain_progress": {},
                    "progress_summary": "Operation in progress",
                    "gaps_identified": [],
                    "recommendations": [],
                    "next_steps": [],
                    "risk_assessment": "Low risk",
                    "evidence_sessions": [],
                    "generated_at": "2024-01-17T10:30:00"
                },
                "scope": "op-123",
                "generated_at": "2024-01-17T10:30:00"
            }
        }
    )


class CachedInsights(BaseModel):
    """Model for cached insights with metadata (red-team typed version)."""
    insights: InsightsResponse = Field(..., description="Cached insights response")
    cache_key: str = Field(..., description="Cache key (hash of operation_ids)")
    cached_at: datetime = Field(..., description="When the insights were cached")
    expires_at: datetime = Field(..., description="When the cache expires")

"""
Core insights models.
GeneralInsights and base insight structures used by all teams.
Team-specific analysis models (e.g., ExpertAnalysis with kill chain) live in their team module.
"""
from datetime import datetime
from typing import List, Union

from pydantic import BaseModel, ConfigDict, Field


class GeneralInsights(BaseModel):
    """General insights model with statistics and aggregated data."""
    total_sessions: int = Field(..., description="Total number of sessions analyzed")
    total_targets: int = Field(..., description="Total number of unique targets")
    total_findings: int = Field(..., description="Total number of unique findings")
    total_tools: int = Field(..., description="Total number of unique tools")
    top_tools: List[dict] = Field(
        default_factory=list,
        description="Top 10 most used tools with counts (format: [{'name': str, 'count': int}])"
    )
    targets_list: List[str] = Field(
        default_factory=list,
        description="List of all unique targets discovered"
    )
    findings_summary: List[dict] = Field(
        default_factory=list,
        description="Findings grouped and counted (format: [{'finding': str, 'count': int}])"
    )
    operators: List[str] = Field(
        default_factory=list,
        description="List of unique operators who conducted sessions"
    )
    timeline_data: List[dict] = Field(
        default_factory=list,
        description="Timeline data grouped by date (format: [{'date': str, 'session_count': int}])"
    )
    generated_at: datetime = Field(..., description="When these insights were generated")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "total_sessions": 15,
                "total_targets": 8,
                "total_findings": 12,
                "total_tools": 5,
                "top_tools": [
                    {"name": "nmap", "count": 10},
                    {"name": "metasploit", "count": 5}
                ],
                "targets_list": ["192.168.1.100", "example.com"],
                "findings_summary": [
                    {"finding": "Open port 22", "count": 3},
                    {"finding": "Weak SSH configuration", "count": 2}
                ],
                "operators": ["John Doe", "Jane Smith"],
                "timeline_data": [
                    {"date": "2024-01-15", "session_count": 5},
                    {"date": "2024-01-16", "session_count": 10}
                ],
                "generated_at": "2024-01-17T10:30:00"
            }
        }
    )


class NextStep(BaseModel):
    """Model for next step recommendation."""
    step: str = Field(..., description="Description of the next step")
    priority: str = Field(..., description="Priority level: High, Medium, or Low")
    reasoning: str = Field(..., description="Reasoning for this recommendation")


class InsightsGenerateRequest(BaseModel):
    """Request model for generating insights."""
    operation_ids: Union[List[str], str] = Field(
        ...,
        description="List of operation IDs to analyze, or 'all' for all operations"
    )


class CachedInsights(BaseModel):
    """Model for cached insights with metadata.
    Note: The 'insights' field type varies by team (each team has its own InsightsResponse).
    This base version stores the raw dict. Teams can subclass with typed field.
    """
    insights: dict = Field(..., description="Cached insights response")
    cache_key: str = Field(..., description="Cache key (hash of operation_ids)")
    cached_at: datetime = Field(..., description="When the insights were cached")
    expires_at: datetime = Field(..., description="When the cache expires")

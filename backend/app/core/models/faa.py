"""
Core Findings and Actions (FAA) models.
These are platform-generic models used by all teams.
"""
from datetime import datetime
from typing import List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


class FAAItem(BaseModel):
    """Model for Findings and Actions item."""
    id: str = Field(..., description="Unique FAA item identifier")
    session_id: str = Field(..., description="ID of the session this item belongs to")
    classification: Literal["action", "finding"] = Field(..., description="Classification: action or finding")
    content: str = Field(..., description="Command/activity description")
    output: Optional[str] = Field(None, description="Command output or finding details")
    mitre_technique: Optional[str] = Field(None, description="MITRE ATT&CK technique (e.g., 'T1046 - Network Service Discovery')")
    mitre_tactic: Optional[str] = Field(None, description="MITRE ATT&CK tactic (e.g., 'Discovery', 'Credential Access')")
    detection_strategy_ids: List[str] = Field(
        default_factory=list,
        description="MITRE ATT&CK Detection Strategy IDs (DET####) that can detect this technique"
    )
    severity: Optional[Literal["critical", "high", "medium", "low"]] = Field(None, description="Severity level (for findings only)")
    timestamp: datetime = Field(..., description="When the activity occurred")
    source: Literal["terminal", "screenshot", "manual"] = Field(..., description="Source of the item")
    confidence_score: float = Field(..., ge=0.0, le=1.0, description="Confidence score from LLM (0.0 to 1.0)")
    manually_corrected: bool = Field(default=False, description="Whether this item was manually corrected")
    notes: Optional[str] = Field(None, description="Operator notes")
    created_at: datetime = Field(..., description="When the item was created")
    updated_at: datetime = Field(..., description="When the item was last updated")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "id": "faa-123",
                "session_id": "session-123",
                "classification": "finding",
                "content": "Found credentials in config file",
                "output": "username=admin, password=secret123",
                "mitre_technique": "T1552.001 - Credentials in Files",
                "mitre_tactic": "Credential Access",
                "severity": "high",
                "timestamp": "2024-01-15T10:35:00",
                "source": "terminal",
                "confidence_score": 0.95,
                "manually_corrected": False,
                "notes": "Credentials found in web.config",
                "created_at": "2024-01-15T10:40:00",
                "updated_at": "2024-01-15T10:40:00"
            }
        }
    )


class FAAItemCreate(BaseModel):
    """Model for creating a new FAA item (manual creation)."""
    session_id: str = Field(..., description="ID of the session")
    classification: Literal["action", "finding"] = Field(..., description="Classification: action or finding")
    content: str = Field(..., description="Command/activity description")
    output: Optional[str] = Field(None, description="Command output or finding details")
    mitre_technique: Optional[str] = Field(None, description="MITRE ATT&CK technique")
    mitre_tactic: Optional[str] = Field(None, description="MITRE ATT&CK tactic")
    severity: Optional[Literal["critical", "high", "medium", "low"]] = Field(None, description="Severity level (for findings only)")
    timestamp: datetime = Field(..., description="When the activity occurred")
    source: Literal["terminal", "screenshot", "manual"] = Field(default="manual", description="Source of the item")
    notes: Optional[str] = Field(None, description="Operator notes")


class FAAItemUpdate(BaseModel):
    """Model for updating an existing FAA item."""
    classification: Optional[Literal["action", "finding"]] = None
    content: Optional[str] = None
    output: Optional[str] = None
    mitre_technique: Optional[str] = None
    mitre_tactic: Optional[str] = None
    severity: Optional[Literal["critical", "high", "medium", "low"]] = None
    notes: Optional[str] = None

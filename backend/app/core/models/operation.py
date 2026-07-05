"""
Core operation models.
These are platform-generic models used by all teams.
"""
from datetime import datetime
from typing import List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


class OperationBase(BaseModel):
    """Base operation model with common fields."""
    name: str = Field(..., description="Operation name")
    description: Optional[str] = Field(None, description="Optional operation description")


class OperationCreate(OperationBase):
    """Model for creating a new operation."""
    pass


class Operation(OperationBase):
    """Complete operation model with all fields."""
    id: str = Field(..., description="Unique operation identifier")
    created_at: datetime = Field(..., description="When the operation was created")
    status: Literal["active", "archived"] = Field(
        default="active",
        description="Operation status: active or archived"
    )
    session_ids: List[str] = Field(
        default_factory=list,
        description="List of session IDs belonging to this operation"
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "id": "op-123",
                "name": "Q1 2024 Penetration Test",
                "description": "Quarterly penetration testing engagement",
                "created_at": "2024-01-15T10:30:00",
                "status": "active",
                "session_ids": ["session-123", "session-456"]
            }
        }
    )


class OperationUpdate(BaseModel):
    """Model for updating an existing operation."""
    name: Optional[str] = None
    description: Optional[str] = None
    status: Optional[Literal["active", "archived"]] = None

"""
Core session models.
These are platform-generic models used by all teams.
"""
from datetime import datetime
from typing import Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field


class Screenshot(BaseModel):
    """Model for screenshot metadata."""
    filename: str = Field(..., description="Name of the screenshot file")
    timestamp: datetime = Field(..., description="When the screenshot was taken")
    description: Optional[str] = Field(None, description="Optional description of the screenshot")
    source_url: Optional[str] = Field(None, description="URL the screenshot was captured from (browser extension)")
    source_title: Optional[str] = Field(None, description="Page title the screenshot was captured from (browser extension)")
    source_domain: Optional[str] = Field(None, description="Domain derived from source_url for grouping/filtering")


class ScreenshotExtraction(BaseModel):
    """Model for screenshot text extraction results."""
    filename: str = Field(..., description="Name of the screenshot file")
    path: str = Field(..., description="Path to the screenshot file")
    uploaded_at: datetime = Field(..., description="When the screenshot was uploaded")
    extracted_text: Optional[str] = Field(None, description="Raw text extracted from the image")
    analysis: Optional[str] = Field(None, description="Brief description of what the image shows")
    extraction_status: str = Field(..., description="Status: success, failed, no_text, not_supported")
    error_message: Optional[str] = Field(None, description="Error message if extraction failed")


class SessionBase(BaseModel):
    """Base session model with common fields."""
    title: str = Field(..., description="Session title")
    description: Optional[str] = Field(None, description="Optional session description")
    tags: List[str] = Field(default_factory=list, description="Tags for categorizing the session")
    targets: Optional[List[str]] = Field(None, description="List of targets (IPs, domains, hostnames) - AI-extracted")
    tools: Optional[List[str]] = Field(None, description="List of tools used - AI-extracted")
    findings: Optional[List[str]] = Field(None, description="List of key findings - AI-extracted")
    # Measurement-week tagging (2026-04 onward). Both optional.
    # primary_tool: the tool that produced most of this session's content, for
    # ranking which tool adapter to build next. Free text so operators can
    # tag new/obscure tools without a model migration.
    primary_tool: Optional[str] = Field(None, description="Primary tool behind this session (e.g. 'bloodhound', 'crackmapexec', 'burp')")
    # documentation_time_minutes: operator self-report of how long documenting
    # this session took. Feeds the weekly North Star metric.
    documentation_time_minutes: Optional[int] = Field(None, ge=0, le=1440, description="Minutes spent documenting this session (operator self-report)")


class SessionCreate(SessionBase):
    """Model for creating a new session."""
    operation_id: str = Field(..., description="ID of the parent operation")
    operator_name: str = Field(..., description="Name of the operator who conducted the session")
    terminal_content: str = Field(..., description="Initial terminal content")
    screenshots: List[Screenshot] = Field(default_factory=list, description="Initial screenshots")


class Session(SessionBase):
    """Complete session model with all fields."""
    id: str = Field(..., description="Unique session identifier")
    created_at: datetime = Field(..., description="When the session was created")
    updated_at: datetime = Field(..., description="When the session was last updated")
    operation_id: Optional[str] = Field(None, description="ID of the parent operation (optional for backward compatibility)")
    operator_name: Optional[str] = Field(None, description="Name of the operator who conducted the session (optional for backward compatibility)")
    terminal_content: str = Field(..., description="Terminal session content")
    screenshots: List[Screenshot] = Field(default_factory=list, description="Screenshots associated with the session")
    screenshot_extractions: List[ScreenshotExtraction] = Field(default_factory=list, description="Screenshot text extraction results")
    metadata: Optional[Dict] = Field(default_factory=dict, description="Additional metadata including screenshot_texts for querying")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "id": "session-123",
                "title": "Penetration Test Session",
                "description": "Initial reconnaissance phase",
                "tags": ["recon", "nmap", "scanning"],
                "operation_id": "op-123",
                "operator_name": "John Doe",
                "targets": ["192.168.1.100", "example.com"],
                "tools": ["nmap", "metasploit"],
                "findings": ["Open port 22", "Weak SSH configuration"],
                "created_at": "2024-01-15T10:30:00",
                "updated_at": "2024-01-15T11:45:00",
                "terminal_content": "nmap -sV 192.168.1.0/24\n...",
                "screenshots": [
                    {
                        "filename": "screenshot-001.png",
                        "timestamp": "2024-01-15T10:35:00",
                        "description": "Initial scan results"
                    }
                ]
            }
        }
    )


class SessionUpdate(BaseModel):
    """Model for updating an existing session."""
    title: Optional[str] = None
    description: Optional[str] = None
    tags: Optional[List[str]] = None
    terminal_content: Optional[str] = None
    targets: Optional[List[str]] = None
    tools: Optional[List[str]] = None
    findings: Optional[List[str]] = None
    primary_tool: Optional[str] = None
    documentation_time_minutes: Optional[int] = Field(None, ge=0, le=1440)

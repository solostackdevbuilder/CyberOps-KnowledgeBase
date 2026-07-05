"""
Plugin base classes.
Every plugin (tool, UI, hybrid) must inherit from one of these.
"""
from abc import ABC, abstractmethod
from enum import Enum
from typing import Any, Dict, List, Optional

from fastapi import APIRouter
from pydantic import BaseModel, Field


# ============================================================================
# Plugin manifest and metadata models
# ============================================================================

class PluginType(str, Enum):
    TOOL = "tool"
    UI = "ui"
    HYBRID = "hybrid"


class ExecutionMode(str, Enum):
    LOCAL = "local"
    REMOTE = "remote"
    BOTH = "both"


class PluginManifest(BaseModel):
    """Plugin metadata loaded from manifest.json."""
    id: str = Field(..., description="Unique plugin identifier")
    name: str = Field(..., description="Human-readable plugin name")
    version: str = Field(..., description="Semantic version")
    plugin_type: PluginType = Field(..., description="Plugin type: tool, ui, or hybrid")
    author: str = Field(default="", description="Plugin author")
    description: str = Field(default="", description="What this plugin does")
    license: str = Field(default="proprietary", description="License type")

    # Execution configuration (for tool/hybrid plugins)
    execution_mode: ExecutionMode = Field(
        default=ExecutionMode.LOCAL,
        description="How the tool executes: local CLI, remote agent, or both"
    )

    # Permissions the plugin needs
    permissions: List[str] = Field(
        default_factory=list,
        description="Required permissions: shell:execute, network:outbound, storage:read_write"
    )

    # Plugin-specific settings schema
    settings_schema: Dict[str, Any] = Field(
        default_factory=dict,
        description="JSON Schema for plugin-specific configuration"
    )

    # Frontend pages (for ui/hybrid plugins)
    frontend_pages: List[Dict[str, str]] = Field(
        default_factory=list,
        description="UI pages this plugin provides: [{path, name, icon}]"
    )

    # Trust/signing. See core/plugins/signing.py for how these are produced
    # and verified. `source_hashes` maps each non-manifest file in the plugin
    # directory to its sha256; `signature` is an Ed25519 signature over the
    # canonical manifest (which includes source_hashes), base64-encoded.
    signature: Optional[str] = Field(None, description="Base64 Ed25519 signature over the canonical manifest")
    signature_algorithm: Optional[str] = Field(None, description="Signature algorithm, e.g. 'ed25519'")
    source_hashes: Optional[Dict[str, str]] = Field(
        None,
        description="Map of {relative_path: 'sha256:HEX'} for every non-manifest file in the plugin dir",
    )
    signed_by: Optional[str] = Field(None, description="Signer identity")


# ============================================================================
# Tool execution result models
# ============================================================================

class ToolResult(BaseModel):
    """Result of a tool execution."""
    status: str = Field(..., description="completed, failed, submitted, timeout")
    output: Optional[str] = Field(None, description="Tool stdout")
    error: Optional[str] = Field(None, description="Tool stderr or error message")
    return_code: Optional[int] = Field(None, description="Process exit code (local only)")
    job_id: Optional[str] = Field(None, description="Async job ID (remote only)")
    data: Optional[Dict[str, Any]] = Field(None, description="Structured result data")


class JobStatus(BaseModel):
    """Status of an async tool job."""
    job_id: str
    status: str = Field(..., description="queued, running, completed, failed, cancelled")
    progress: Optional[float] = Field(None, description="0.0-1.0 progress indicator")
    message: Optional[str] = Field(None, description="Status message")
    result: Optional[ToolResult] = Field(None, description="Result when completed")


# ============================================================================
# Plugin base classes
# ============================================================================

class PluginBase(ABC):
    """Base class for all plugins."""

    manifest: PluginManifest

    @abstractmethod
    async def initialize(self, settings: dict) -> None:
        """Called during app startup. Set up connections, validate config."""
        pass

    @abstractmethod
    async def shutdown(self) -> None:
        """Called during app shutdown. Clean up resources."""
        pass

    async def health_check(self) -> dict:
        """Return plugin health status."""
        return {"status": "ok", "plugin": self.manifest.id}

    def get_routes(self) -> Optional[APIRouter]:
        """Return FastAPI router if this plugin has API endpoints."""
        return None

    def get_frontend_manifest(self) -> dict:
        """Return manifest for frontend consumption."""
        return {
            "id": self.manifest.id,
            "name": self.manifest.name,
            "type": self.manifest.plugin_type.value,
            "description": self.manifest.description,
            "pages": self.manifest.frontend_pages,
        }


class ToolPlugin(PluginBase):
    """Base class for tool plugins (hashcat, john, nmap, etc.)."""

    @abstractmethod
    async def execute(self, params: dict) -> ToolResult:
        """Run the tool with given parameters.
        Implementation decides local vs remote based on config.
        """
        pass

    @abstractmethod
    async def get_status(self, job_id: str) -> JobStatus:
        """Check status of an async tool execution."""
        pass

    async def cancel(self, job_id: str) -> bool:
        """Cancel a running job. Returns True if cancelled."""
        return False

    def get_input_schema(self) -> dict:
        """Return JSON Schema for the tool's input parameters.
        Used by frontend to render a dynamic input form.
        """
        return {}


class UIPlugin(PluginBase):
    """Base class for UI plugins (enterprise auth, dashboards, etc.)."""

    def get_middleware(self) -> Optional[list]:
        """Return middleware to inject into the app (e.g., auth middleware)."""
        return None

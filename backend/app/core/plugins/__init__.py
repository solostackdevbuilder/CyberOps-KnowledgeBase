"""
Plugin framework for CyberOps platform.
Supports tool plugins (hashcat, nmap), UI plugins (auth), and hybrid plugins.
"""
from app.core.plugins.base import (
    JobStatus,
    PluginBase,
    PluginManifest,
    ToolPlugin,
    ToolResult,
    UIPlugin,
)

__all__ = [
    "JobStatus",
    "PluginBase",
    "PluginManifest",
    "ToolPlugin",
    "ToolResult",
    "UIPlugin",
]

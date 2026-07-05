"""
Plugin capability enforcement.

Plugins declare the capabilities they need in manifest.json under
`permissions`. Shared core helpers (LocalCLIAdapter, RemoteAgentAdapter,
_run_ssh_command, PluginDataStore) check the calling plugin's manifest
against the capability they're about to exercise. A plugin that tries to
use a helper for a capability it did not declare raises PermissionDenied.

## What this is

- An audit layer: the manifest is the source of truth for what a plugin
  does. If a plugin silently starts doing something new (e.g., a recent
  refactor made it reach out over the network), the check fails loudly.
- A policy hook: operators can set CYBEROPS_DISABLED_CAPABILITIES in the
  environment to turn off specific capabilities globally, useful for
  hardened deployments.
- A declaration contract: new plugin authors learn what they need to
  declare because the helper they're calling won't work without it.

## What this is NOT

- A sandbox. Any Python code in the plugin process can `import subprocess`
  and bypass the check entirely. If you need real isolation, run plugins
  in separate processes with OS-level sandboxing (out of scope here).
- A replacement for plugin signature verification (PluginManifest.signature
  exists but is not yet validated by PluginRegistry.load - that is a
  separate open item).

## Usage

    from app.core.plugins.capabilities import require, SHELL_EXECUTE

    class LocalCLIAdapter:
        def __init__(self, manifest: PluginManifest):
            require(manifest, SHELL_EXECUTE)
            self._manifest = manifest

When the enforcer raises, the caller sees a PermissionDenied with the
plugin id and the missing capability name.
"""
from __future__ import annotations

import logging
import os
from typing import TYPE_CHECKING, Iterable, Set

if TYPE_CHECKING:
    from app.core.plugins.base import PluginManifest

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Well-known capabilities
# ---------------------------------------------------------------------------

SHELL_EXECUTE = "shell:execute"
NETWORK_OUTBOUND = "network:outbound"
STORAGE_READ_WRITE = "storage:read_write"
CREDENTIALS_READ = "credentials:read"

KNOWN_CAPABILITIES: Set[str] = {
    SHELL_EXECUTE,
    NETWORK_OUTBOUND,
    STORAGE_READ_WRITE,
    CREDENTIALS_READ,
}


class PermissionDenied(Exception):
    """Raised when a plugin tries to exercise a capability it did not declare."""

    def __init__(self, plugin_id: str, capability: str, reason: str = "not declared"):
        self.plugin_id = plugin_id
        self.capability = capability
        self.reason = reason
        super().__init__(
            f"Plugin '{plugin_id}' cannot use capability '{capability}': {reason}. "
            f"Add it to the plugin's manifest.json under `permissions` "
            f"(or remove the feature that requires it)."
        )


class CapabilityConfigError(Exception):
    """Raised when a plugin declares an unknown capability name."""


def _globally_disabled() -> Set[str]:
    """Capabilities disabled for this process via env var.

    CYBEROPS_DISABLED_CAPABILITIES is a comma-separated list of capability
    names. Useful for hardened deployments that want to rule out, e.g.,
    shell execution regardless of what individual plugins declare.
    """
    raw = os.environ.get("CYBEROPS_DISABLED_CAPABILITIES", "").strip()
    if not raw:
        return set()
    return {p.strip() for p in raw.split(",") if p.strip()}


def require(manifest: "PluginManifest", capability: str) -> None:
    """Raise PermissionDenied unless `manifest` declares `capability`.

    Also honors the CYBEROPS_DISABLED_CAPABILITIES env var - a capability
    disabled globally is denied to every plugin regardless of declaration.
    """
    if capability in _globally_disabled():
        raise PermissionDenied(
            manifest.id,
            capability,
            reason="globally disabled via CYBEROPS_DISABLED_CAPABILITIES",
        )
    if capability not in manifest.permissions:
        raise PermissionDenied(manifest.id, capability)


def check_declared(manifest: "PluginManifest") -> None:
    """Fail loudly if a plugin declares a capability name we don't recognize.

    Meant to run at plugin load time. Unknown names are almost always typos
    (`shell:exec` instead of `shell:execute`) that would otherwise silently
    grant nothing, which is worse than a clear error.
    """
    unknown = [p for p in manifest.permissions if p not in KNOWN_CAPABILITIES]
    if unknown:
        raise CapabilityConfigError(
            f"Plugin '{manifest.id}' declares unknown capabilities in "
            f"manifest.json: {unknown}. Known capabilities: "
            f"{sorted(KNOWN_CAPABILITIES)}"
        )


def has(manifest: "PluginManifest", capability: str) -> bool:
    """Non-raising variant for branching logic (e.g., to pick between
    local execution and a graceful fallback). Honors the global disable list."""
    if capability in _globally_disabled():
        return False
    return capability in manifest.permissions


def declared_capabilities(manifest: "PluginManifest") -> Iterable[str]:
    """The effective capability set after applying the global disable list."""
    disabled = _globally_disabled()
    return [p for p in manifest.permissions if p not in disabled]

"""
SSH host-key pinning storage for the remote_servers plugin.

This module owns the persistence layer for per-server SSH pins. The
actual matching + raising lives in core/plugins/ssh.py - the shared
SSH helper there calls `get_pinned_key(server_id)` / `pin(...)` on
whichever store the calling plugin supplies. HostKeyMismatch (the
exception for pin drift) also lives in core/plugins/ssh.py since it's
a property of the SSH session, not of the storage backend.

## Trust model: TOFU with rekey-on-demand

Same model SSH clients have used for 30 years:

1. **First successful connect:** _run_ssh_command captures the server's
   presented host key and calls `pin(server_id, host, public_key)`.
2. **Every connect after:** _run_ssh_command reads via
   `get_pinned_key(server_id)` and passes the expected key to asyncssh.
   Mismatch raises HostKeyMismatch.
3. **Legitimate key rotation:** operator hits POST
   /api/plugins/remote_servers/servers/{id}/rekey, which calls
   `clear(server_id)`. The next connect TOFU-captures the new key.

## What this is NOT

- It does not protect the FIRST connect. If the operator was MITM'd the
  very first time they connected to a server, the attacker's key gets
  pinned. Classic TOFU trade-off. Out-of-band verification (compare the
  fingerprint against what the server admin says) is the mitigation.
- It only works via asyncssh. The subprocess-ssh fallback in
  _run_ssh_command cannot easily pin keys per server; if asyncssh is
  unavailable, a warning fires and pinning is skipped for that call.
  Since asyncssh is a required dep in requirements.txt, this fallback
  only kicks in for broken installs.
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional

from app.core.plugins.data_store import PluginDataStore

# Re-export for back-compat: HostKeyMismatch moved to core/plugins/ssh.py
# in Phase 2.2 but historically lived here. Importing from either location
# resolves to the same class.
from app.core.plugins.ssh import HostKeyMismatch  # noqa: F401

logger = logging.getLogger(__name__)

_COLLECTION = "host_keys"


class HostKeyStore:
    """Per-server host key pins, backed by PluginDataStore."""

    def __init__(self, data_store: PluginDataStore):
        self._store = data_store

    async def get_pinned_key(self, server_id: str) -> Optional[str]:
        """Return the pinned host key as an SSH public-key string, or None."""
        doc = await self._store.load(_COLLECTION, server_id)
        if not doc:
            return None
        key = doc.get("public_key")
        return key if isinstance(key, str) and key else None

    async def pin(self, server_id: str, host: str, public_key: str) -> None:
        """Store the host key as the pinned value for this server."""
        if not public_key or not public_key.strip():
            raise ValueError("public_key must be a non-empty SSH public-key string")
        await self._store.save(
            _COLLECTION,
            server_id,
            {
                "public_key": public_key.strip(),
                "host": host,
                "pinned_at": datetime.utcnow().isoformat(),
            },
        )
        logger.info(
            "Pinned SSH host key for server '%s' (%s)", server_id, host
        )

    async def clear(self, server_id: str) -> bool:
        """Drop the pin for this server. Returns True if something was removed."""
        removed = await self._store.delete(_COLLECTION, server_id)
        if removed:
            logger.info("Cleared SSH host key pin for server '%s'", server_id)
        return removed

    async def list_pinned(self) -> list[str]:
        """Return all server_ids that currently have a pinned host key."""
        return await self._store.list_keys(_COLLECTION)

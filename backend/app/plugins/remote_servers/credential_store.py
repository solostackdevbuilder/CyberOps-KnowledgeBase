"""
Encrypted credential store for the remote_servers plugin.

SSH credentials (passwords, private keys, key passphrases) are encrypted
at rest using Fernet (symmetric AEAD) with a key sourced from the
CYBEROPS_CREDENTIALS_KEY environment variable. A stale backup, leaked
snapshot, or stolen laptop no longer hands an attacker every remote
SSH password in plaintext.

## Threat model

Protects against:
- Offline data exposure: stolen backup tape, leaked cloud snapshot,
  accidental upload of the data directory
- Filesystem-only compromise where the attacker can read data/ but not
  the process environment (e.g., a read-only bucket leak)

Does NOT protect against:
- Live process compromise (attacker reads the env var or process memory)
- Attacker with access to both the data directory AND the key
- Root on the host (can read /proc/<pid>/environ)

Real isolation for the last case would require a KMS or hardware token,
out of scope for a self-hosted pentesting tool.

## Operator contract

Set CYBEROPS_CREDENTIALS_KEY to a Fernet-formatted base64 URL-safe 32-byte
key. Generate one with:

    python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"

Put it in the environment where the backend runs (`.env`, docker compose
env, systemd unit `Environment=`). Losing the key means every stored
credential becomes unreadable - back the key up the same way you back
up a password manager master key.

## Behavior when the key is unset

Falls back to plaintext storage with a loud startup warning. This exists
so existing deployments don't break on upgrade. In a hardened deployment
you should treat the warning as a config error - plaintext SSH creds on
disk is what we're trying to stop.

## Transparent migration

When the key IS set and a stored credential is found in plaintext format
(no `_encrypted` marker), it is decrypted-as-plaintext, re-saved in the
encrypted format, and returned. No manual migration step required.
"""
from __future__ import annotations

import json
import logging
import os
from typing import Any, Dict, Optional

from cryptography.fernet import Fernet, InvalidToken

from app.core.plugins.data_store import PluginDataStore

logger = logging.getLogger(__name__)

ENV_KEY_NAME = "CYBEROPS_CREDENTIALS_KEY"
_COLLECTION = "credentials"

# Marker stored at the top level of every encrypted record. Presence of the
# marker + "ciphertext" field means the payload is encrypted; absence means
# legacy plaintext and the next save will re-encrypt.
_ENCRYPTED_MARKER = "_encrypted"


class EncryptedCredentialStore:
    """Wraps PluginDataStore with Fernet encryption on the `credentials`
    collection. All other collections on the same data store are untouched
    - only credentials get this treatment.
    """

    def __init__(self, data_store: PluginDataStore):
        self._store = data_store
        raw_key = os.environ.get(ENV_KEY_NAME, "").strip()

        if not raw_key:
            # Existing deployments must not break on upgrade. Log once at
            # construction so operators see it in startup logs and test
            # output, but continue in plaintext mode.
            logger.warning(
                "%s is not set - remote_servers credentials are stored in "
                "PLAINTEXT on disk. Generate a key with `python -c \"from "
                "cryptography.fernet import Fernet; "
                "print(Fernet.generate_key().decode())\"` and set it in the "
                "process environment to enable encryption at rest.",
                ENV_KEY_NAME,
            )
            self._fernet: Optional[Fernet] = None
            return

        try:
            self._fernet = Fernet(raw_key.encode("ascii"))
        except (ValueError, TypeError) as e:
            raise ValueError(
                f"{ENV_KEY_NAME} is set but not a valid Fernet key: {e}. "
                f"Generate one with `python -c \"from cryptography.fernet "
                f"import Fernet; print(Fernet.generate_key().decode())\"`."
            ) from e

    @property
    def encryption_enabled(self) -> bool:
        return self._fernet is not None

    # ------------------------------------------------------------------
    # Public API mirrors PluginDataStore for save/load/delete/list_keys
    # on the credentials collection only.
    # ------------------------------------------------------------------

    async def save(self, server_id: str, credentials: Dict[str, Any]) -> None:
        """Persist credentials, encrypted if the key is configured."""
        if self._fernet is None:
            # Plaintext fallback - matches legacy behavior.
            await self._store.save(_COLLECTION, server_id, credentials)
            return

        payload = json.dumps(credentials, default=str).encode("utf-8")
        ciphertext = self._fernet.encrypt(payload).decode("ascii")
        await self._store.save(
            _COLLECTION,
            server_id,
            {_ENCRYPTED_MARKER: True, "ciphertext": ciphertext},
        )

    async def load(self, server_id: str) -> Optional[Dict[str, Any]]:
        """Load credentials, decrypting if needed. Returns None on miss.

        If the stored record is plaintext (legacy) and encryption is now
        enabled, re-encrypts and saves before returning. If decryption
        fails (wrong key, corrupted data), returns None and logs loudly
        - do not silently hand the caller bad data.
        """
        record = await self._store.load(_COLLECTION, server_id)
        if record is None:
            return None

        is_encrypted = bool(record.get(_ENCRYPTED_MARKER))

        if not is_encrypted:
            # Legacy plaintext record. If we have a key, upgrade in place.
            if self._fernet is not None:
                logger.info(
                    "Upgrading plaintext credential record for server '%s' "
                    "to encrypted format",
                    server_id,
                )
                await self.save(server_id, record)
            return record

        # Encrypted path.
        if self._fernet is None:
            logger.error(
                "Credential record for server '%s' is encrypted but %s is "
                "not set. Set the key in the environment to read this "
                "credential.",
                server_id,
                ENV_KEY_NAME,
            )
            return None

        ciphertext = record.get("ciphertext")
        if not isinstance(ciphertext, str):
            logger.error(
                "Credential record for server '%s' has encrypted marker but "
                "no ciphertext field; data is corrupt",
                server_id,
            )
            return None

        try:
            plaintext = self._fernet.decrypt(ciphertext.encode("ascii"))
        except InvalidToken:
            logger.error(
                "Failed to decrypt credential record for server '%s' - key "
                "mismatch or corrupted data. Will not return plaintext. "
                "Re-register the server with the Remote Servers UI to "
                "replace this record.",
                server_id,
            )
            return None

        try:
            return json.loads(plaintext.decode("utf-8"))
        except (ValueError, UnicodeDecodeError) as e:
            logger.error(
                "Credential record for server '%s' decrypted successfully "
                "but the payload is not valid JSON: %s",
                server_id,
                e,
            )
            return None

    async def delete(self, server_id: str) -> bool:
        """Delete a credential record."""
        return await self._store.delete(_COLLECTION, server_id)

    async def list_keys(self) -> list[str]:
        """List server_ids with stored credentials."""
        return await self._store.list_keys(_COLLECTION)


def generate_key() -> str:
    """Helper: generate a fresh Fernet key and return it as a string.

    Use via `python -m app.plugins.remote_servers.generate_key` (script
    entry point added alongside this module) or call directly from a REPL.
    """
    return Fernet.generate_key().decode("ascii")


if __name__ == "__main__":
    # `python -m app.plugins.remote_servers.credential_store` prints a key.
    print(generate_key())

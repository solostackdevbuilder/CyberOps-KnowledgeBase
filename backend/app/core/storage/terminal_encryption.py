"""
At-rest encryption for session terminal content.

Terminal output captured during a red-team session is high-value evidence:
commands run against client infrastructure, credentials harvested during
engagement, domain users enumerated, tool output mentioning IPs/hosts.
A leaked backup or stolen laptop with plaintext terminal logs walks that
evidence out the door.

This module provides a small Fernet wrapper, `TerminalContentCipher`,
that `FileStore` uses to encrypt the per-session `.txt` log files.
Metadata (title, tags, targets, operator name) stays in the session
JSON untouched so search and filtering keep working without the key.

## Threat model

Same as `plugins/remote_servers/credential_store.py` and
`core/storage/settings_encryption.py`: protects against offline
exposure (stolen backup, leaked snapshot, accidental commit of
`backend/data/`). Does NOT protect against live-process compromise,
a root-level attacker, or a disk image paired with the env.

## Key reuse

Reuses `CYBEROPS_CREDENTIALS_KEY`. Credential-class data at rest shares
one key so operators have one secret to back up and one to rotate.

## Behavior when the key is unset

Falls back to plaintext storage with a loud startup warning (logged
once at construction). Existing deployments do not break on upgrade.
In a hardened deployment, treat the warning as a config error.

## On-disk format

The canonical `.txt` file contains EITHER:

- the raw plaintext terminal content (legacy, pre-encryption), OR
- a Fernet token (base64 URL-safe ASCII, always starts with `gAAAAA`)
  produced by `Fernet.encrypt(text.encode("utf-8"))`.

On read, `decrypt` attempts Fernet decode first; if that succeeds the
content was encrypted, if it raises `InvalidToken` the content is
treated as legacy plaintext and flagged via `had_plaintext_legacy` so
the caller can trigger re-encryption on next save.

## Decryption failure

If a record IS a valid-looking Fernet token but the key does not
decrypt it (wrong key, corrupted ciphertext), `decrypt` returns
(empty string, False). The `False` flag prevents the caller from
mistaking the failure for a legacy record and overwriting the
ciphertext with empty content.
"""
from __future__ import annotations

import logging
import os
from typing import Optional, Tuple

from cryptography.fernet import Fernet, InvalidToken

logger = logging.getLogger(__name__)

ENV_KEY_NAME = "CYBEROPS_CREDENTIALS_KEY"

# All Fernet tokens are base64 URL-safe ASCII and start with "gAAAAA"
# (the first 6 chars encode the current Fernet version byte 0x80 plus
# the high bits of the timestamp). Terminal output never starts this
# way in practice, so this prefix is a safe "is this encrypted?"
# sniff before trying a full decrypt.
_FERNET_PREFIX = "gAAAAA"


class TerminalContentCipher:
    """Fernet wrapper for session terminal `.txt` files.

    One Fernet instance (or None in fallback mode) held per process.
    Tests pass `raw_key` explicitly; production reads the env.
    """

    def __init__(self, raw_key: Optional[str] = None):
        if raw_key is None:
            raw_key = os.environ.get(ENV_KEY_NAME, "").strip()

        if not raw_key:
            logger.warning(
                "%s is not set - session terminal_content is stored in "
                "PLAINTEXT on disk. Generate a key with `python -c \"from "
                "cryptography.fernet import Fernet; "
                "print(Fernet.generate_key().decode())\"` and set it in the "
                "process environment to encrypt terminal evidence at rest.",
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

    def encrypt(self, text: str) -> str:
        """Return text as a Fernet token string, or unchanged if
        encryption is disabled.

        Empty strings round-trip as empty strings - no point wasting
        8KB of ciphertext per empty session.
        """
        if self._fernet is None or text == "":
            return text
        return self._fernet.encrypt(text.encode("utf-8")).decode("ascii")

    def decrypt(self, blob: str) -> Tuple[str, bool]:
        """Return `(plaintext, had_plaintext_legacy)`.

        - Empty input → ("", False).
        - Fernet-shaped AND decrypts → (plaintext, False).
        - Not Fernet-shaped → treat as legacy plaintext: (blob, True).
          Caller uses `True` to trigger re-encryption on next save.
        - Fernet-shaped but decrypt fails → log loudly and return
          ("", False). Returning the raw ciphertext to the caller
          would hand them garbage; returning `True` would trick the
          caller into overwriting the stored ciphertext with empty
          on next save.
        """
        if blob == "":
            return "", False

        if not blob.startswith(_FERNET_PREFIX):
            # Legacy plaintext path.
            return blob, True

        if self._fernet is None:
            logger.error(
                "Terminal log appears encrypted but %s is not set. Set the "
                "key in the environment to read this session's content.",
                ENV_KEY_NAME,
            )
            return "", False

        try:
            plaintext = self._fernet.decrypt(blob.encode("ascii"))
        except InvalidToken:
            logger.error(
                "Failed to decrypt terminal log - key mismatch or corrupted "
                "data. The session's terminal content will appear empty. "
                "Restore from backup or re-capture the session."
            )
            return "", False

        return plaintext.decode("utf-8"), False


def generate_key() -> str:
    """Helper: generate a fresh Fernet key string."""
    return Fernet.generate_key().decode("ascii")


if __name__ == "__main__":
    print(generate_key())

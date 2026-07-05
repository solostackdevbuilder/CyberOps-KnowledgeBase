"""
Field-level encryption for settings.json.

LLM API keys, database passwords, and webhook URLs with embedded secret
paths are encrypted at rest using Fernet (symmetric AEAD) with a key
sourced from the CYBEROPS_CREDENTIALS_KEY environment variable. A stale
backup, leaked snapshot, or stolen laptop no longer hands an attacker
a live Anthropic API key in plaintext.

## What gets encrypted

Only the fields listed in `SECRET_FIELDS` are encrypted. Non-secret
settings (storage backend, privacy rules, entity groups, sensitive
defaults, etc.) stay in plaintext so the file remains readable for
ops inspection and so operators who lose the key do not lose their
whole configuration.

Each secret field is serialized as:

    {"_encrypted": true, "ciphertext": "<base64 Fernet token>"}

in place of the raw string. Load path reverses this. Non-secret fields
are passed through untouched.

## Threat model

Same as `plugins/remote_servers/credential_store.py` - protects against
offline data exposure (stolen backup, leaked snapshot, accidental commit
of the data directory). Does NOT protect against live-process compromise
or an attacker who has both the disk and the environment.

## Key reuse

Reuses `CYBEROPS_CREDENTIALS_KEY` rather than introducing a second env
var. Settings and SSH credentials share the same "credential-class at
rest" protection; one key to back up, one key to rotate.

## Behavior when the key is unset

Falls back to plaintext storage with a loud startup warning. This is
identical to credential_store.py fallback so operators upgrading from
an older build do not get a broken settings file. In a hardened
deployment treat the warning as a config error.

## Transparent migration

On `decrypt_secrets`, any field listed in `SECRET_FIELDS` that holds a
raw string (legacy plaintext) instead of the `{"_encrypted": ...}`
marker dict is detected and flagged via the returned `had_plaintext`
bool. `SettingsStore.load_settings` uses that signal to trigger an
immediate re-save, which encrypts the field on next write.
"""
from __future__ import annotations

import logging
import os
from typing import Any, Dict, List, Optional, Tuple

from cryptography.fernet import Fernet, InvalidToken

logger = logging.getLogger(__name__)

ENV_KEY_NAME = "CYBEROPS_CREDENTIALS_KEY"
_ENCRYPTED_MARKER = "_encrypted"

# Dotted paths into the settings dict for fields that must be encrypted.
# Add a field here to include it in the at-rest protection. Paths that
# traverse None/missing intermediate dicts are silently skipped, so listing
# a field that isn't always present (e.g., database_config.password) is
# safe.
SECRET_FIELDS: List[str] = [
    "llm_config.api_key",
    "database_config.password",
    "database_config.connection_string",
    "webhook_config.teams_webhook_url",
    "webhook_config.slack_webhook_url",
]


class SettingsEncryptor:
    """Field-level encrypt/decrypt helper for the settings dict.

    Holds the Fernet instance (or None in fallback mode) and knows
    which paths to touch. Stateless beyond the key itself.
    """

    def __init__(self, raw_key: Optional[str] = None):
        """Construct from a raw Fernet key string, or read from the env.

        Passing `raw_key=None` reads `CYBEROPS_CREDENTIALS_KEY`. Passing
        an explicit string is for tests.
        """
        if raw_key is None:
            raw_key = os.environ.get(ENV_KEY_NAME, "").strip()

        if not raw_key:
            logger.warning(
                "%s is not set - settings.json secret fields (LLM API key, "
                "webhook URLs, DB password) are stored in PLAINTEXT on disk. "
                "Generate a key with `python -c \"from cryptography.fernet "
                "import Fernet; print(Fernet.generate_key().decode())\"` and "
                "set it in the process environment to enable encryption at "
                "rest.",
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

    def encrypt_secrets(self, settings_dict: Dict[str, Any]) -> Dict[str, Any]:
        """Return a deep-ish copy of `settings_dict` with every path in
        `SECRET_FIELDS` replaced by an encrypted marker dict.

        No-op when encryption is disabled (key unset). Strings that are
        already an `{"_encrypted": ...}` marker dict are left alone.
        Empty strings and None values are left alone (no point
        encrypting nothing, and None means "field not configured").
        """
        if self._fernet is None:
            return settings_dict

        result = _copy_for_walk(settings_dict)
        for path in SECRET_FIELDS:
            value = _get_path(result, path)
            if value is None or value == "":
                continue
            if isinstance(value, dict) and value.get(_ENCRYPTED_MARKER):
                continue
            if not isinstance(value, str):
                logger.warning(
                    "Secret field '%s' is not a string (got %s); skipping "
                    "encryption. This is a data-shape bug.",
                    path,
                    type(value).__name__,
                )
                continue
            ciphertext = self._fernet.encrypt(value.encode("utf-8")).decode("ascii")
            _set_path(result, path, {_ENCRYPTED_MARKER: True, "ciphertext": ciphertext})
        return result

    def decrypt_secrets(
        self, settings_dict: Dict[str, Any]
    ) -> Tuple[Dict[str, Any], bool]:
        """Return `(dict_with_plaintext_secrets, had_plaintext_legacy)`.

        `had_plaintext_legacy` is True when any SECRET_FIELDS path held a
        raw string instead of the encrypted marker dict. The caller uses
        that to trigger a re-save so legacy plaintext records upgrade in
        place on next load.

        Decryption failures (wrong key, corrupted ciphertext) log loudly
        and clear the field to None. Returning corrupted ciphertext as
        the apparent "plaintext" would silently break downstream code.
        """
        result = _copy_for_walk(settings_dict)
        had_plaintext = False

        for path in SECRET_FIELDS:
            value = _get_path(result, path)
            if value is None or value == "":
                continue

            if isinstance(value, dict) and value.get(_ENCRYPTED_MARKER):
                if self._fernet is None:
                    logger.error(
                        "Settings field '%s' is encrypted but %s is not set. "
                        "Set the key in the environment to read this field.",
                        path,
                        ENV_KEY_NAME,
                    )
                    _set_path(result, path, None)
                    continue
                ciphertext = value.get("ciphertext")
                if not isinstance(ciphertext, str):
                    logger.error(
                        "Settings field '%s' has encrypted marker but no "
                        "ciphertext field; data is corrupt.",
                        path,
                    )
                    _set_path(result, path, None)
                    continue
                try:
                    plaintext = self._fernet.decrypt(ciphertext.encode("ascii"))
                except InvalidToken:
                    logger.error(
                        "Failed to decrypt settings field '%s' - key mismatch "
                        "or corrupted data. Field will be cleared. Re-enter "
                        "the value in Settings to replace it.",
                        path,
                    )
                    _set_path(result, path, None)
                    continue
                _set_path(result, path, plaintext.decode("utf-8"))
                continue

            if isinstance(value, str):
                had_plaintext = True

        return result, had_plaintext


def generate_key() -> str:
    """Helper: generate a fresh Fernet key string."""
    return Fernet.generate_key().decode("ascii")


def _copy_for_walk(d: Dict[str, Any]) -> Dict[str, Any]:
    """Shallow-copy the top-level dict plus every intermediate dict that
    SECRET_FIELDS traverses. Avoids mutating the caller's dict while
    also avoiding a full deepcopy of potentially large privacy-rule
    lists.
    """
    copied: Dict[str, Any] = dict(d)
    for path in SECRET_FIELDS:
        parts = path.split(".")
        cursor = copied
        for key in parts[:-1]:
            nested = cursor.get(key)
            if not isinstance(nested, dict):
                break
            cursor[key] = dict(nested)
            cursor = cursor[key]
    return copied


def _get_path(d: Dict[str, Any], path: str) -> Any:
    cursor: Any = d
    for key in path.split("."):
        if not isinstance(cursor, dict):
            return None
        cursor = cursor.get(key)
        if cursor is None:
            return None
    return cursor


def _set_path(d: Dict[str, Any], path: str, value: Any) -> None:
    cursor = d
    parts = path.split(".")
    for key in parts[:-1]:
        nested = cursor.get(key)
        if not isinstance(nested, dict):
            return
        cursor = nested
    cursor[parts[-1]] = value


if __name__ == "__main__":
    print(generate_key())

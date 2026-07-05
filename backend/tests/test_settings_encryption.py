"""
Tests for field-level settings encryption.

Scenarios covered:
- Round-trip: save + load round-trips LLMConfig.api_key correctly.
- On-disk ciphertext: the raw file does NOT contain the api_key.
- Non-secret fields stay plaintext (storage_backend, privacy rules, etc.).
- Fallback: with no key set, behavior matches the legacy plaintext store.
- Migration: a plaintext api_key in an existing file is transparently
  re-encrypted on next load.
- Wrong key: decrypt clears the field to None, returns
  had_plaintext_legacy=False so load does NOT re-save and overwrite
  the encrypted-but-unreadable record.
- Invalid key in env: clear error at construction, not at runtime.
- Multiple secret fields encrypt independently.
"""
from __future__ import annotations

import asyncio
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from cryptography.fernet import Fernet

from app.core.storage.settings_encryption import (
    ENV_KEY_NAME,
    SECRET_FIELDS,
    SettingsEncryptor,
    generate_key,
)
from app.core.storage.settings_store import SettingsStore
from app.models_settings import (
    LLMConfig,
    LLMProvider,
    Settings,
    StorageBackend,
    WebhookConfig,
)


def _run(coro):
    return asyncio.run(coro)


def _make_settings(api_key: str = "sk-ant-fake-test-key") -> Settings:
    return Settings(
        storage_backend=StorageBackend.JSON,
        llm_provider=LLMProvider.CLAUDE,
        llm_config=LLMConfig(
            provider=LLMProvider.CLAUDE,
            api_key=api_key,
            model_name="claude-sonnet-4-5-20250929",
        ),
        webhook_config=WebhookConfig(
            teams_webhook_url="https://outlook.office.com/webhook/abc123/IncomingWebhook/keysegment/xxx",
            enabled=False,
        ),
    )


def _make_store(key: str | None) -> tuple[SettingsStore, Path, tempfile.TemporaryDirectory]:
    tmp = tempfile.TemporaryDirectory()
    settings_file = Path(tmp.name) / "settings.json"
    if key is None:
        os.environ.pop(ENV_KEY_NAME, None)
        store = SettingsStore(settings_file=settings_file, encryptor=SettingsEncryptor())
    else:
        store = SettingsStore(
            settings_file=settings_file, encryptor=SettingsEncryptor(raw_key=key)
        )
    return store, settings_file, tmp


class GenerateKeyTests(unittest.TestCase):
    def test_generates_valid_fernet_key(self) -> None:
        key = generate_key()
        Fernet(key.encode("ascii"))


class EncryptorUnitTests(unittest.TestCase):
    """Direct tests on SettingsEncryptor without the SettingsStore."""

    def test_encrypt_then_decrypt_round_trip(self) -> None:
        enc = SettingsEncryptor(raw_key=generate_key())
        raw = {
            "storage_backend": "json",
            "llm_config": {"provider": "claude", "api_key": "SECRET_123"},
        }
        encrypted = enc.encrypt_secrets(raw)
        self.assertIsInstance(encrypted["llm_config"]["api_key"], dict)
        self.assertTrue(encrypted["llm_config"]["api_key"]["_encrypted"])
        decrypted, had_plaintext = enc.decrypt_secrets(encrypted)
        self.assertEqual(decrypted["llm_config"]["api_key"], "SECRET_123")
        self.assertFalse(had_plaintext)

    def test_non_secret_fields_are_untouched(self) -> None:
        enc = SettingsEncryptor(raw_key=generate_key())
        raw = {
            "storage_backend": "json",
            "llm_provider": "claude",
            "privacy_replacements": {"enabled": True, "rules": [{"id": "r1"}]},
            "llm_config": {"provider": "claude", "api_key": "secret"},
        }
        encrypted = enc.encrypt_secrets(raw)
        self.assertEqual(encrypted["storage_backend"], "json")
        self.assertEqual(encrypted["llm_provider"], "claude")
        self.assertEqual(encrypted["privacy_replacements"]["enabled"], True)
        self.assertEqual(encrypted["privacy_replacements"]["rules"], [{"id": "r1"}])

    def test_missing_secret_paths_are_silently_skipped(self) -> None:
        enc = SettingsEncryptor(raw_key=generate_key())
        raw = {"storage_backend": "json"}
        encrypted = enc.encrypt_secrets(raw)
        self.assertEqual(encrypted, {"storage_backend": "json"})

    def test_empty_string_secrets_are_not_encrypted(self) -> None:
        enc = SettingsEncryptor(raw_key=generate_key())
        raw = {"llm_config": {"api_key": ""}, "webhook_config": {"teams_webhook_url": None}}
        encrypted = enc.encrypt_secrets(raw)
        self.assertEqual(encrypted["llm_config"]["api_key"], "")
        self.assertIsNone(encrypted["webhook_config"]["teams_webhook_url"])

    def test_already_encrypted_field_is_not_double_encrypted(self) -> None:
        key = generate_key()
        enc = SettingsEncryptor(raw_key=key)
        once = enc.encrypt_secrets({"llm_config": {"api_key": "v1"}})
        twice = enc.encrypt_secrets(once)
        self.assertEqual(once["llm_config"]["api_key"], twice["llm_config"]["api_key"])

    def test_decrypt_flags_legacy_plaintext_secrets(self) -> None:
        enc = SettingsEncryptor(raw_key=generate_key())
        raw = {"llm_config": {"api_key": "legacy-plaintext"}}
        decrypted, had_plaintext = enc.decrypt_secrets(raw)
        self.assertTrue(had_plaintext)
        self.assertEqual(decrypted["llm_config"]["api_key"], "legacy-plaintext")

    def test_fallback_mode_is_noop(self) -> None:
        # No key => encryptor runs in plaintext fallback.
        enc = SettingsEncryptor(raw_key="")
        raw = {"llm_config": {"api_key": "still-plain"}}
        encrypted = enc.encrypt_secrets(raw)
        self.assertEqual(encrypted, raw)
        decrypted, had_plaintext = enc.decrypt_secrets(raw)
        self.assertEqual(decrypted["llm_config"]["api_key"], "still-plain")
        self.assertTrue(had_plaintext)

    def test_invalid_key_fails_at_construction(self) -> None:
        with self.assertRaises(ValueError) as ctx:
            SettingsEncryptor(raw_key="not-a-valid-fernet-key!!!")
        self.assertIn(ENV_KEY_NAME, str(ctx.exception))

    def test_invalid_key_from_env_fails_at_construction(self) -> None:
        with patch.dict(os.environ, {ENV_KEY_NAME: "also-not-valid!!!"}):
            with self.assertRaises(ValueError):
                SettingsEncryptor()

    def test_wrong_key_clears_field_and_does_not_flag_migration(self) -> None:
        # Write with key A, decrypt with key B: the field goes to None
        # (protecting the caller from silently broken data) and
        # had_plaintext stays False (so the store does NOT re-save and
        # overwrite the original encrypted record with None).
        key_a = generate_key()
        key_b = generate_key()
        enc_a = SettingsEncryptor(raw_key=key_a)
        enc_b = SettingsEncryptor(raw_key=key_b)
        encrypted = enc_a.encrypt_secrets({"llm_config": {"api_key": "secret"}})
        decrypted, had_plaintext = enc_b.decrypt_secrets(encrypted)
        self.assertIsNone(decrypted["llm_config"]["api_key"])
        self.assertFalse(had_plaintext)

    def test_all_declared_secret_paths_encrypt(self) -> None:
        enc = SettingsEncryptor(raw_key=generate_key())
        raw: dict = {}
        # Build a dict that has every SECRET_FIELDS path populated.
        for path in SECRET_FIELDS:
            parts = path.split(".")
            cursor = raw
            for key in parts[:-1]:
                cursor.setdefault(key, {})
                cursor = cursor[key]
            cursor[parts[-1]] = f"value-for-{path}"

        encrypted = enc.encrypt_secrets(raw)
        # Every secret path must now hold a marker dict.
        for path in SECRET_FIELDS:
            cursor = encrypted
            for key in path.split("."):
                cursor = cursor[key]
            self.assertIsInstance(cursor, dict)
            self.assertTrue(cursor.get("_encrypted"))


class SettingsStoreRoundTripTests(unittest.TestCase):
    def test_save_then_load_preserves_api_key(self) -> None:
        key = generate_key()
        store, _path, tmp = _make_store(key)
        try:
            original = _make_settings(api_key="sk-ant-real-looking-key")
            _run(store.save_settings(original))
            loaded = _run(store.load_settings())
            self.assertEqual(loaded.llm_config.api_key, "sk-ant-real-looking-key")
            self.assertEqual(loaded.storage_backend, StorageBackend.JSON)
        finally:
            tmp.cleanup()

    def test_api_key_is_not_on_disk_in_plaintext(self) -> None:
        """The whole point of the feature."""
        key = generate_key()
        store, path, tmp = _make_store(key)
        try:
            secret = "sk-ant-very-sensitive-string"
            _run(store.save_settings(_make_settings(api_key=secret)))
            raw = path.read_bytes()
            self.assertNotIn(secret.encode(), raw)
            parsed = json.loads(raw)
            api_key_field = parsed["llm_config"]["api_key"]
            self.assertIsInstance(api_key_field, dict)
            self.assertTrue(api_key_field["_encrypted"])
            self.assertIn("ciphertext", api_key_field)
        finally:
            tmp.cleanup()

    def test_webhook_url_is_not_on_disk_in_plaintext(self) -> None:
        key = generate_key()
        store, path, tmp = _make_store(key)
        try:
            _run(store.save_settings(_make_settings()))
            raw = path.read_text(encoding="utf-8")
            self.assertNotIn("keysegment", raw)
            parsed = json.loads(raw)
            self.assertTrue(
                parsed["webhook_config"]["teams_webhook_url"]["_encrypted"]
            )
        finally:
            tmp.cleanup()

    def test_non_secret_fields_remain_readable_on_disk(self) -> None:
        key = generate_key()
        store, path, tmp = _make_store(key)
        try:
            _run(store.save_settings(_make_settings()))
            parsed = json.loads(path.read_text(encoding="utf-8"))
            # Plaintext inspection still works for non-secrets.
            self.assertEqual(parsed["storage_backend"], "json")
            self.assertEqual(parsed["llm_provider"], "claude")
            self.assertIn("privacy_replacements", parsed)
        finally:
            tmp.cleanup()


class SettingsStoreFallbackTests(unittest.TestCase):
    def test_no_key_stores_plaintext(self) -> None:
        """Upgrade path: operators who don't set the key still get a
        functional deployment (with a startup warning)."""
        store, path, tmp = _make_store(None)
        try:
            _run(store.save_settings(_make_settings(api_key="plain-visible")))
            raw = path.read_text(encoding="utf-8")
            self.assertIn("plain-visible", raw)
        finally:
            tmp.cleanup()

    def test_no_key_round_trip_still_works(self) -> None:
        store, _path, tmp = _make_store(None)
        try:
            _run(store.save_settings(_make_settings(api_key="plain-visible")))
            loaded = _run(store.load_settings())
            self.assertEqual(loaded.llm_config.api_key, "plain-visible")
        finally:
            tmp.cleanup()


class SettingsStoreMigrationTests(unittest.TestCase):
    def test_plaintext_settings_file_is_reencrypted_on_next_load(self) -> None:
        """Existing deployment upgrades: plaintext settings.json on disk,
        operator sets the key, first load re-saves encrypted."""
        tmp = tempfile.TemporaryDirectory()
        try:
            path = Path(tmp.name) / "settings.json"

            # Phase 1: write a legacy plaintext file directly.
            legacy = _make_settings(api_key="legacy-plain-key").model_dump(mode="json")
            path.write_text(json.dumps(legacy), encoding="utf-8")

            # Phase 2: load via an encrypted store - should return the
            # same data AND re-save encrypted.
            key = generate_key()
            store = SettingsStore(
                settings_file=path, encryptor=SettingsEncryptor(raw_key=key)
            )
            loaded = _run(store.load_settings())
            self.assertEqual(loaded.llm_config.api_key, "legacy-plain-key")

            # On-disk must now be encrypted.
            raw = path.read_text(encoding="utf-8")
            self.assertNotIn("legacy-plain-key", raw)
            parsed = json.loads(raw)
            self.assertTrue(parsed["llm_config"]["api_key"]["_encrypted"])
        finally:
            tmp.cleanup()


class SettingsStoreWrongKeyTests(unittest.TestCase):
    def test_wrong_key_load_does_not_destroy_encrypted_record(self) -> None:
        """Operator rotates the key incorrectly. We must NOT silently
        overwrite the encrypted field with None on next save. The
        decrypt_secrets contract is that wrong-key clears the field in
        memory but does NOT set had_plaintext=True, so no re-save fires.
        """
        key_a = generate_key()
        key_b = generate_key()
        tmp = tempfile.TemporaryDirectory()
        try:
            path = Path(tmp.name) / "settings.json"
            store_a = SettingsStore(
                settings_file=path, encryptor=SettingsEncryptor(raw_key=key_a)
            )
            _run(store_a.save_settings(_make_settings(api_key="safe-key")))
            encrypted_disk = json.loads(path.read_text(encoding="utf-8"))

            # Attempt load with wrong key - llm_config clears to None
            # during decrypt, and Pydantic validation rejects a Claude
            # provider with no api_key, so load raises. But the on-disk
            # ciphertext must still be there afterwards.
            store_b = SettingsStore(
                settings_file=path, encryptor=SettingsEncryptor(raw_key=key_b)
            )
            with self.assertRaises(RuntimeError):
                _run(store_b.load_settings())

            disk_after = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(
                encrypted_disk["llm_config"]["api_key"],
                disk_after["llm_config"]["api_key"],
            )
        finally:
            tmp.cleanup()


if __name__ == "__main__":
    unittest.main()

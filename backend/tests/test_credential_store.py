"""
Tests for EncryptedCredentialStore.

Scenarios covered:
- Round-trip: save encrypted, load decrypts to the same dict
- On-disk ciphertext: the raw file does NOT contain password plaintext
- Fallback: with no key set, behavior matches plain PluginDataStore
- Migration: plaintext record written before encryption was enabled
  is transparently re-encrypted on next load
- Wrong key: load returns None and logs an error (not silent)
- Invalid key in env: clear error at construction, not at runtime
"""
import asyncio
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from cryptography.fernet import Fernet

from app.core.plugins.base import PluginManifest
from app.core.plugins.data_store import PluginDataStore
from app.plugins.remote_servers.credential_store import (
    ENV_KEY_NAME,
    EncryptedCredentialStore,
    generate_key,
)


def _run(coro):
    return asyncio.run(coro)


def _manifest() -> PluginManifest:
    return PluginManifest(
        id="remote_servers",
        name="Remote Servers",
        version="1.0.0",
        plugin_type="hybrid",
        permissions=["network:outbound", "storage:read_write", "credentials:read"],
    )


def _make_store(key: str | None) -> tuple[EncryptedCredentialStore, PluginDataStore, tempfile.TemporaryDirectory]:
    tmp = tempfile.TemporaryDirectory()
    data_store = PluginDataStore(_manifest(), Path(tmp.name))
    env = {ENV_KEY_NAME: key} if key is not None else {}
    with patch.dict(os.environ, env, clear=False):
        if key is None:
            # Explicitly remove the env var so a developer's shell doesn't
            # accidentally make tests pass.
            os.environ.pop(ENV_KEY_NAME, None)
            cred_store = EncryptedCredentialStore(data_store)
        else:
            cred_store = EncryptedCredentialStore(data_store)
    return cred_store, data_store, tmp


class GenerateKeyTests(unittest.TestCase):
    def test_generates_valid_fernet_key(self) -> None:
        key = generate_key()
        # Constructing Fernet with it must not raise.
        Fernet(key.encode("ascii"))


class RoundTripTests(unittest.TestCase):
    def test_save_and_load_returns_same_dict(self) -> None:
        key = Fernet.generate_key().decode("ascii")
        store, _data, tmp = _make_store(key)
        try:
            creds = {"host": "1.2.3.4", "port": 22, "username": "kali", "password": "hunter2"}
            _run(store.save("srv", creds))
            loaded = _run(store.load("srv"))
            self.assertEqual(loaded, creds)
        finally:
            tmp.cleanup()

    def test_encryption_enabled_flag(self) -> None:
        key = Fernet.generate_key().decode("ascii")
        store, _, tmp = _make_store(key)
        try:
            self.assertTrue(store.encryption_enabled)
        finally:
            tmp.cleanup()

    def test_plaintext_fallback_flag(self) -> None:
        store, _, tmp = _make_store(None)
        try:
            self.assertFalse(store.encryption_enabled)
        finally:
            tmp.cleanup()


class CiphertextOnDiskTests(unittest.TestCase):
    """The whole point of this feature: an attacker reading the raw file
    must not see the password."""

    def test_password_is_not_on_disk_in_plaintext(self) -> None:
        key = Fernet.generate_key().decode("ascii")
        store, data_store, tmp = _make_store(key)
        try:
            secret = "correct-horse-battery-staple"
            _run(store.save("srv", {
                "host": "1.2.3.4", "port": 22, "username": "kali",
                "password": secret, "private_key": "-----BEGIN KEY-----xxx-----END KEY-----",
            }))
            # Locate the on-disk file for this record and read its raw bytes.
            disk_file = Path(data_store.data_dir) / "credentials" / "srv.json"
            raw = disk_file.read_bytes()
            self.assertNotIn(secret.encode(), raw)
            self.assertNotIn(b"-----BEGIN KEY-----", raw)
            # And the on-disk record declares it is encrypted.
            parsed = json.loads(raw)
            self.assertTrue(parsed.get("_encrypted"))
            self.assertIn("ciphertext", parsed)
        finally:
            tmp.cleanup()

    def test_fallback_stores_plaintext_when_key_unset(self) -> None:
        # Documents the current fallback behavior explicitly so future
        # changes that silently "improve" to always encrypt don't slip
        # past review.
        store, data_store, tmp = _make_store(None)
        try:
            secret = "plaintext-secret"
            _run(store.save("srv", {"password": secret}))
            disk_file = Path(data_store.data_dir) / "credentials" / "srv.json"
            raw = disk_file.read_bytes()
            self.assertIn(secret.encode(), raw)
        finally:
            tmp.cleanup()


class MigrationTests(unittest.TestCase):
    def test_plaintext_record_is_reencrypted_on_next_load(self) -> None:
        """Operator enables encryption on an existing deployment - the
        stored plaintext record must upgrade in place on next read."""
        # Phase 1: write a plaintext record (no key set).
        key = Fernet.generate_key().decode("ascii")
        _, data_store, tmp = _make_store(None)
        try:
            _run(data_store.save("credentials", "srv", {
                "host": "1.2.3.4", "username": "kali", "password": "legacy",
            }))

            # Phase 2: load through an encrypted store - should return the
            # same data AND re-save it encrypted.
            with patch.dict(os.environ, {ENV_KEY_NAME: key}):
                enc_store = EncryptedCredentialStore(data_store)
                loaded = _run(enc_store.load("srv"))

            self.assertEqual(loaded["password"], "legacy")

            # Now the on-disk file must be encrypted.
            disk_file = Path(data_store.data_dir) / "credentials" / "srv.json"
            parsed = json.loads(disk_file.read_bytes())
            self.assertTrue(parsed.get("_encrypted"))
            self.assertNotIn("legacy", disk_file.read_text())
        finally:
            tmp.cleanup()


class WrongKeyTests(unittest.TestCase):
    def test_returns_none_on_decryption_failure(self) -> None:
        key_a = Fernet.generate_key().decode("ascii")
        key_b = Fernet.generate_key().decode("ascii")

        # Write with key A.
        store_a, data_store, tmp = _make_store(key_a)
        try:
            _run(store_a.save("srv", {"password": "hunter2"}))

            # Read with key B - decryption must fail and return None,
            # not silently hand the caller something wrong.
            with patch.dict(os.environ, {ENV_KEY_NAME: key_b}):
                store_b = EncryptedCredentialStore(data_store)
                self.assertIsNone(_run(store_b.load("srv")))
        finally:
            tmp.cleanup()

    def test_returns_none_when_key_unset_and_record_is_encrypted(self) -> None:
        """Operator rotates away from encryption - stored encrypted
        records must NOT be returned as-is (they would be unusable junk)."""
        key = Fernet.generate_key().decode("ascii")
        store, data_store, tmp = _make_store(key)
        try:
            _run(store.save("srv", {"password": "hunter2"}))

            with patch.dict(os.environ, {}, clear=False):
                os.environ.pop(ENV_KEY_NAME, None)
                store_no_key = EncryptedCredentialStore(data_store)
                self.assertIsNone(_run(store_no_key.load("srv")))
        finally:
            tmp.cleanup()


class InvalidKeyTests(unittest.TestCase):
    def test_malformed_key_fails_at_construction(self) -> None:
        """Operator copy-pastes something that isn't a valid Fernet key -
        fail loudly at startup, not later when a credential is loaded."""
        tmp = tempfile.TemporaryDirectory()
        try:
            data_store = PluginDataStore(_manifest(), Path(tmp.name))
            with patch.dict(os.environ, {ENV_KEY_NAME: "this-is-not-base64!!"}):
                with self.assertRaises(ValueError) as ctx:
                    EncryptedCredentialStore(data_store)
                self.assertIn(ENV_KEY_NAME, str(ctx.exception))
        finally:
            tmp.cleanup()


class MissingRecordTests(unittest.TestCase):
    def test_load_missing_returns_none(self) -> None:
        key = Fernet.generate_key().decode("ascii")
        store, _, tmp = _make_store(key)
        try:
            self.assertIsNone(_run(store.load("does-not-exist")))
        finally:
            tmp.cleanup()

    def test_delete_missing_returns_false(self) -> None:
        key = Fernet.generate_key().decode("ascii")
        store, _, tmp = _make_store(key)
        try:
            self.assertFalse(_run(store.delete("does-not-exist")))
        finally:
            tmp.cleanup()


if __name__ == "__main__":
    unittest.main()

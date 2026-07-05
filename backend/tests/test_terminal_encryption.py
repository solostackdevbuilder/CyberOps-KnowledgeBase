"""
Tests for terminal content at-rest encryption.

Scenarios covered:
- Round-trip: cipher.encrypt -> cipher.decrypt returns the original.
- Empty string passes through unchanged (don't waste ciphertext).
- Fallback: with no key set, encrypt is a no-op and plaintext stays.
- Legacy plaintext detection: random text → (text, had_plaintext=True)
  so FileStore can re-encrypt on next save.
- Wrong key: valid-looking Fernet token but wrong key decrypts to
  (empty string, had_plaintext=False). False flag is load-bearing:
  it prevents the caller from treating the failure as a legacy record
  and overwriting the stored ciphertext with empty.
- Invalid key in env: clear error at construction.
- FileStore integration:
  - Session .txt file on disk is ciphertext, not plaintext.
  - Session metadata JSON does NOT contain terminal_content on disk.
  - get_session returns the decrypted terminal_content.
  - Legacy plaintext .txt migrates to encrypted on first get_session.
"""
from __future__ import annotations

import asyncio
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.core.models import SessionCreate
from app.core.storage.terminal_encryption import (
    ENV_KEY_NAME,
    TerminalContentCipher,
    generate_key,
)


def _run(coro):
    return asyncio.run(coro)


class CipherUnitTests(unittest.TestCase):
    def test_round_trip(self) -> None:
        cipher = TerminalContentCipher(raw_key=generate_key())
        original = "root@target:~# whoami\nroot\n"
        token = cipher.encrypt(original)
        self.assertNotEqual(token, original)
        self.assertTrue(token.startswith("gAAAAA"))
        plaintext, had_plaintext = cipher.decrypt(token)
        self.assertEqual(plaintext, original)
        self.assertFalse(had_plaintext)

    def test_empty_string_is_noop(self) -> None:
        cipher = TerminalContentCipher(raw_key=generate_key())
        self.assertEqual(cipher.encrypt(""), "")
        plaintext, had_plaintext = cipher.decrypt("")
        self.assertEqual(plaintext, "")
        self.assertFalse(had_plaintext)

    def test_unicode_round_trip(self) -> None:
        cipher = TerminalContentCipher(raw_key=generate_key())
        original = "λ ✓ 中文 emoji 😀\n"
        token = cipher.encrypt(original)
        plaintext, _ = cipher.decrypt(token)
        self.assertEqual(plaintext, original)

    def test_fallback_mode_is_plaintext_passthrough(self) -> None:
        cipher = TerminalContentCipher(raw_key="")
        self.assertFalse(cipher.encryption_enabled)
        original = "some terminal output"
        self.assertEqual(cipher.encrypt(original), original)

    def test_legacy_plaintext_is_flagged(self) -> None:
        # A record that isn't Fernet-shaped is treated as legacy
        # plaintext so FileStore re-encrypts it on next save.
        cipher = TerminalContentCipher(raw_key=generate_key())
        plaintext, had_plaintext = cipher.decrypt("$ ls -la\ntotal 0\n")
        self.assertEqual(plaintext, "$ ls -la\ntotal 0\n")
        self.assertTrue(had_plaintext)

    def test_wrong_key_clears_field_does_not_flag_migration(self) -> None:
        # Encrypt with key A, decrypt with key B: the ciphertext IS
        # Fernet-shaped so we hit InvalidToken rather than the legacy
        # path. Must NOT flag had_plaintext=True (that would make
        # FileStore overwrite the stored ciphertext with empty on
        # next save, losing the evidence forever).
        cipher_a = TerminalContentCipher(raw_key=generate_key())
        cipher_b = TerminalContentCipher(raw_key=generate_key())
        token = cipher_a.encrypt("sensitive")
        plaintext, had_plaintext = cipher_b.decrypt(token)
        self.assertEqual(plaintext, "")
        self.assertFalse(had_plaintext)

    def test_key_unset_but_record_is_encrypted(self) -> None:
        """Operator rotates away the key while encrypted records still
        exist. We do NOT return the raw ciphertext as apparent
        plaintext."""
        cipher_with = TerminalContentCipher(raw_key=generate_key())
        token = cipher_with.encrypt("secret")

        cipher_without = TerminalContentCipher(raw_key="")
        plaintext, had_plaintext = cipher_without.decrypt(token)
        self.assertEqual(plaintext, "")
        self.assertFalse(had_plaintext)

    def test_invalid_key_fails_at_construction(self) -> None:
        with self.assertRaises(ValueError) as ctx:
            TerminalContentCipher(raw_key="not-a-valid-fernet-key!!!")
        self.assertIn(ENV_KEY_NAME, str(ctx.exception))

    def test_invalid_key_from_env_fails_at_construction(self) -> None:
        with patch.dict(os.environ, {ENV_KEY_NAME: "also-invalid!!!"}):
            with self.assertRaises(ValueError):
                TerminalContentCipher()


class FileStoreIntegrationTests(unittest.TestCase):
    """Integration tests that exercise FileStore with a cipher against
    real temp directories. FileStore reads paths from `app.config.settings`
    so we patch those before importing FileStore.
    """

    def _make_store_and_dirs(self, key: str | None):
        tmp = tempfile.TemporaryDirectory()
        base = Path(tmp.name)
        sessions = base / "sessions"
        terminal = base / "terminal_logs"
        screenshots = base / "screenshots"
        faa = base / "faa"
        for p in [sessions, terminal, screenshots, faa]:
            p.mkdir()

        from app.core.storage.file_store import FileStore
        cipher = TerminalContentCipher(raw_key=key) if key is not None else TerminalContentCipher(raw_key="")
        store = FileStore(cipher=cipher)
        # FileStore.__init__ pulls dirs from app.config.settings; override
        # them on the instance so we don't mutate global config.
        store.sessions_dir = sessions
        store.terminal_logs_dir = terminal
        store.screenshots_dir = screenshots
        store.faa_dir = faa
        return store, sessions, terminal, tmp, []

    def _stop(self, patchers, tmp) -> None:
        for p in patchers:
            p.stop()
        tmp.cleanup()

    def _make_session_create(self, terminal_content: str = "secret payload") -> SessionCreate:
        return SessionCreate(
            title="Test session",
            description="test",
            tags=[],
            operation_id="op-123",
            operator_name="kali",
            targets=[],
            tools=[],
            findings=[],
            terminal_content=terminal_content,
            screenshots=[],
        )

    def test_terminal_log_on_disk_is_ciphertext(self) -> None:
        key = generate_key()
        store, sessions, terminal, tmp, patchers = self._make_store_and_dirs(key)
        try:
            secret = "root@box:~# cat /etc/shadow\nroot:$6$supersecret\n"
            created = _run(store.create_session(self._make_session_create(secret)))
            terminal_file = terminal / f"{created.id}.txt"
            raw = terminal_file.read_text(encoding="utf-8")
            self.assertNotIn(secret, raw)
            self.assertTrue(raw.startswith("gAAAAA"))
        finally:
            self._stop(patchers, tmp)

    def test_session_metadata_json_has_no_terminal_content(self) -> None:
        """Metadata JSON must not leak terminal content on disk."""
        key = generate_key()
        store, sessions, terminal, tmp, patchers = self._make_store_and_dirs(key)
        try:
            secret = "very-sensitive-terminal-output"
            created = _run(store.create_session(self._make_session_create(secret)))
            meta_file = sessions / f"{created.id}.json"
            raw = meta_file.read_text(encoding="utf-8")
            self.assertNotIn(secret, raw)
            parsed = json.loads(raw)
            self.assertEqual(parsed["terminal_content"], "")
        finally:
            self._stop(patchers, tmp)

    def test_get_session_returns_decrypted_content(self) -> None:
        key = generate_key()
        store, _sessions, _terminal, tmp, patchers = self._make_store_and_dirs(key)
        try:
            secret = "plaintext after decrypt"
            created = _run(store.create_session(self._make_session_create(secret)))
            loaded = _run(store.get_session(created.id))
            self.assertIsNotNone(loaded)
            self.assertEqual(loaded.terminal_content, secret)
        finally:
            self._stop(patchers, tmp)

    def test_list_sessions_returns_decrypted_content(self) -> None:
        key = generate_key()
        store, _sessions, _terminal, tmp, patchers = self._make_store_and_dirs(key)
        try:
            secret = "content visible via list"
            _run(store.create_session(self._make_session_create(secret)))
            sessions = _run(store.list_sessions())
            self.assertEqual(len(sessions), 1)
            self.assertEqual(sessions[0].terminal_content, secret)
        finally:
            self._stop(patchers, tmp)

    def test_legacy_plaintext_migrates_on_get(self) -> None:
        """Existing deployment: a plaintext .txt exists, operator sets
        the key, first get_session re-saves encrypted."""
        key = generate_key()
        store, _sessions, terminal, tmp, patchers = self._make_store_and_dirs(key)
        try:
            # Seed a session WITHOUT using the cipher (simulate legacy).
            legacy_content = "old plaintext terminal log"
            created = _run(store.create_session(self._make_session_create("placeholder")))
            terminal_file = terminal / f"{created.id}.txt"
            terminal_file.write_text(legacy_content, encoding="utf-8")

            # Now load through the encrypted store.
            loaded = _run(store.get_session(created.id))
            self.assertEqual(loaded.terminal_content, legacy_content)

            # File on disk must now be encrypted.
            raw = terminal_file.read_text(encoding="utf-8")
            self.assertNotIn(legacy_content, raw)
            self.assertTrue(raw.startswith("gAAAAA"))
        finally:
            self._stop(patchers, tmp)

    def test_no_key_fallback_stores_plaintext(self) -> None:
        """Upgrade path: operators who don't set the key still get a
        functional deployment."""
        store, _sessions, terminal, tmp, patchers = self._make_store_and_dirs(None)
        try:
            content = "still-plain-without-key"
            created = _run(store.create_session(self._make_session_create(content)))
            raw = (terminal / f"{created.id}.txt").read_text(encoding="utf-8")
            self.assertEqual(raw, content)
            loaded = _run(store.get_session(created.id))
            self.assertEqual(loaded.terminal_content, content)
        finally:
            self._stop(patchers, tmp)

    def test_update_session_reencrypts_new_content(self) -> None:
        from app.core.models import SessionUpdate
        key = generate_key()
        store, _sessions, terminal, tmp, patchers = self._make_store_and_dirs(key)
        try:
            created = _run(store.create_session(self._make_session_create("old")))
            _run(store.update_session(
                created.id,
                SessionUpdate(terminal_content="new-evidence-123"),
            ))
            raw = (terminal / f"{created.id}.txt").read_text(encoding="utf-8")
            self.assertNotIn("new-evidence-123", raw)
            self.assertTrue(raw.startswith("gAAAAA"))
            loaded = _run(store.get_session(created.id))
            self.assertEqual(loaded.terminal_content, "new-evidence-123")
        finally:
            self._stop(patchers, tmp)


if __name__ == "__main__":
    unittest.main()

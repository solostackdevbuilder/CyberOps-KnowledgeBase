"""
Tests for the browser_extension plugin.

The plugin wraps the red_team screenshot upload with a pairing-token gate.
These tests verify that:
- endpoints gated by require_token reject unconfigured/invalid tokens with 401
- token rotation generates fresh, high-entropy tokens
- valid requests update the last_heartbeat timestamp
- the download route streams a zip of the extension/ directory

Uses a tempdir-backed PluginDataStore to exercise the real storage path
rather than mocking it away - each test gets an isolated data_dir.
"""
import asyncio
import io
import secrets
import tempfile
import unittest
import zipfile
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.plugins.base import PluginManifest
from app.core.plugins.data_store import PluginDataStore
from app.plugins.browser_extension.plugin import BrowserExtensionPlugin


def _browser_extension_manifest() -> PluginManifest:
    """Minimal manifest matching the real browser_extension/manifest.json.

    Declaring storage:read_write is required for the PluginDataStore
    capability check to pass.
    """
    return PluginManifest(
        id="browser_extension",
        name="Browser Extension",
        version="1.0.0",
        plugin_type="hybrid",
        permissions=["storage:read_write"],
    )


def _run(coro):
    return asyncio.run(coro)


def _build_client() -> tuple[TestClient, BrowserExtensionPlugin, tempfile.TemporaryDirectory]:
    """Mount the plugin with an isolated tempdir data store."""
    tmp = tempfile.TemporaryDirectory()
    plugin = BrowserExtensionPlugin()
    plugin.manifest = _browser_extension_manifest()
    plugin._data_store = PluginDataStore(plugin.manifest, Path(tmp.name))

    app = FastAPI()
    app.include_router(plugin.get_routes())
    client = TestClient(app)
    return client, plugin, tmp


class HealthEndpointTests(unittest.TestCase):
    def test_initial_health_reports_no_token_configured(self) -> None:
        client, _plugin, tmp = _build_client()
        try:
            resp = client.get("/api/plugins/browser_extension/health")
            self.assertEqual(resp.status_code, 200)
            body = resp.json()
            self.assertEqual(body["status"], "ok")
            self.assertFalse(body["token_configured"])
            self.assertEqual(body["captures_total"], 0)
            self.assertIsNone(body["last_heartbeat"])
        finally:
            tmp.cleanup()

    def test_health_reports_token_configured_after_rotation(self) -> None:
        client, _plugin, tmp = _build_client()
        try:
            client.post("/api/plugins/browser_extension/token/rotate")
            body = client.get("/api/plugins/browser_extension/health").json()
            self.assertTrue(body["token_configured"])
        finally:
            tmp.cleanup()


class TokenRotationTests(unittest.TestCase):
    def test_rotate_returns_high_entropy_token(self) -> None:
        client, _plugin, tmp = _build_client()
        try:
            resp = client.post("/api/plugins/browser_extension/token/rotate")
            self.assertEqual(resp.status_code, 200)
            token = resp.json()["token"]
            # secrets.token_urlsafe(32) produces >= 40 url-safe chars.
            self.assertGreaterEqual(len(token), 40)
            self.assertTrue(all(c.isalnum() or c in "-_" for c in token))
        finally:
            tmp.cleanup()

    def test_rotate_invalidates_previous_token(self) -> None:
        client, _plugin, tmp = _build_client()
        try:
            first = client.post("/api/plugins/browser_extension/token/rotate").json()["token"]
            second = client.post("/api/plugins/browser_extension/token/rotate").json()["token"]
            self.assertNotEqual(first, second)

            # Old token must now be rejected.
            resp_old = client.get(
                "/api/plugins/browser_extension/sessions",
                headers={"X-Plugin-Token": first},
            )
            self.assertEqual(resp_old.status_code, 401)
        finally:
            tmp.cleanup()


class RequireTokenTests(unittest.TestCase):
    """Gate semantics on a token-protected endpoint (/sessions)."""

    def test_missing_header_returns_401_when_no_token_configured(self) -> None:
        client, _plugin, tmp = _build_client()
        try:
            resp = client.get("/api/plugins/browser_extension/sessions")
            self.assertEqual(resp.status_code, 401)
            self.assertIn("No pairing token", resp.json()["detail"])
        finally:
            tmp.cleanup()

    def test_missing_header_returns_401_after_token_rotated(self) -> None:
        client, _plugin, tmp = _build_client()
        try:
            client.post("/api/plugins/browser_extension/token/rotate")
            resp = client.get("/api/plugins/browser_extension/sessions")
            self.assertEqual(resp.status_code, 401)
            self.assertIn("Invalid pairing token", resp.json()["detail"])
        finally:
            tmp.cleanup()

    def test_wrong_token_rejected(self) -> None:
        client, _plugin, tmp = _build_client()
        try:
            client.post("/api/plugins/browser_extension/token/rotate")
            resp = client.get(
                "/api/plugins/browser_extension/sessions",
                headers={"X-Plugin-Token": "not-the-real-token"},
            )
            self.assertEqual(resp.status_code, 401)
        finally:
            tmp.cleanup()

    def test_timing_safe_compare_used(self) -> None:
        """Verify the plugin uses secrets.compare_digest (not ==).

        Timing-safe compare prevents network-observable token leaks via
        character-by-character short-circuit comparison. This test
        substitutes compare_digest with a counter to prove it runs.
        """
        client, _plugin, tmp = _build_client()
        try:
            client.post("/api/plugins/browser_extension/token/rotate")

            from app.plugins.browser_extension import plugin as mod
            call_count = {"n": 0}
            original = mod.secrets.compare_digest

            def counting(a: str, b: str) -> bool:
                call_count["n"] += 1
                return original(a, b)

            mod.secrets.compare_digest = counting  # type: ignore[assignment]
            try:
                client.get(
                    "/api/plugins/browser_extension/sessions",
                    headers={"X-Plugin-Token": "anything"},
                )
            finally:
                mod.secrets.compare_digest = original

            self.assertGreaterEqual(call_count["n"], 1)
        finally:
            tmp.cleanup()


class HeartbeatTests(unittest.TestCase):
    def test_valid_request_records_heartbeat(self) -> None:
        client, plugin, tmp = _build_client()
        try:
            token = client.post("/api/plugins/browser_extension/token/rotate").json()["token"]

            # Before: no heartbeat.
            self.assertIsNone(_run(plugin._get_heartbeat()))

            # Hit /sessions with a valid token. We don't care about the
            # body shape - only that require_token ran _record_heartbeat.
            # Storage is not wired, so /sessions will error internally, but
            # the heartbeat is recorded before that.
            try:
                client.get(
                    "/api/plugins/browser_extension/sessions",
                    headers={"X-Plugin-Token": token},
                )
            except Exception:
                pass

            heartbeat = _run(plugin._get_heartbeat())
            self.assertIsNotNone(heartbeat)
        finally:
            tmp.cleanup()


class DownloadRouteTests(unittest.TestCase):
    def test_download_streams_extension_zip(self) -> None:
        # The plugin ships an extension/ directory alongside plugin.py;
        # /download must produce a valid zip containing manifest.json.
        client, _plugin, tmp = _build_client()
        try:
            resp = client.get("/api/plugins/browser_extension/download")
            self.assertEqual(resp.status_code, 200)
            self.assertEqual(resp.headers["content-type"], "application/zip")
            self.assertIn("cyops-capture.zip", resp.headers["content-disposition"])

            zf = zipfile.ZipFile(io.BytesIO(resp.content))
            names = zf.namelist()
            # Must include the manifest and the background service worker.
            self.assertIn("manifest.json", names)
            self.assertTrue(any(n.endswith("background.js") for n in names))
        finally:
            tmp.cleanup()


class CaptureCountTests(unittest.TestCase):
    def test_capture_count_persists_across_loads(self) -> None:
        plugin1 = BrowserExtensionPlugin()
        with tempfile.TemporaryDirectory() as tmpdir:
            manifest = _browser_extension_manifest()
            plugin1.manifest = manifest
            plugin1._data_store = PluginDataStore(manifest, Path(tmpdir))
            _run(plugin1._incr_capture_count())
            _run(plugin1._incr_capture_count())
            self.assertEqual(_run(plugin1._get_capture_count()), 2)

            # Second plugin instance pointing at the same dir should see
            # the same count - exercises the persistence path.
            plugin2 = BrowserExtensionPlugin()
            plugin2.manifest = manifest
            plugin2._data_store = PluginDataStore(manifest, Path(tmpdir))
            self.assertEqual(_run(plugin2._get_capture_count()), 2)


if __name__ == "__main__":
    unittest.main()

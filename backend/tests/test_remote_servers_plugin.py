"""
Tests for the remote_servers plugin.

Critical behaviors verified here:
- Credentials are stored in a separate collection from server metadata
  (blast-radius minimization on a stolen store)
- Partial updates MUST NOT wipe existing password/private_key fields when
  the update payload omits them - regression-risk if the merge logic changes
- find_servers_with_tool filters strictly by installed_tools
- _ssh_user_known_hosts_null returns the right device per-OS

SSH execution is not exercised here - it would require mocking asyncssh
or spawning real ssh. Those can be added later as integration tests.
"""
import asyncio
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.plugins.base import PluginManifest
from app.core.plugins.data_store import PluginDataStore
from app.plugins.remote_servers.credential_store import EncryptedCredentialStore
from app.core.plugins.ssh import _ssh_user_known_hosts_null
from app.plugins.remote_servers.plugin import RemoteServersPlugin


def _run(coro):
    return asyncio.run(coro)


def _remote_servers_manifest() -> PluginManifest:
    """Minimal manifest matching the real remote_servers/manifest.json."""
    return PluginManifest(
        id="remote_servers",
        name="Remote Servers",
        version="1.0.0",
        plugin_type="hybrid",
        permissions=["network:outbound", "storage:read_write", "credentials:read"],
    )


def _make_plugin() -> tuple[RemoteServersPlugin, tempfile.TemporaryDirectory]:
    tmp = tempfile.TemporaryDirectory()
    plugin = RemoteServersPlugin()
    plugin.manifest = _remote_servers_manifest()
    plugin._data_store = PluginDataStore(plugin.manifest, Path(tmp.name))
    # EncryptedCredentialStore falls back to plaintext when
    # CYBEROPS_CREDENTIALS_KEY is unset (tests don't set it), so CRUD and
    # direct _data_store reads continue to work as before.
    plugin._credential_store = EncryptedCredentialStore(plugin._data_store)
    plugin._known_tools = ["hashcat", "nmap", "john"]
    return plugin, tmp


def _build_client() -> tuple[TestClient, RemoteServersPlugin, tempfile.TemporaryDirectory]:
    plugin, tmp = _make_plugin()
    app = FastAPI()
    app.include_router(plugin.get_routes())
    return TestClient(app), plugin, tmp


# ---------------------------------------------------------------------------
# OS-agnostic helpers
# ---------------------------------------------------------------------------


class SshKnownHostsNullTests(unittest.TestCase):
    def test_returns_os_appropriate_null_device(self) -> None:
        expected = "NUL" if os.name == "nt" else "/dev/null"
        self.assertEqual(_ssh_user_known_hosts_null(), expected)

    def test_uses_posix_null_when_not_nt(self) -> None:
        with patch("app.core.plugins.ssh.os") as m:
            m.name = "posix"
            self.assertEqual(_ssh_user_known_hosts_null(), "/dev/null")

    def test_uses_windows_null_when_nt(self) -> None:
        with patch("app.core.plugins.ssh.os") as m:
            m.name = "nt"
            self.assertEqual(_ssh_user_known_hosts_null(), "NUL")


# ---------------------------------------------------------------------------
# CRUD + credential isolation
# ---------------------------------------------------------------------------


class AddServerTests(unittest.TestCase):
    def test_add_server_stores_metadata_and_credentials_separately(self) -> None:
        client, plugin, tmp = _build_client()
        try:
            payload = {
                "name": "Cracker 1",
                "credentials": {
                    "host": "10.0.0.1",
                    "port": 2222,
                    "username": "kali",
                    "auth_method": "password",
                    "password": "sup3r-s3cret",
                },
                "tags": ["gpu"],
                "notes": "test rig",
            }
            resp = client.post("/api/plugins/remote_servers/servers", json=payload)
            self.assertEqual(resp.status_code, 200)
            body = resp.json()
            server_id = body["id"]

            # Server metadata must not carry the password - that lives in
            # the credentials collection only.
            self.assertNotIn("password", body)

            server_doc = _run(plugin._data_store.load("servers", server_id))
            self.assertIsNotNone(server_doc)
            self.assertNotIn("password", server_doc or {})

            cred_doc = _run(plugin._data_store.load("credentials", server_id))
            self.assertEqual(cred_doc["password"], "sup3r-s3cret")
        finally:
            tmp.cleanup()

    def test_list_after_add_returns_server(self) -> None:
        client, _plugin, tmp = _build_client()
        try:
            client.post("/api/plugins/remote_servers/servers", json={
                "name": "alpha",
                "credentials": {"host": "h1", "username": "u"},
            })
            client.post("/api/plugins/remote_servers/servers", json={
                "name": "beta",
                "credentials": {"host": "h2", "username": "u"},
            })
            resp = client.get("/api/plugins/remote_servers/servers")
            self.assertEqual(resp.status_code, 200)
            names = {s["name"] for s in resp.json()}
            self.assertEqual(names, {"alpha", "beta"})
        finally:
            tmp.cleanup()

    def test_get_missing_server_returns_404(self) -> None:
        client, _plugin, tmp = _build_client()
        try:
            resp = client.get("/api/plugins/remote_servers/servers/nope")
            self.assertEqual(resp.status_code, 404)
        finally:
            tmp.cleanup()


class UpdateServerCredentialMergeTests(unittest.TestCase):
    """The update route must not wipe stored secrets when the payload
    omits password / private_key / passphrase fields. This is the class
    of bug that silently locks you out of every remote box you manage."""

    def _add_server(self, client: TestClient, password: str = "orig-pw") -> str:
        resp = client.post("/api/plugins/remote_servers/servers", json={
            "name": "rig",
            "credentials": {
                "host": "1.2.3.4",
                "port": 22,
                "username": "kali",
                "auth_method": "password",
                "password": password,
            },
        })
        return resp.json()["id"]

    def test_update_without_password_preserves_stored_password(self) -> None:
        client, plugin, tmp = _build_client()
        try:
            server_id = self._add_server(client, password="orig-pw")

            # Partial update that intentionally omits password.
            resp = client.put(f"/api/plugins/remote_servers/servers/{server_id}", json={
                "name": "renamed",
                "credentials": {
                    "host": "1.2.3.4",
                    "port": 22,
                    "username": "kali",
                    "auth_method": "password",
                    # password intentionally omitted
                },
            })
            self.assertEqual(resp.status_code, 200)

            # Original password must still be in the store.
            creds = _run(plugin._data_store.load("credentials", server_id))
            self.assertEqual(creds["password"], "orig-pw")
        finally:
            tmp.cleanup()

    def test_update_with_blank_password_preserves_stored_password(self) -> None:
        # The merge logic treats empty strings as "keep existing". Pin this.
        client, plugin, tmp = _build_client()
        try:
            server_id = self._add_server(client, password="orig-pw")
            client.put(f"/api/plugins/remote_servers/servers/{server_id}", json={
                "credentials": {
                    "host": "1.2.3.4",
                    "port": 22,
                    "username": "kali",
                    "auth_method": "password",
                    "password": "   ",  # whitespace only
                },
            })
            creds = _run(plugin._data_store.load("credentials", server_id))
            self.assertEqual(creds["password"], "orig-pw")
        finally:
            tmp.cleanup()

    def test_update_with_new_password_overwrites(self) -> None:
        client, plugin, tmp = _build_client()
        try:
            server_id = self._add_server(client, password="orig-pw")
            client.put(f"/api/plugins/remote_servers/servers/{server_id}", json={
                "credentials": {
                    "host": "1.2.3.4",
                    "port": 22,
                    "username": "kali",
                    "auth_method": "password",
                    "password": "new-pw",
                },
            })
            creds = _run(plugin._data_store.load("credentials", server_id))
            self.assertEqual(creds["password"], "new-pw")
        finally:
            tmp.cleanup()


class DeleteServerTests(unittest.TestCase):
    def test_delete_removes_both_metadata_and_credentials(self) -> None:
        client, plugin, tmp = _build_client()
        try:
            resp = client.post("/api/plugins/remote_servers/servers", json={
                "name": "ghost",
                "credentials": {"host": "h", "username": "u", "password": "p"},
            })
            server_id = resp.json()["id"]

            # Confirm both collections have the entry.
            self.assertIsNotNone(_run(plugin._data_store.load("servers", server_id)))
            self.assertIsNotNone(_run(plugin._data_store.load("credentials", server_id)))

            client.delete(f"/api/plugins/remote_servers/servers/{server_id}")

            self.assertIsNone(_run(plugin._data_store.load("servers", server_id)))
            self.assertIsNone(_run(plugin._data_store.load("credentials", server_id)))
        finally:
            tmp.cleanup()

    def test_delete_missing_server_returns_404(self) -> None:
        client, _plugin, tmp = _build_client()
        try:
            resp = client.delete("/api/plugins/remote_servers/servers/nope")
            self.assertEqual(resp.status_code, 404)
        finally:
            tmp.cleanup()


class FindServersWithToolTests(unittest.TestCase):
    def test_only_servers_with_tool_are_returned(self) -> None:
        plugin, tmp = _make_plugin()
        try:
            _run(plugin._save_server("s1", {
                "id": "s1", "name": "has-hashcat",
                "installed_tools": ["hashcat", "nmap"],
                "status": "online",
            }))
            _run(plugin._save_credentials("s1", {
                "host": "1.1.1.1", "port": 22, "username": "u",
            }))
            _run(plugin._save_server("s2", {
                "id": "s2", "name": "no-hashcat",
                "installed_tools": ["john"],
                "status": "online",
            }))
            _run(plugin._save_credentials("s2", {
                "host": "2.2.2.2", "port": 22, "username": "u",
            }))

            matches = _run(plugin.find_servers_with_tool("hashcat"))
            self.assertEqual([m["id"] for m in matches], ["s1"])
            self.assertEqual(matches[0]["host"], "1.1.1.1")
        finally:
            tmp.cleanup()

    def test_empty_store_returns_empty_list(self) -> None:
        plugin, tmp = _make_plugin()
        try:
            self.assertEqual(_run(plugin.find_servers_with_tool("hashcat")), [])
        finally:
            tmp.cleanup()


class HealthCheckTests(unittest.TestCase):
    def test_health_reports_server_count(self) -> None:
        plugin, tmp = _make_plugin()
        try:
            _run(plugin._save_server("s1", {"id": "s1"}))
            _run(plugin._save_server("s2", {"id": "s2"}))
            health = _run(plugin.health_check())
            self.assertEqual(health["status"], "ok")
            self.assertEqual(health["plugin"], "remote_servers")
            self.assertEqual(health["server_count"], 2)
            self.assertIn(health["ssh_backend"], {"asyncssh", "subprocess"})
        finally:
            tmp.cleanup()


class DiscoverEndpointTests(unittest.TestCase):
    def test_discover_returns_tool_match_count(self) -> None:
        client, plugin, tmp = _build_client()
        try:
            _run(plugin._save_server("srv", {
                "id": "srv", "name": "n",
                "installed_tools": ["hashcat"],
                "status": "online",
            }))
            _run(plugin._save_credentials("srv", {
                "host": "1.1.1.1", "port": 22, "username": "u",
            }))

            resp = client.get("/api/plugins/remote_servers/discover/hashcat")
            self.assertEqual(resp.status_code, 200)
            body = resp.json()
            self.assertEqual(body["tool"], "hashcat")
            self.assertEqual(body["count"], 1)
            self.assertEqual(body["servers"][0]["id"], "srv")

            # Tool with no matches returns empty list, count 0.
            resp = client.get("/api/plugins/remote_servers/discover/does-not-exist")
            self.assertEqual(resp.json()["count"], 0)
        finally:
            tmp.cleanup()


if __name__ == "__main__":
    unittest.main()

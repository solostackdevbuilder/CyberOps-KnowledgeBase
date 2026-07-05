"""
Tests for SSH host-key pinning (remote_servers plugin).

Layered:
- HostKeyStore CRUD (pure data layer)
- _run_ssh_command pinning branches, exercised with asyncssh.connect
  patched out (we don't spin up a real SSH server in CI)
- /servers/{id}/rekey endpoint behavior

Pinning only kicks in when both host_key_store and server_id are passed
to _run_ssh_command. Tests assert on the behavior; asyncssh itself is
the authoritative verifier of the matching.
"""
import asyncio
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.plugins.base import PluginManifest
from app.core.plugins.data_store import PluginDataStore
from app.core.plugins.ssh import HostKeyMismatch, _run_ssh_command
from app.plugins.remote_servers.credential_store import EncryptedCredentialStore
from app.plugins.remote_servers.host_key_store import HostKeyStore
from app.plugins.remote_servers.plugin import RemoteServersPlugin


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


# ---------------------------------------------------------------------------
# HostKeyStore: pure data layer
# ---------------------------------------------------------------------------


class HostKeyStoreTests(unittest.TestCase):
    def test_get_missing_returns_none(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            data = PluginDataStore(_manifest(), Path(tmp))
            store = HostKeyStore(data)
            self.assertIsNone(_run(store.get_pinned_key("srv")))

    def test_pin_and_retrieve_round_trip(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            data = PluginDataStore(_manifest(), Path(tmp))
            store = HostKeyStore(data)
            key = "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIabcdef"
            _run(store.pin("srv", "1.2.3.4", key))
            self.assertEqual(_run(store.get_pinned_key("srv")), key)

    def test_pin_strips_whitespace(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            data = PluginDataStore(_manifest(), Path(tmp))
            store = HostKeyStore(data)
            _run(store.pin("srv", "host", "  ssh-rsa AAAA\n"))
            self.assertEqual(_run(store.get_pinned_key("srv")), "ssh-rsa AAAA")

    def test_pin_rejects_empty_key(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            data = PluginDataStore(_manifest(), Path(tmp))
            store = HostKeyStore(data)
            for bad in ("", "   ", "\n"):
                with self.subTest(value=bad):
                    with self.assertRaises(ValueError):
                        _run(store.pin("srv", "host", bad))

    def test_clear_returns_true_when_removed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            data = PluginDataStore(_manifest(), Path(tmp))
            store = HostKeyStore(data)
            _run(store.pin("srv", "host", "ssh-rsa AAAA"))
            self.assertTrue(_run(store.clear("srv")))
            self.assertIsNone(_run(store.get_pinned_key("srv")))

    def test_clear_returns_false_when_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            data = PluginDataStore(_manifest(), Path(tmp))
            store = HostKeyStore(data)
            self.assertFalse(_run(store.clear("nope")))

    def test_list_pinned_returns_server_ids(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            data = PluginDataStore(_manifest(), Path(tmp))
            store = HostKeyStore(data)
            _run(store.pin("a", "h1", "ssh-rsa X"))
            _run(store.pin("b", "h2", "ssh-rsa Y"))
            pinned = _run(store.list_pinned())
            self.assertEqual(set(pinned), {"a", "b"})


# ---------------------------------------------------------------------------
# _run_ssh_command pinning branches with asyncssh patched out
# ---------------------------------------------------------------------------


def _fake_asyncssh_connect(server_key_str: str):
    """Build an async-context-manager mock for asyncssh.connect.

    The connection's get_server_host_key() returns an object whose
    export_public_key() returns the given key as bytes. `conn.run()`
    returns a completed result object.
    """
    server_key_obj = MagicMock()
    server_key_obj.export_public_key.return_value = server_key_str.encode("ascii")

    run_result = MagicMock()
    run_result.exit_status = 0
    run_result.stdout = "ok"
    run_result.stderr = ""

    conn = MagicMock()
    conn.get_server_host_key.return_value = server_key_obj
    conn.run = AsyncMock(return_value=run_result)

    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=conn)
    ctx.__aexit__ = AsyncMock(return_value=None)

    connect = MagicMock(return_value=ctx)
    return connect, conn


class RunSshCommandPinningTests(unittest.TestCase):
    def _make_store(self) -> tuple[HostKeyStore, tempfile.TemporaryDirectory]:
        tmp = tempfile.TemporaryDirectory()
        data = PluginDataStore(_manifest(), Path(tmp.name))
        return HostKeyStore(data), tmp

    def test_without_pinning_args_no_pin_is_stored(self) -> None:
        """Back-compat: callers that don't pass host_key_store+server_id
        get the old unpinned behavior and no data is written."""
        store, tmp = self._make_store()
        try:
            connect, _ = _fake_asyncssh_connect("ssh-ed25519 AAAA")
            with patch("asyncssh.connect", connect), \
                 patch("asyncssh.import_known_hosts"), \
                 patch("asyncssh.import_private_key"):
                result = _run(_run_ssh_command(
                    _manifest(),
                    host="1.2.3.4", port=22, username="kali",
                    password="pw", private_key=None, passphrase=None,
                    command="uname -a",
                ))

            self.assertEqual(result.status, "completed")
            # No pin because we didn't request pinning.
            self.assertEqual(_run(store.list_pinned()), [])
        finally:
            tmp.cleanup()

    def test_tofu_captures_key_on_first_connect(self) -> None:
        store, tmp = self._make_store()
        try:
            key_str = "ssh-ed25519 AAAA-FIRST-KEY"
            connect, _ = _fake_asyncssh_connect(key_str)
            with patch("asyncssh.connect", connect), \
                 patch("asyncssh.import_known_hosts") as ikh, \
                 patch("asyncssh.import_private_key"):
                result = _run(_run_ssh_command(
                    _manifest(),
                    host="1.2.3.4", port=22, username="kali",
                    password="pw", private_key=None, passphrase=None,
                    command="uname -a",
                    host_key_store=store, server_id="srv1",
                ))

            self.assertEqual(result.status, "completed")
            # TOFU path should not have called import_known_hosts (no pin yet).
            ikh.assert_not_called()
            # And the key should now be pinned.
            self.assertEqual(_run(store.get_pinned_key("srv1")), key_str)
        finally:
            tmp.cleanup()

    def test_second_connect_passes_known_hosts_with_pinned_key(self) -> None:
        store, tmp = self._make_store()
        try:
            key_str = "ssh-ed25519 AAAA-PINNED"
            _run(store.pin("srv1", "1.2.3.4", key_str))

            connect, _ = _fake_asyncssh_connect(key_str)
            with patch("asyncssh.connect", connect), \
                 patch("asyncssh.import_known_hosts", return_value="KNOWN_HOSTS_OBJ") as ikh, \
                 patch("asyncssh.import_private_key"):
                result = _run(_run_ssh_command(
                    _manifest(),
                    host="1.2.3.4", port=22, username="kali",
                    password="pw", private_key=None, passphrase=None,
                    command="uname -a",
                    host_key_store=store, server_id="srv1",
                ))

            self.assertEqual(result.status, "completed")
            # Strict match path passes known_hosts carrying the pinned key.
            ikh.assert_called_once_with(f"1.2.3.4 {key_str}")
            # asyncssh.connect should have received the parsed known_hosts.
            connect_kwargs = connect.call_args.kwargs
            self.assertEqual(connect_kwargs["known_hosts"], "KNOWN_HOSTS_OBJ")
        finally:
            tmp.cleanup()

    def test_mismatch_returns_failed_with_clear_rekey_guidance(self) -> None:
        store, tmp = self._make_store()
        try:
            _run(store.pin("srv1", "1.2.3.4", "ssh-ed25519 AAAA-OLD"))

            import asyncssh
            # Simulate asyncssh refusing the connection because the server
            # presented a different key than what's pinned.
            def _raise(*args, **kwargs):
                raise asyncssh.HostKeyNotVerifiable("host key differs")

            with patch("asyncssh.connect", side_effect=_raise), \
                 patch("asyncssh.import_known_hosts", return_value="kh"), \
                 patch("asyncssh.import_private_key"):
                result = _run(_run_ssh_command(
                    _manifest(),
                    host="1.2.3.4", port=22, username="kali",
                    password="pw", private_key=None, passphrase=None,
                    command="uname -a",
                    host_key_store=store, server_id="srv1",
                ))

            self.assertEqual(result.status, "failed")
            self.assertIn("rekey", (result.error or "").lower())
            self.assertIn("srv1", result.error or "")
        finally:
            tmp.cleanup()


# ---------------------------------------------------------------------------
# /rekey endpoint + delete_server pin cleanup
# ---------------------------------------------------------------------------


def _build_client() -> tuple[TestClient, RemoteServersPlugin, tempfile.TemporaryDirectory]:
    tmp = tempfile.TemporaryDirectory()
    plugin = RemoteServersPlugin()
    plugin.manifest = _manifest()
    plugin._data_store = PluginDataStore(plugin.manifest, Path(tmp.name))
    plugin._credential_store = EncryptedCredentialStore(plugin._data_store)
    plugin._host_key_store = HostKeyStore(plugin._data_store)
    plugin._known_tools = ["hashcat"]

    app = FastAPI()
    app.include_router(plugin.get_routes())
    return TestClient(app), plugin, tmp


class RekeyEndpointTests(unittest.TestCase):
    def _add_server(self, client: TestClient) -> str:
        resp = client.post("/api/plugins/remote_servers/servers", json={
            "name": "rig",
            "credentials": {"host": "1.2.3.4", "port": 22, "username": "kali", "password": "p"},
        })
        return resp.json()["id"]

    def test_rekey_clears_pinned_key(self) -> None:
        client, plugin, tmp = _build_client()
        try:
            server_id = self._add_server(client)
            _run(plugin._host_key_store.pin(server_id, "1.2.3.4", "ssh-rsa PINNED"))

            resp = client.post(f"/api/plugins/remote_servers/servers/{server_id}/rekey")
            self.assertEqual(resp.status_code, 200)
            self.assertEqual(resp.json()["status"], "rekeyed")
            self.assertIsNone(_run(plugin._host_key_store.get_pinned_key(server_id)))
        finally:
            tmp.cleanup()

    def test_rekey_when_no_pin_reports_no_pin_present(self) -> None:
        client, _plugin, tmp = _build_client()
        try:
            server_id = self._add_server(client)
            resp = client.post(f"/api/plugins/remote_servers/servers/{server_id}/rekey")
            self.assertEqual(resp.status_code, 200)
            self.assertEqual(resp.json()["status"], "no_pin_present")
        finally:
            tmp.cleanup()

    def test_rekey_missing_server_returns_404(self) -> None:
        client, _plugin, tmp = _build_client()
        try:
            resp = client.post("/api/plugins/remote_servers/servers/ghost/rekey")
            self.assertEqual(resp.status_code, 404)
        finally:
            tmp.cleanup()

    def test_delete_server_also_clears_pin(self) -> None:
        client, plugin, tmp = _build_client()
        try:
            server_id = self._add_server(client)
            _run(plugin._host_key_store.pin(server_id, "1.2.3.4", "ssh-rsa PINNED"))

            client.delete(f"/api/plugins/remote_servers/servers/{server_id}")
            self.assertIsNone(_run(plugin._host_key_store.get_pinned_key(server_id)))
        finally:
            tmp.cleanup()


class HostKeyMismatchExceptionTests(unittest.TestCase):
    def test_message_points_at_rekey_endpoint(self) -> None:
        exc = HostKeyMismatch(
            server_id="s1", host="1.2.3.4",
            expected="ssh-rsa OLD", actual="ssh-rsa NEW",
        )
        msg = str(exc)
        self.assertIn("s1", msg)
        self.assertIn("1.2.3.4", msg)
        self.assertIn("rekey", msg.lower())
        self.assertIn("MITM", msg)  # Be explicit about the scary scenario.


if __name__ == "__main__":
    unittest.main()

"""
Coverage for the hashcat plugin's execution dispatch and response parsing.

test_hashcat_plugin.py pins the shell-injection regression (Chunk 4). This
file exercises the surrounding behavior: hash_type / attack_mode dispatch,
the failure paths, the JSON input schema, and the hashcat output parser
(hash:password + Exhausted detection) that lives in the crack_hash route.
"""
import asyncio
import unittest
from unittest.mock import AsyncMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.plugins.base import ToolResult
from app.plugins.hashcat.plugin import ATTACK_MODES, HASH_TYPES, HashcatPlugin


def _run(coro):
    return asyncio.run(coro)


class ExecuteDispatchTests(unittest.TestCase):
    """execute() must validate inputs and route to the correct backend."""

    def setUp(self) -> None:
        self.plugin = HashcatPlugin()

    def test_unknown_hash_type_returns_failed(self) -> None:
        result = _run(
            self.plugin.execute(
                {"hash_value": "abc", "hash_type": "not-a-real-hash"}
            )
        )
        self.assertEqual(result.status, "failed")
        self.assertIn("Unknown hash type", result.error or "")

    def test_unknown_attack_mode_returns_failed(self) -> None:
        result = _run(
            self.plugin.execute(
                {"hash_value": "abc", "attack_mode": "telepathy"}
            )
        )
        self.assertEqual(result.status, "failed")
        self.assertIn("Unknown attack mode", result.error or "")

    def test_local_mode_without_hashcat_binary_returns_failed(self) -> None:
        # Fresh plugin has _hashcat_available=False and _execution_mode="local".
        result = _run(
            self.plugin.execute(
                {"hash_value": "abc", "hash_type": "md5"}
            )
        )
        self.assertEqual(result.status, "failed")
        self.assertIn("not available", (result.error or "").lower())

    def test_remote_mode_without_adapter_returns_failed(self) -> None:
        self.plugin._execution_mode = "remote"
        result = _run(
            self.plugin.execute(
                {"hash_value": "abc", "hash_type": "md5"}
            )
        )
        self.assertEqual(result.status, "failed")
        self.assertIn("not configured", (result.error or "").lower())

    def test_invalid_execution_mode_returns_failed(self) -> None:
        self.plugin._execution_mode = "carrier-pigeon"
        result = _run(
            self.plugin.execute(
                {"hash_value": "abc", "hash_type": "md5"}
            )
        )
        self.assertEqual(result.status, "failed")

    def test_server_id_dispatches_to_remote_server_path(self) -> None:
        # With no remote_servers plugin loaded, the server-scoped execution
        # must surface a clear error rather than crashing.
        with patch("app.plugins.hashcat.plugin.HashcatPlugin._execute_on_server", new=AsyncMock(
            return_value=ToolResult(status="failed", error="Remote Servers plugin is not loaded")
        )) as mock_exec:
            result = _run(
                self.plugin.execute(
                    {
                        "hash_value": "abc",
                        "hash_type": "md5",
                        "attack_mode": "dictionary",
                        "server_id": "srv1",
                    }
                )
            )
            mock_exec.assert_called_once()
            self.assertEqual(result.status, "failed")
            self.assertIn("Remote Servers", result.error or "")


class InputSchemaTests(unittest.TestCase):
    def test_schema_exposes_expected_fields(self) -> None:
        schema = HashcatPlugin().get_input_schema()
        self.assertEqual(schema["type"], "object")
        props = schema["properties"]
        for key in ("hash_value", "hash_type", "attack_mode", "wordlist", "mask"):
            self.assertIn(key, props)
        self.assertEqual(schema["required"], ["hash_value"])

    def test_schema_hash_type_enum_covers_known_types(self) -> None:
        schema = HashcatPlugin().get_input_schema()
        enum = set(schema["properties"]["hash_type"]["enum"])
        # "auto" plus every key in HASH_TYPES is the contract.
        self.assertIn("auto", enum)
        self.assertTrue(set(HASH_TYPES.keys()).issubset(enum))

    def test_schema_attack_mode_enum_matches_attack_modes(self) -> None:
        schema = HashcatPlugin().get_input_schema()
        self.assertEqual(
            set(schema["properties"]["attack_mode"]["enum"]),
            set(ATTACK_MODES.keys()),
        )


# ---------------------------------------------------------------------------
# Crack endpoint parsing: spins up a mini FastAPI app with only the hashcat
# router, mocks execute() to return canned hashcat output, and verifies the
# response shape (cracked passwords extracted, Exhausted detected).
# ---------------------------------------------------------------------------


def _build_client(plugin: HashcatPlugin) -> TestClient:
    """Mount just the plugin router on a fresh FastAPI app.

    We don't use the real data_store, so set it to None to short-circuit
    save/load in the route. The plugin handles None defensively.
    """
    app = FastAPI()
    app.include_router(plugin.get_routes())
    plugin._data_store = None
    return TestClient(app)


class CrackResponseParsingTests(unittest.TestCase):
    def test_cracked_hash_parsed_from_output(self) -> None:
        plugin = HashcatPlugin()
        cracked_output = (
            "Session..........: hashcat\n"
            "Status...........: Cracked\n"
            "8743b52063cd84097a65d1633f5c74f5:hello\n"
        )
        plugin.execute = AsyncMock(return_value=ToolResult(
            status="completed", output=cracked_output
        ))
        client = _build_client(plugin)

        resp = client.post(
            "/api/plugins/hashcat/crack",
            json={
                "hash_value": "8743b52063cd84097a65d1633f5c74f5",
                "hash_type": "md5",
                "attack_mode": "dictionary",
            },
        )
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["status"], "cracked")
        self.assertEqual(body["message"], "Password found: hello")

    def test_exhausted_keyspace_detected(self) -> None:
        plugin = HashcatPlugin()
        exhausted_output = (
            "Session..........: hashcat\n"
            "Status...........: Exhausted\n"
            "Recovered........: 0/1 (0.00%) Digests\n"
        )
        plugin.execute = AsyncMock(return_value=ToolResult(
            status="completed", output=exhausted_output
        ))
        client = _build_client(plugin)

        resp = client.post(
            "/api/plugins/hashcat/crack",
            json={"hash_value": "abc", "hash_type": "md5"},
        )
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["status"], "exhausted")
        self.assertIn("Exhausted", body["message"])

    def test_completed_without_crack_reports_no_match(self) -> None:
        plugin = HashcatPlugin()
        plugin.execute = AsyncMock(return_value=ToolResult(
            status="completed", output="Session starting...\n"
        ))
        client = _build_client(plugin)

        resp = client.post(
            "/api/plugins/hashcat/crack",
            json={"hash_value": "abc", "hash_type": "md5"},
        )
        body = resp.json()
        self.assertEqual(body["status"], "completed")
        self.assertIn("no match", body["message"].lower())

    def test_timeout_surfaces_helpful_message(self) -> None:
        plugin = HashcatPlugin()
        plugin.execute = AsyncMock(return_value=ToolResult(
            status="timeout", error="exceeded max_runtime"
        ))
        client = _build_client(plugin)

        resp = client.post(
            "/api/plugins/hashcat/crack",
            json={"hash_value": "abc", "hash_type": "md5"},
        )
        body = resp.json()
        self.assertEqual(body["status"], "timeout")
        self.assertIn("timed out", body["message"])

    def test_list_endpoints_expose_known_types(self) -> None:
        client = _build_client(HashcatPlugin())
        hash_resp = client.get("/api/plugins/hashcat/hash-types")
        self.assertEqual(hash_resp.status_code, 200)
        self.assertIn("md5", hash_resp.json()["hash_types"])

        mode_resp = client.get("/api/plugins/hashcat/attack-modes")
        self.assertEqual(mode_resp.status_code, 200)
        self.assertIn("dictionary", mode_resp.json()["attack_modes"])


if __name__ == "__main__":
    unittest.main()

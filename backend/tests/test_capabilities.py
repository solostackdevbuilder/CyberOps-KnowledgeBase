"""
Tests for the plugin capability enforcement layer.

Covers:
- require() passes when a capability is declared, raises otherwise
- check_declared() rejects unknown capability names (typo detection)
- has() is a non-raising predicate
- CYBEROPS_DISABLED_CAPABILITIES env var overrides individual declarations
- LocalCLIAdapter / RemoteAgentAdapter / PluginDataStore refuse to
  construct when the manifest does not declare the matching capability
  (the integration surface that future plugins will hit)
"""
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.core.plugins.base import PluginManifest
from app.core.plugins.capabilities import (
    CREDENTIALS_READ,
    KNOWN_CAPABILITIES,
    NETWORK_OUTBOUND,
    SHELL_EXECUTE,
    STORAGE_READ_WRITE,
    CapabilityConfigError,
    PermissionDenied,
    check_declared,
    declared_capabilities,
    has,
    require,
)
from app.core.plugins.data_store import PluginDataStore
from app.core.plugins.execution import LocalCLIAdapter, RemoteAgentAdapter


def _manifest(*permissions: str) -> PluginManifest:
    return PluginManifest(
        id="test_plugin",
        name="Test",
        version="1.0.0",
        plugin_type="tool",
        permissions=list(permissions),
    )


class RequireTests(unittest.TestCase):
    def test_passes_when_declared(self) -> None:
        # No exception = pass; the call returns None.
        self.assertIsNone(require(_manifest(SHELL_EXECUTE), SHELL_EXECUTE))

    def test_raises_when_missing(self) -> None:
        with self.assertRaises(PermissionDenied) as ctx:
            require(_manifest(STORAGE_READ_WRITE), SHELL_EXECUTE)
        err = ctx.exception
        self.assertEqual(err.plugin_id, "test_plugin")
        self.assertEqual(err.capability, SHELL_EXECUTE)
        self.assertIn("manifest.json", str(err))

    def test_env_var_disables_capability_globally(self) -> None:
        manifest = _manifest(SHELL_EXECUTE)
        with patch.dict(os.environ, {"CYBEROPS_DISABLED_CAPABILITIES": "shell:execute"}):
            with self.assertRaises(PermissionDenied) as ctx:
                require(manifest, SHELL_EXECUTE)
            self.assertIn("globally disabled", str(ctx.exception))

    def test_env_var_accepts_comma_list(self) -> None:
        manifest = _manifest(SHELL_EXECUTE, NETWORK_OUTBOUND)
        with patch.dict(
            os.environ,
            {"CYBEROPS_DISABLED_CAPABILITIES": "shell:execute, network:outbound"},
        ):
            with self.assertRaises(PermissionDenied):
                require(manifest, SHELL_EXECUTE)
            with self.assertRaises(PermissionDenied):
                require(manifest, NETWORK_OUTBOUND)


class HasTests(unittest.TestCase):
    def test_returns_true_when_declared(self) -> None:
        self.assertTrue(has(_manifest(STORAGE_READ_WRITE), STORAGE_READ_WRITE))

    def test_returns_false_when_missing(self) -> None:
        self.assertFalse(has(_manifest(), SHELL_EXECUTE))

    def test_honors_global_disable(self) -> None:
        manifest = _manifest(SHELL_EXECUTE)
        with patch.dict(os.environ, {"CYBEROPS_DISABLED_CAPABILITIES": "shell:execute"}):
            self.assertFalse(has(manifest, SHELL_EXECUTE))


class CheckDeclaredTests(unittest.TestCase):
    """Catches typos like `shell:exec` before they silently grant nothing."""

    def test_known_capabilities_pass(self) -> None:
        manifest = _manifest(SHELL_EXECUTE, NETWORK_OUTBOUND, STORAGE_READ_WRITE, CREDENTIALS_READ)
        # Should not raise - all four are known.
        check_declared(manifest)

    def test_unknown_capability_raises(self) -> None:
        manifest = _manifest("shell:exec")  # missing 'ute'
        with self.assertRaises(CapabilityConfigError) as ctx:
            check_declared(manifest)
        self.assertIn("shell:exec", str(ctx.exception))
        # Error lists the known set so the fix is obvious.
        for capability in KNOWN_CAPABILITIES:
            self.assertIn(capability, str(ctx.exception))

    def test_empty_permissions_is_fine(self) -> None:
        # A plugin that declares no capabilities is valid - it just can't
        # use any of the gated helpers.
        check_declared(_manifest())


class DeclaredCapabilitiesTests(unittest.TestCase):
    def test_returns_all_when_nothing_disabled(self) -> None:
        manifest = _manifest(SHELL_EXECUTE, STORAGE_READ_WRITE)
        self.assertEqual(
            list(declared_capabilities(manifest)),
            [SHELL_EXECUTE, STORAGE_READ_WRITE],
        )

    def test_strips_globally_disabled(self) -> None:
        manifest = _manifest(SHELL_EXECUTE, STORAGE_READ_WRITE)
        with patch.dict(os.environ, {"CYBEROPS_DISABLED_CAPABILITIES": "shell:execute"}):
            self.assertEqual(
                list(declared_capabilities(manifest)),
                [STORAGE_READ_WRITE],
            )


# ---------------------------------------------------------------------------
# Integration: adapter constructors enforce capabilities
# ---------------------------------------------------------------------------


class LocalCLIAdapterGateTests(unittest.TestCase):
    def test_refuses_without_shell_execute(self) -> None:
        with self.assertRaises(PermissionDenied):
            LocalCLIAdapter(_manifest(STORAGE_READ_WRITE))

    def test_constructs_when_declared(self) -> None:
        adapter = LocalCLIAdapter(_manifest(SHELL_EXECUTE))
        self.assertIs(adapter._manifest.id, "test_plugin")


class RemoteAgentAdapterGateTests(unittest.TestCase):
    def test_refuses_without_network_outbound(self) -> None:
        with self.assertRaises(PermissionDenied):
            RemoteAgentAdapter(_manifest(SHELL_EXECUTE), agent_url="http://agent")

    def test_constructs_when_declared(self) -> None:
        adapter = RemoteAgentAdapter(
            _manifest(NETWORK_OUTBOUND), agent_url="http://agent"
        )
        self.assertEqual(adapter.agent_url, "http://agent")


class PluginDataStoreGateTests(unittest.TestCase):
    def test_refuses_without_storage_read_write(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(PermissionDenied):
                PluginDataStore(_manifest(SHELL_EXECUTE), Path(tmp))

    def test_constructs_when_declared(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = PluginDataStore(_manifest(STORAGE_READ_WRITE), Path(tmp))
            self.assertEqual(store.plugin_id, "test_plugin")


if __name__ == "__main__":
    unittest.main()

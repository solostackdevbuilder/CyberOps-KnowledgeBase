"""
Tests for plugin signature verification.

Covers:
- compute_source_hashes walks directory correctly (ignores pycache/pyc/manifest)
- canonical_manifest_bytes is deterministic and drops the signature field
- sign_plugin round-trip: signed manifest verifies against the corresponding
  public key
- Tampering detection: modified source file fails, modified manifest fails
- Wrong trusted key fails
- Policy enforcement: off / warn / strict behave correctly
- Env parsing: trusted-keys list tolerates bad entries; policy defaults to off
- Registry refuses a tampered plugin under strict policy
"""
import base64
import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from app.core.plugins.base import PluginManifest
from app.core.plugins.signing import (
    ALGORITHM_ED25519,
    ENV_POLICY,
    ENV_TRUSTED_KEYS,
    POLICY_OFF,
    POLICY_STRICT,
    POLICY_WARN,
    _main as signing_cli_main,
    canonical_manifest_bytes,
    compute_source_hashes,
    enforce,
    get_policy_from_env,
    load_trusted_keys_from_env,
    sign_plugin,
    verify_plugin,
)


def _fresh_keypair() -> tuple[str, str]:
    """Return (private_b64, public_b64) for an Ed25519 keypair."""
    pk = Ed25519PrivateKey.generate()
    priv = base64.b64encode(pk.private_bytes_raw()).decode("ascii")
    pub = base64.b64encode(pk.public_key().public_bytes_raw()).decode("ascii")
    return priv, pub


def _make_plugin(tmp_root: Path, plugin_id: str = "sample") -> Path:
    """Build a minimal plugin directory tree for signing tests."""
    pdir = tmp_root / plugin_id
    pdir.mkdir()
    (pdir / "__init__.py").write_text("", encoding="utf-8")
    (pdir / "plugin.py").write_text(
        "class SamplePlugin: pass\n", encoding="utf-8"
    )
    (pdir / "manifest.json").write_text(
        json.dumps({
            "id": plugin_id,
            "name": "Sample",
            "version": "1.0.0",
            "plugin_type": "tool",
            "permissions": ["storage:read_write"],
        }),
        encoding="utf-8",
    )
    return pdir


# ---------------------------------------------------------------------------
# compute_source_hashes
# ---------------------------------------------------------------------------


class SourceHashTests(unittest.TestCase):
    def test_hashes_every_non_manifest_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            pdir = _make_plugin(Path(tmp))
            hashes = compute_source_hashes(pdir)
            self.assertIn("__init__.py", hashes)
            self.assertIn("plugin.py", hashes)
            self.assertNotIn("manifest.json", hashes)
            # Values look like "sha256:hex".
            for h in hashes.values():
                self.assertTrue(h.startswith("sha256:"))
                self.assertEqual(len(h), len("sha256:") + 64)

    def test_skips_pycache_and_pyc(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            pdir = _make_plugin(Path(tmp))
            (pdir / "__pycache__").mkdir()
            (pdir / "__pycache__" / "plugin.cpython-310.pyc").write_bytes(b"x")
            (pdir / "plugin.pyc").write_bytes(b"x")
            hashes = compute_source_hashes(pdir)
            self.assertNotIn("plugin.pyc", hashes)
            for key in hashes:
                self.assertNotIn("__pycache__", key)

    def test_walks_subdirectories(self) -> None:
        # Covers e.g. browser_extension/extension/*
        with tempfile.TemporaryDirectory() as tmp:
            pdir = _make_plugin(Path(tmp))
            sub = pdir / "sub"
            sub.mkdir()
            (sub / "asset.js").write_text("console.log('hi')\n", encoding="utf-8")
            hashes = compute_source_hashes(pdir)
            self.assertIn("sub/asset.js", hashes)


# ---------------------------------------------------------------------------
# canonical_manifest_bytes
# ---------------------------------------------------------------------------


class CanonicalManifestTests(unittest.TestCase):
    def test_strips_signature_field(self) -> None:
        m = {"id": "x", "signature": "SIG", "a": 1}
        out = canonical_manifest_bytes(m)
        self.assertNotIn(b"SIG", out)
        self.assertNotIn(b"signature", out)

    def test_sorted_keys_regardless_of_insertion_order(self) -> None:
        a = canonical_manifest_bytes({"b": 2, "a": 1})
        b = canonical_manifest_bytes({"a": 1, "b": 2})
        self.assertEqual(a, b)

    def test_no_whitespace(self) -> None:
        out = canonical_manifest_bytes({"a": 1, "b": [1, 2]})
        self.assertNotIn(b" ", out)


# ---------------------------------------------------------------------------
# Round-trip sign + verify
# ---------------------------------------------------------------------------


class SignVerifyRoundTripTests(unittest.TestCase):
    def test_signed_manifest_verifies_against_public_key(self) -> None:
        priv, pub = _fresh_keypair()
        with tempfile.TemporaryDirectory() as tmp:
            pdir = _make_plugin(Path(tmp))
            signed = sign_plugin(pdir, priv)

            # Persist so the registry-style verify reads what we saved.
            (pdir / "manifest.json").write_text(json.dumps(signed), encoding="utf-8")

            with patch.dict(os.environ, {
                ENV_TRUSTED_KEYS: f"ed25519:{pub}",
                ENV_POLICY: POLICY_STRICT,
            }):
                keys = load_trusted_keys_from_env()
                result = verify_plugin(pdir, signed, keys)
            self.assertTrue(result.ok, result.reason)


# ---------------------------------------------------------------------------
# Tampering detection
# ---------------------------------------------------------------------------


class TamperingTests(unittest.TestCase):
    def _signed_plugin(self) -> tuple[Path, dict, str, tempfile.TemporaryDirectory]:
        priv, pub = _fresh_keypair()
        tmp = tempfile.TemporaryDirectory()
        pdir = _make_plugin(Path(tmp.name))
        signed = sign_plugin(pdir, priv)
        (pdir / "manifest.json").write_text(json.dumps(signed), encoding="utf-8")
        return pdir, signed, pub, tmp

    def test_modified_source_file_fails_hash_check(self) -> None:
        pdir, signed, pub, tmp = self._signed_plugin()
        try:
            # Attacker replaces plugin.py with different contents.
            (pdir / "plugin.py").write_text(
                "class SamplePlugin: EVIL = True\n", encoding="utf-8"
            )
            with patch.dict(os.environ, {ENV_TRUSTED_KEYS: f"ed25519:{pub}"}):
                keys = load_trusted_keys_from_env()
                result = verify_plugin(pdir, signed, keys)
            self.assertFalse(result.ok)
            self.assertIn("tamper", result.reason.lower())
        finally:
            tmp.cleanup()

    def test_extra_file_added_fails_hash_check(self) -> None:
        """A plugin silently growing a new file must not pass verification,
        even if the existing source_hashes still match their files."""
        pdir, signed, pub, tmp = self._signed_plugin()
        try:
            (pdir / "extra.py").write_text("print('smuggled')\n", encoding="utf-8")
            with patch.dict(os.environ, {ENV_TRUSTED_KEYS: f"ed25519:{pub}"}):
                keys = load_trusted_keys_from_env()
                result = verify_plugin(pdir, signed, keys)
            self.assertFalse(result.ok)
            self.assertIn("extra files", result.reason.lower())
        finally:
            tmp.cleanup()

    def test_modified_manifest_metadata_fails_signature(self) -> None:
        pdir, signed, pub, tmp = self._signed_plugin()
        try:
            # Attacker tries to add shell:execute by hand to an existing
            # signed manifest. Signature is over the canonical form so
            # this drift blows up verify.
            tampered = dict(signed)
            tampered["permissions"] = list(signed["permissions"]) + ["shell:execute"]
            with patch.dict(os.environ, {ENV_TRUSTED_KEYS: f"ed25519:{pub}"}):
                keys = load_trusted_keys_from_env()
                result = verify_plugin(pdir, tampered, keys)
            self.assertFalse(result.ok)
            self.assertIn("does not verify", result.reason.lower())
        finally:
            tmp.cleanup()

    def test_wrong_trusted_key_fails(self) -> None:
        pdir, signed, _pub, tmp = self._signed_plugin()
        try:
            _priv2, pub2 = _fresh_keypair()  # Different key
            with patch.dict(os.environ, {ENV_TRUSTED_KEYS: f"ed25519:{pub2}"}):
                keys = load_trusted_keys_from_env()
                result = verify_plugin(pdir, signed, keys)
            self.assertFalse(result.ok)
            self.assertIn("does not verify", result.reason.lower())
        finally:
            tmp.cleanup()

    def test_missing_signature_refused(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            pdir = _make_plugin(Path(tmp))
            _priv, pub = _fresh_keypair()
            manifest = json.loads((pdir / "manifest.json").read_text())
            with patch.dict(os.environ, {ENV_TRUSTED_KEYS: f"ed25519:{pub}"}):
                keys = load_trusted_keys_from_env()
                result = verify_plugin(pdir, manifest, keys)
            self.assertFalse(result.ok)
            self.assertIn("no `signature`", result.reason)


# ---------------------------------------------------------------------------
# Policy enforcement
# ---------------------------------------------------------------------------


class PolicyEnforcementTests(unittest.TestCase):
    def _signed_plugin_ctx(self) -> tuple[Path, dict, str, tempfile.TemporaryDirectory]:
        priv, pub = _fresh_keypair()
        tmp = tempfile.TemporaryDirectory()
        pdir = _make_plugin(Path(tmp.name))
        signed_dict = sign_plugin(pdir, priv)
        (pdir / "manifest.json").write_text(json.dumps(signed_dict), encoding="utf-8")
        return pdir, signed_dict, pub, tmp

    def test_off_policy_skips_verification(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            pdir = _make_plugin(Path(tmp))
            data = json.loads((pdir / "manifest.json").read_text())
            # No trusted keys, no signature, policy=off → should still pass.
            result = enforce(pdir, data, policy=POLICY_OFF, trusted_keys=[])
            self.assertTrue(result.ok)
            self.assertIn("skipped", result.reason.lower())

    def test_warn_policy_loads_even_on_failure(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            pdir = _make_plugin(Path(tmp))  # unsigned
            data = json.loads((pdir / "manifest.json").read_text())
            result = enforce(pdir, data, policy=POLICY_WARN, trusted_keys=[])
            self.assertTrue(result.ok, "warn policy must always allow load")
            # But reason surfaces the real failure for logs.
            self.assertIn("no", result.reason.lower())

    def test_strict_policy_refuses_unsigned(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            pdir = _make_plugin(Path(tmp))
            data = json.loads((pdir / "manifest.json").read_text())
            result = enforce(pdir, data, policy=POLICY_STRICT, trusted_keys=[])
            self.assertFalse(result.ok)

    def test_strict_policy_accepts_signed(self) -> None:
        pdir, signed_dict, pub_b64, tmp = self._signed_plugin_ctx()
        try:
            with patch.dict(os.environ, {ENV_TRUSTED_KEYS: f"ed25519:{pub_b64}"}):
                trusted = load_trusted_keys_from_env()
            result = enforce(pdir, signed_dict, policy=POLICY_STRICT, trusted_keys=trusted)
            self.assertTrue(result.ok, result.reason)
        finally:
            tmp.cleanup()


# ---------------------------------------------------------------------------
# Env parsing
# ---------------------------------------------------------------------------


class EnvParsingTests(unittest.TestCase):
    def test_policy_default_is_off(self) -> None:
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop(ENV_POLICY, None)
            self.assertEqual(get_policy_from_env(), POLICY_OFF)

    def test_policy_invalid_falls_back_to_off(self) -> None:
        with patch.dict(os.environ, {ENV_POLICY: "paranoid"}):
            self.assertEqual(get_policy_from_env(), POLICY_OFF)

    def test_policy_case_insensitive(self) -> None:
        with patch.dict(os.environ, {ENV_POLICY: "Strict"}):
            self.assertEqual(get_policy_from_env(), POLICY_STRICT)

    def test_trusted_keys_parses_prefixed_and_bare(self) -> None:
        _priv1, pub1 = _fresh_keypair()
        _priv2, pub2 = _fresh_keypair()
        with patch.dict(os.environ, {ENV_TRUSTED_KEYS: f"ed25519:{pub1},{pub2}"}):
            keys = load_trusted_keys_from_env()
        self.assertEqual(len(keys), 2)

    def test_trusted_keys_skips_malformed_entries(self) -> None:
        _priv, pub = _fresh_keypair()
        with patch.dict(os.environ, {ENV_TRUSTED_KEYS: f"ed25519:{pub},garbage,not-base64!!"}):
            keys = load_trusted_keys_from_env()
        # One good key survives; the malformed ones are dropped with a warning.
        self.assertEqual(len(keys), 1)

    def test_trusted_keys_empty_returns_empty_list(self) -> None:
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop(ENV_TRUSTED_KEYS, None)
            self.assertEqual(load_trusted_keys_from_env(), [])


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


class CliTests(unittest.TestCase):
    def test_generate_key_prints_valid_keypair(self) -> None:
        import io
        from contextlib import redirect_stdout

        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = signing_cli_main(["generate-key"])
        self.assertEqual(rc, 0)
        out = buf.getvalue()
        # Should contain both an ed25519: public key line and a raw private.
        self.assertIn("ed25519:", out)
        # Extract and use them to verify the round trip works.
        lines = [ln for ln in out.splitlines() if ln and not ln.startswith("#")]
        public_line = next(ln for ln in lines if ln.startswith("ed25519:"))
        private_line = next(ln for ln in lines if not ln.startswith("ed25519:"))
        # Sign + verify with the emitted keys.
        with tempfile.TemporaryDirectory() as tmp:
            pdir = _make_plugin(Path(tmp))
            signed = sign_plugin(pdir, private_line)
            (pdir / "manifest.json").write_text(json.dumps(signed), encoding="utf-8")
            pub_b64 = public_line.split(":", 1)[1]
            with patch.dict(os.environ, {ENV_TRUSTED_KEYS: f"ed25519:{pub_b64}"}):
                keys = load_trusted_keys_from_env()
            result = verify_plugin(pdir, signed, keys)
            self.assertTrue(result.ok)

    def test_sign_command_writes_signed_manifest(self) -> None:
        priv, _pub = _fresh_keypair()
        with tempfile.TemporaryDirectory() as tmp:
            pdir = _make_plugin(Path(tmp))
            rc = signing_cli_main([
                "sign",
                str(pdir),
                "--private-key",
                priv,
            ])
            self.assertEqual(rc, 0)
            manifest = json.loads((pdir / "manifest.json").read_text())
            self.assertIn("signature", manifest)
            self.assertIn("source_hashes", manifest)
            self.assertEqual(manifest["signature_algorithm"], ALGORITHM_ED25519)

    def test_sign_without_key_returns_error(self) -> None:
        import io
        from contextlib import redirect_stderr

        with tempfile.TemporaryDirectory() as tmp:
            pdir = _make_plugin(Path(tmp))
            buf = io.StringIO()
            with redirect_stderr(buf):
                rc = signing_cli_main(["sign", str(pdir)])
            self.assertEqual(rc, 2)


# ---------------------------------------------------------------------------
# Registry integration: strict policy refuses tampered plugins
# ---------------------------------------------------------------------------


class RegistryEnforcementTests(unittest.TestCase):
    def test_registry_skips_tampered_plugin_under_strict_policy(self) -> None:
        from app.core.plugins.registry import PluginRegistry

        priv, pub = _fresh_keypair()
        tmp = tempfile.TemporaryDirectory()
        try:
            plugins_dir = Path(tmp.name) / "plugins"
            plugins_dir.mkdir()
            pdir = _make_plugin(plugins_dir, "tampered")
            signed = sign_plugin(pdir, priv)
            (pdir / "manifest.json").write_text(json.dumps(signed), encoding="utf-8")

            # Tamper after signing.
            (pdir / "plugin.py").write_text(
                "class TamperedPlugin: STOLEN = True\n", encoding="utf-8"
            )

            data_dir = Path(tmp.name) / "data"
            data_dir.mkdir()
            registry = PluginRegistry(plugins_dir, data_dir)

            with patch.dict(os.environ, {
                ENV_POLICY: POLICY_STRICT,
                ENV_TRUSTED_KEYS: f"ed25519:{pub}",
            }):
                with self.assertRaises(RuntimeError) as ctx:
                    registry._load_manifest("tampered")
            self.assertIn("signature verification", str(ctx.exception))
        finally:
            tmp.cleanup()

    def test_registry_loads_tampered_plugin_under_off_policy(self) -> None:
        """Default policy is off - an unsigned or tampered plugin still
        loads. This is the back-compat guarantee for existing deployments."""
        from app.core.plugins.registry import PluginRegistry

        tmp = tempfile.TemporaryDirectory()
        try:
            plugins_dir = Path(tmp.name) / "plugins"
            plugins_dir.mkdir()
            _make_plugin(plugins_dir, "unsigned")

            data_dir = Path(tmp.name) / "data"
            data_dir.mkdir()
            registry = PluginRegistry(plugins_dir, data_dir)

            with patch.dict(os.environ, {}, clear=False):
                os.environ.pop(ENV_POLICY, None)
                os.environ.pop(ENV_TRUSTED_KEYS, None)
                manifest = registry._load_manifest("unsigned")
            self.assertEqual(manifest.id, "unsigned")
        finally:
            tmp.cleanup()


if __name__ == "__main__":
    unittest.main()

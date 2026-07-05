"""
Plugin signature verification.

The three existing plugins (hashcat, remote_servers, browser_extension)
live as Python source under backend/app/plugins/ and run with full app
privileges. Anyone who can write to that tree can drop in a new plugin
or modify an existing one and get authenticated RCE inside the backend
process - that's the gap PluginManifest.signature was always meant to
close but never did.

This module closes it. A plugin is signed by producing an Ed25519
signature over:
  1. Its canonical manifest.json (all fields except `signature`, sorted,
     no whitespace).
  2. A SHA-256 hash of every other file in the plugin directory
     (recursively, excluding __pycache__ and .pyc). Those hashes live
     inside the manifest under `source_hashes`, so the signature over
     the canonical manifest covers them transitively.

Verification at plugin load:
  1. Read manifest. If missing signature AND policy is "strict", refuse.
  2. Recompute source_hashes from the on-disk files; compare against
     what the manifest claims. Any mismatch means a source file was
     tampered with post-signing.
  3. Verify the signature over the canonical-minus-signature manifest
     using one of the trusted public keys.

## Operator contract

Set the policy and trust keys in the environment:

    CYBEROPS_PLUGIN_SIGNATURE_POLICY=strict     # or "warn", default "off"
    CYBEROPS_PLUGIN_TRUSTED_KEYS=ed25519:BASE64PUBKEY,ed25519:...

Generate a keypair once:

    python -m app.core.plugins.signing generate-key

That prints two lines - the base64 public key (put in
CYBEROPS_PLUGIN_TRUSTED_KEYS) and the base64 private key (store offline,
like a code-signing key). Then sign a plugin directory:

    python -m app.core.plugins.signing sign backend/app/plugins/hashcat \\
        --private-key-file ~/secrets/plugin-signing.key

That rewrites hashcat/manifest.json with `source_hashes`, `signature`,
and `signature_algorithm` fields populated.

## What this is NOT

- Not a protection against the signing key being stolen. Treat the
  private key like any code-signing key: offline storage, rotation on
  suspicion of compromise.
- Not a protection against an attacker with root on the host - they can
  replace the trusted-keys env var just as easily as the plugin code.
  Defense in depth against that kind of attacker is out of scope.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import logging
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)

from app.core.plugins.base import PluginManifest

logger = logging.getLogger(__name__)


ALGORITHM_ED25519 = "ed25519"
ENV_POLICY = "CYBEROPS_PLUGIN_SIGNATURE_POLICY"
ENV_TRUSTED_KEYS = "CYBEROPS_PLUGIN_TRUSTED_KEYS"

POLICY_OFF = "off"
POLICY_WARN = "warn"
POLICY_STRICT = "strict"
_VALID_POLICIES = {POLICY_OFF, POLICY_WARN, POLICY_STRICT}

# Paths inside a plugin directory that are not part of the signed source
# tree. __pycache__ changes constantly; .pyc is derivative of .py; the
# manifest is covered separately by the signature itself.
_IGNORED_DIR_NAMES = {"__pycache__"}
_IGNORED_SUFFIXES = {".pyc", ".pyo"}
_MANIFEST_FILENAME = "manifest.json"


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------


@dataclass
class VerificationResult:
    """Outcome of verifying a plugin signature. `ok` is what callers
    branch on; `reason` is a human-readable message suitable for logs
    and UI."""

    ok: bool
    reason: str


# ---------------------------------------------------------------------------
# Source hashing
# ---------------------------------------------------------------------------


def compute_source_hashes(plugin_dir: Path) -> Dict[str, str]:
    """Walk the plugin directory and return {relative_path: sha256-hex}.

    Skips manifest.json (covered by the signature directly), __pycache__
    directories, and .pyc/.pyo files. Paths are relative to plugin_dir
    and use forward slashes for cross-platform stability of the manifest.
    """
    if not plugin_dir.is_dir():
        raise ValueError(f"Not a directory: {plugin_dir}")

    hashes: Dict[str, str] = {}
    for path in sorted(plugin_dir.rglob("*")):
        if not path.is_file():
            continue
        if path.name == _MANIFEST_FILENAME and path.parent == plugin_dir:
            continue
        if any(part in _IGNORED_DIR_NAMES for part in path.relative_to(plugin_dir).parts):
            continue
        if path.suffix in _IGNORED_SUFFIXES:
            continue
        rel = path.relative_to(plugin_dir).as_posix()
        hashes[rel] = "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()
    return hashes


# ---------------------------------------------------------------------------
# Canonical manifest for signing
# ---------------------------------------------------------------------------


def canonical_manifest_bytes(manifest_dict: Dict) -> bytes:
    """Produce the byte sequence that gets signed / verified.

    The `signature` field is stripped - we sign the manifest that CAN be
    written to disk, so the signature itself is not part of the signed
    input. `source_hashes` IS included, so hash drift in any source file
    breaks signature verification.

    Output is JSON with sorted keys, no whitespace, UTF-8. Determinism
    is critical: any disagreement between signer and verifier on the
    byte layout here makes every signature fail.
    """
    payload = {k: v for k, v in manifest_dict.items() if k != "signature"}
    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")


# ---------------------------------------------------------------------------
# Key encoding
# ---------------------------------------------------------------------------


def _encode_key_bytes(key: bytes) -> str:
    """Base64-encode a raw key for env-var / CLI transport."""
    return base64.b64encode(key).decode("ascii")


def _decode_trusted_key_entry(entry: str) -> Optional[Ed25519PublicKey]:
    """Parse one entry from CYBEROPS_PLUGIN_TRUSTED_KEYS.

    Accepts `ed25519:BASE64` or bare `BASE64`. Returns None if the entry
    is malformed - caller decides whether to hard-fail or skip.
    """
    entry = entry.strip()
    if not entry:
        return None
    if ":" in entry:
        algo, b64 = entry.split(":", 1)
        if algo.lower() != ALGORITHM_ED25519:
            logger.warning("Ignoring trusted key with unsupported algorithm: %s", algo)
            return None
    else:
        b64 = entry
    try:
        raw = base64.b64decode(b64)
        return Ed25519PublicKey.from_public_bytes(raw)
    except (ValueError, TypeError) as e:
        logger.warning("Ignoring malformed trusted key entry: %s", e)
        return None


def load_trusted_keys_from_env() -> List[Ed25519PublicKey]:
    """Return the list of trusted public keys declared in the environment."""
    raw = os.environ.get(ENV_TRUSTED_KEYS, "")
    keys: List[Ed25519PublicKey] = []
    for entry in raw.split(","):
        key = _decode_trusted_key_entry(entry)
        if key is not None:
            keys.append(key)
    return keys


# ---------------------------------------------------------------------------
# Policy
# ---------------------------------------------------------------------------


def get_policy_from_env() -> str:
    """Return the configured signature policy, defaulting to `off`.

    Default is `off` so existing deployments don't break. Operators
    opt in by setting CYBEROPS_PLUGIN_SIGNATURE_POLICY=warn (transition)
    or =strict (production).
    """
    value = (os.environ.get(ENV_POLICY, "") or POLICY_OFF).strip().lower()
    if value not in _VALID_POLICIES:
        logger.warning(
            "Invalid %s=%r; falling back to %s. Valid values: %s",
            ENV_POLICY, value, POLICY_OFF, sorted(_VALID_POLICIES),
        )
        return POLICY_OFF
    return value


# ---------------------------------------------------------------------------
# Signing
# ---------------------------------------------------------------------------


def sign_plugin(plugin_dir: Path, private_key_b64: str) -> Dict:
    """Sign a plugin directory's manifest + source tree.

    Reads manifest.json, computes source_hashes over the rest of the
    directory, signs the canonical manifest bytes with the Ed25519
    private key, and returns the updated manifest dict. The caller is
    responsible for writing it back to disk.
    """
    manifest_path = plugin_dir / _MANIFEST_FILENAME
    if not manifest_path.is_file():
        raise FileNotFoundError(f"No manifest.json in {plugin_dir}")

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["source_hashes"] = compute_source_hashes(plugin_dir)
    manifest["signature_algorithm"] = ALGORITHM_ED25519

    key_bytes = base64.b64decode(private_key_b64)
    private_key = Ed25519PrivateKey.from_private_bytes(key_bytes)

    payload = canonical_manifest_bytes(manifest)
    signature_raw = private_key.sign(payload)
    manifest["signature"] = _encode_key_bytes(signature_raw)
    return manifest


# ---------------------------------------------------------------------------
# Verification + policy enforcement
# ---------------------------------------------------------------------------


def _hashes_match(expected: Dict[str, str], actual: Dict[str, str]) -> Tuple[bool, str]:
    """Compare two source_hashes dicts. Returns (ok, reason-if-not-ok)."""
    missing = set(expected) - set(actual)
    extra = set(actual) - set(expected)
    if missing:
        return False, f"expected files missing from disk: {sorted(missing)}"
    if extra:
        return False, f"extra files on disk not covered by signature: {sorted(extra)}"
    mismatched = [p for p in expected if expected[p] != actual[p]]
    if mismatched:
        return False, f"hash mismatch on: {sorted(mismatched)}"
    return True, ""


def verify_plugin(
    plugin_dir: Path,
    manifest_dict: Dict,
    trusted_keys: List[Ed25519PublicKey],
) -> VerificationResult:
    """Verify a plugin's signature + source tree integrity.

    Pure function - does not consult the environment. Callers that want
    env-driven policy use `enforce()`.
    """
    signature_b64 = manifest_dict.get("signature")
    if not signature_b64:
        return VerificationResult(False, "manifest has no `signature` field")

    source_hashes_claimed = manifest_dict.get("source_hashes")
    if not isinstance(source_hashes_claimed, dict):
        return VerificationResult(
            False, "manifest has `signature` but no `source_hashes` to verify against"
        )

    algorithm = (manifest_dict.get("signature_algorithm") or "").lower()
    if algorithm and algorithm != ALGORITHM_ED25519:
        return VerificationResult(
            False, f"unsupported signature_algorithm: {algorithm!r}"
        )

    if not trusted_keys:
        return VerificationResult(
            False,
            f"no trusted keys configured - set {ENV_TRUSTED_KEYS} or run "
            f"with policy=off to skip verification",
        )

    # Hash check: do the on-disk files match what the manifest claims?
    actual_hashes = compute_source_hashes(plugin_dir)
    ok, reason = _hashes_match(source_hashes_claimed, actual_hashes)
    if not ok:
        return VerificationResult(False, f"source tree tampered - {reason}")

    # Signature check: does one of the trusted keys verify the canonical
    # manifest (which includes the now-matched source_hashes)?
    payload = canonical_manifest_bytes(manifest_dict)
    try:
        signature_raw = base64.b64decode(signature_b64)
    except (ValueError, TypeError) as e:
        return VerificationResult(False, f"signature field is not valid base64: {e}")

    for key in trusted_keys:
        try:
            key.verify(signature_raw, payload)
            return VerificationResult(True, "signature verified")
        except InvalidSignature:
            continue

    return VerificationResult(
        False, "signature does not verify against any configured trusted key"
    )


def enforce(
    plugin_dir: Path,
    manifest_dict: Dict,
    *,
    policy: Optional[str] = None,
    trusted_keys: Optional[List[Ed25519PublicKey]] = None,
) -> VerificationResult:
    """Apply the configured policy to a plugin's verification outcome.

    Takes the raw manifest dict (the one loaded from manifest.json, not
    a PluginManifest). This matters: the signer signed the dict form,
    and PluginManifest.model_dump() may introduce default-None fields
    that drift the canonical bytes. Always verify against what's on disk.

    Returns a VerificationResult whose `ok` field is what the registry
    branches on:
      - policy=off: ok=True always, reason reflects that check was skipped
      - policy=warn: verify, but ok=True regardless (reason surfaces the
        real outcome for logging)
      - policy=strict: ok reflects the real verification result

    `policy` and `trusted_keys` default to whatever the env says, but
    can be overridden for tests.
    """
    plugin_id = manifest_dict.get("id", plugin_dir.name)
    policy = policy or get_policy_from_env()
    if policy == POLICY_OFF:
        return VerificationResult(True, "signature check skipped (policy=off)")

    if trusted_keys is None:
        trusted_keys = load_trusted_keys_from_env()

    result = verify_plugin(plugin_dir, manifest_dict, trusted_keys)

    if policy == POLICY_WARN:
        # Log the real outcome but always return ok so the plugin still loads.
        if result.ok:
            logger.info("Plugin %r signature verified (policy=warn)", plugin_id)
        else:
            logger.warning(
                "Plugin %r signature check FAILED but policy=warn, loading "
                "anyway: %s", plugin_id, result.reason,
            )
        return VerificationResult(True, result.reason)

    # policy=strict
    if result.ok:
        logger.info("Plugin %r signature verified (policy=strict)", plugin_id)
    else:
        logger.error(
            "Plugin %r signature check failed (policy=strict): %s",
            plugin_id, result.reason,
        )
    return result


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _cli_generate_key(_args: argparse.Namespace) -> int:
    private_key = Ed25519PrivateKey.generate()
    private_bytes = private_key.private_bytes_raw()
    public_bytes = private_key.public_key().public_bytes_raw()
    print("# Public key (put in CYBEROPS_PLUGIN_TRUSTED_KEYS)")
    print(f"ed25519:{_encode_key_bytes(public_bytes)}")
    print("# Private key (KEEP THIS SECRET - it signs plugins)")
    print(_encode_key_bytes(private_bytes))
    return 0


def _cli_sign(args: argparse.Namespace) -> int:
    plugin_dir = Path(args.plugin_dir).resolve()
    if args.private_key_file:
        private_key_b64 = Path(args.private_key_file).read_text(encoding="utf-8").strip()
    elif args.private_key:
        private_key_b64 = args.private_key.strip()
    else:
        print(
            "error: provide --private-key or --private-key-file",
            file=sys.stderr,
        )
        return 2

    manifest = sign_plugin(plugin_dir, private_key_b64)
    manifest_path = plugin_dir / _MANIFEST_FILENAME
    manifest_path.write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )
    print(f"Signed {manifest_path}")
    print(f"  files covered: {len(manifest['source_hashes'])}")
    print(f"  signature: {manifest['signature'][:16]}... ({manifest['signature_algorithm']})")
    return 0


def _main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.core.plugins.signing")
    sub = parser.add_subparsers(dest="command", required=True)

    gen = sub.add_parser("generate-key", help="Generate a new Ed25519 keypair for signing plugins")
    gen.set_defaults(func=_cli_generate_key)

    sign = sub.add_parser("sign", help="Sign a plugin directory")
    sign.add_argument("plugin_dir", help="Path to the plugin directory (containing manifest.json)")
    sign.add_argument("--private-key", help="Base64-encoded Ed25519 private key")
    sign.add_argument("--private-key-file", help="File containing the base64-encoded private key")
    sign.set_defaults(func=_cli_sign)

    args = parser.parse_args(argv)
    return int(args.func(args) or 0)


if __name__ == "__main__":
    raise SystemExit(_main())

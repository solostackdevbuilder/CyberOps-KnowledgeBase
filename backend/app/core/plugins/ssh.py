"""
Shared SSH helper used by plugins that exec commands on remote servers.

Originally lived inside the remote_servers plugin. Hashcat needed to
reuse it for cracking-rig execution, creating a cross-plugin import
(`from app.plugins.remote_servers.plugin import _run_ssh_command`) that
was the biggest modularity smell in the codebase. This module is the
shared infrastructure; plugins that want to SSH out import from here.

The function takes an opaque `host_key_store` argument - any object
with `get_pinned_key(server_id)` and `pin(server_id, host, public_key)`
async methods. The remote_servers plugin supplies
plugins.remote_servers.host_key_store.HostKeyStore. Other plugins can
supply their own backing store without depending on the remote_servers
plugin at all.

Capability enforcement: _run_ssh_command calls
`require(manifest, NETWORK_OUTBOUND)` at the top, so a plugin that
didn't declare `network:outbound` can't SSH even by accident.
"""
from __future__ import annotations

import asyncio
import logging
import os
import tempfile
from typing import TYPE_CHECKING, Optional

from app.core.plugins.base import PluginManifest, ToolResult
from app.core.plugins.capabilities import NETWORK_OUTBOUND, require

if TYPE_CHECKING:
    # Plugin-supplied storage - type-only to avoid a runtime dependency
    # on any specific plugin's data layer.
    from app.plugins.remote_servers.host_key_store import HostKeyStore

logger = logging.getLogger(__name__)


class HostKeyMismatch(Exception):
    """Raised when a server presents a host key that does not match the
    previously-pinned key for its server_id.

    Carries enough context to render a clear UI error: operator can
    either re-pin (if they know the rotation was legitimate) or refuse
    to connect (if they suspect interception).
    """

    def __init__(self, server_id: str, host: str, expected: str, actual: str):
        self.server_id = server_id
        self.host = host
        self.expected = expected
        self.actual = actual
        super().__init__(
            f"SSH host key mismatch for server '{server_id}' ({host}). "
            f"Expected key differs from what the server presented. Either "
            f"the server's key was legitimately rotated (call POST "
            f"/api/plugins/remote_servers/servers/{server_id}/rekey to "
            f"clear the pin and TOFU-capture the new key) OR you are "
            f"being MITM'd. Do not proceed until you have verified "
            f"out-of-band."
        )


def _ssh_user_known_hosts_null() -> str:
    """OpenSSH null device for UserKnownHostsFile: Windows uses NUL, Unix /dev/null."""
    return "NUL" if os.name == "nt" else "/dev/null"


def _format_ssh_exception(exc: BaseException) -> str:
    """Avoid empty UI messages when str(exc) is blank."""
    text = str(exc).strip()
    if text:
        return text
    return f"{type(exc).__name__}: {exc!r}"


async def _run_ssh_command(
    manifest: PluginManifest,
    host: str, port: int, username: str,
    password: Optional[str], private_key: Optional[str],
    passphrase: Optional[str],
    command: str, timeout: int = 30,
    host_key_store: Optional["HostKeyStore"] = None,
    server_id: Optional[str] = None,
) -> ToolResult:
    """Run a command on a remote server via SSH.

    Tries asyncssh first, falls back to subprocess ssh.

    Requires the calling plugin's manifest to declare NETWORK_OUTBOUND.
    The manifest is first so it reads like a method receiver for the
    enforcement model even though this is a module-level function.

    When both `host_key_store` and `server_id` are provided, asyncssh
    connections enforce TOFU host-key pinning: first successful connect
    captures the server's key, subsequent connects require a match. A
    mismatch returns a ToolResult with status="failed" and an error
    message pointing the operator at the rekey endpoint. The subprocess
    fallback cannot pin per-server cleanly; if asyncssh is unavailable
    AND pinning was requested, a warning is logged and the connection
    proceeds without pinning (which only happens with a broken install,
    since asyncssh is in requirements.txt).
    """
    require(manifest, NETWORK_OUTBOUND)
    if private_key:
        private_key = private_key.replace("\r\n", "\n").replace("\r", "\n")

    pinning_enabled = host_key_store is not None and server_id is not None

    # Try asyncssh
    try:
        import asyncssh

        connect_kwargs = {
            "host": host,
            "port": port,
            "username": username,
        }

        pinned_key: Optional[str] = None
        if pinning_enabled:
            pinned_key = await host_key_store.get_pinned_key(server_id)
            if pinned_key:
                # Strict match: asyncssh raises HostKeyNotVerifiable on drift.
                connect_kwargs["known_hosts"] = asyncssh.import_known_hosts(
                    f"{host} {pinned_key}"
                )
            else:
                # TOFU: accept any key this time, capture it after connect.
                connect_kwargs["known_hosts"] = None
        else:
            # Pinning not requested (e.g., health checks from a script).
            connect_kwargs["known_hosts"] = None

        if private_key:
            connect_kwargs["client_keys"] = [asyncssh.import_private_key(private_key, passphrase)]
        elif password:
            connect_kwargs["password"] = password

        try:
            async with asyncssh.connect(**connect_kwargs) as conn:
                # Capture + pin the server's key on first successful TOFU connect.
                if pinning_enabled and pinned_key is None:
                    try:
                        server_key = conn.get_server_host_key()
                        key_str = server_key.export_public_key().decode("ascii").strip()
                        await host_key_store.pin(server_id, host, key_str)
                    except Exception as pin_err:  # noqa: BLE001
                        # Don't fail the command because we couldn't pin -
                        # surface a warning. Next connect will try again.
                        logger.warning(
                            "Connected to %s but failed to capture host key "
                            "for pinning: %s", server_id, pin_err,
                        )

                result = await asyncio.wait_for(conn.run(command), timeout=timeout)
                return ToolResult(
                    status="completed" if result.exit_status == 0 else "failed",
                    output=result.stdout.strip() if result.stdout else None,
                    error=result.stderr.strip() if result.stderr else None,
                    return_code=result.exit_status,
                )
        except asyncssh.HostKeyNotVerifiable as e:
            # Mismatch on a pinned server. Surface HostKeyMismatch-shaped
            # guidance so the operator knows how to recover.
            mismatch = HostKeyMismatch(
                server_id=server_id or "(unpinned)",
                host=host,
                expected=pinned_key or "(unknown)",
                actual=str(e),
            )
            logger.error(str(mismatch))
            return ToolResult(status="failed", error=str(mismatch))

    except ImportError:
        logger.debug("asyncssh not available, falling back to subprocess ssh")
        if pinning_enabled:
            logger.warning(
                "Host key pinning was requested for server '%s' but asyncssh "
                "is not installed. Falling back to unpinned subprocess ssh.",
                server_id,
            )
    except asyncio.TimeoutError:
        return ToolResult(status="timeout", error=f"Command timed out after {timeout}s")
    except Exception as e:
        # If asyncssh fails for a connection reason, return error
        error_msg = str(e)
        em = error_msg.lower()
        if any(
            s in em
            for s in (
                "connect",
                "auth",
                "refused",
                "permission",
                "denied",
                "unable",
                "invalid",
                "host key",
                "no matching",
                "algorithm",
            )
        ):
            return ToolResult(status="failed", error=f"SSH connection failed: {_format_ssh_exception(e)}")
        logger.warning(
            "asyncssh failed (%s); trying subprocess ssh fallback",
            _format_ssh_exception(e),
        )

    # Fallback: subprocess ssh (password auth won't work without sshpass)
    key_path: Optional[str] = None
    try:
        known_hosts = _ssh_user_known_hosts_null()
        args = [
            "ssh",
            "-o",
            "StrictHostKeyChecking=no",
            "-o",
            f"UserKnownHostsFile={known_hosts}",
            "-o",
            f"ConnectTimeout={min(timeout, 10)}",
            "-p",
            str(port),
        ]
        if private_key:
            # Write key to temp file - not ideal but works as fallback
            key_file = tempfile.NamedTemporaryFile(
                mode="w",
                suffix=".pem",
                delete=False,
                encoding="utf-8",
                newline="\n",
            )
            key_file.write(private_key)
            key_file.close()
            key_path = key_file.name
            args.extend(["-i", key_path])

        args.append(f"{username}@{host}")
        args.append(command)

        proc = await asyncio.create_subprocess_exec(
            *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        stderr_text = stderr.decode(errors="replace").strip() if stderr else ""
        if proc.returncode != 0 and not stderr_text:
            stderr_text = f"ssh exited with code {proc.returncode} (no stderr)"
        return ToolResult(
            status="completed" if proc.returncode == 0 else "failed",
            output=stdout.decode(errors="replace").strip() if stdout else None,
            error=stderr_text or None,
            return_code=proc.returncode,
        )
    except asyncio.TimeoutError:
        return ToolResult(status="timeout", error=f"SSH command timed out after {timeout}s")
    except FileNotFoundError:
        return ToolResult(status="failed", error="SSH client not found. Install asyncssh (pip install asyncssh) or ensure ssh is in PATH.")
    except Exception as e:
        return ToolResult(status="failed", error=f"SSH execution failed: {_format_ssh_exception(e)}")
    finally:
        if key_path:
            try:
                os.unlink(key_path)
            except OSError:
                pass

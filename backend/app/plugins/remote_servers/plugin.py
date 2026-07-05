"""
Remote Servers plugin.

Manages an inventory of SSH-accessible servers so that other plugins
(hashcat, john, nmap, etc.) can discover and offload work to remote
machines that have the required tools installed.

Provides:
- POST   /api/plugins/remote_servers/servers          - Add a server
- GET    /api/plugins/remote_servers/servers           - List all servers
- GET    /api/plugins/remote_servers/servers/{id}      - Get server details
- PUT    /api/plugins/remote_servers/servers/{id}      - Update a server
- DELETE /api/plugins/remote_servers/servers/{id}      - Remove a server
- POST   /api/plugins/remote_servers/servers/{id}/test - Test SSH connection
- POST   /api/plugins/remote_servers/servers/{id}/scan - Scan for installed tools
- GET    /api/plugins/remote_servers/discover/{tool}   - Find servers with a tool
"""
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional
from uuid import uuid4

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.core.plugins.base import PluginBase, PluginManifest, ToolResult
from app.core.plugins.data_store import PluginDataStore
from app.core.plugins.ssh import _run_ssh_command
from app.plugins.remote_servers.credential_store import EncryptedCredentialStore
from app.plugins.remote_servers.host_key_store import HostKeyStore

logger = logging.getLogger(__name__)


# ============================================================================
# Request/Response models
# ============================================================================

class ServerCredentials(BaseModel):
    """SSH credentials for a remote server."""
    host: str = Field(..., description="IP address or hostname")
    port: int = Field(default=22, description="SSH port")
    username: str = Field(..., description="SSH username")
    auth_method: str = Field(default="password", description="Auth method: password or key")
    password: Optional[str] = Field(None, description="SSH password (if auth_method=password)")
    private_key: Optional[str] = Field(None, description="SSH private key contents (if auth_method=key)")
    passphrase: Optional[str] = Field(None, description="Private key passphrase (optional)")


class AddServerRequest(BaseModel):
    """Request to add a remote server."""
    name: str = Field(..., description="Friendly name for this server (e.g., 'Cracking Rig 1')")
    credentials: ServerCredentials
    tags: List[str] = Field(default_factory=list, description="Tags for organization (e.g., ['gpu', 'cracking'])")
    notes: Optional[str] = Field(None, description="Optional notes about this server")


class UpdateServerRequest(BaseModel):
    """Request to update a remote server."""
    name: Optional[str] = None
    credentials: Optional[ServerCredentials] = None
    tags: Optional[List[str]] = None
    notes: Optional[str] = None


class ServerInfo(BaseModel):
    """Server info returned to the frontend."""
    id: str
    name: str
    host: str
    port: int
    username: str
    auth_method: str
    tags: List[str] = []
    notes: Optional[str] = None
    status: str = "unknown"  # unknown, online, offline, error
    last_seen: Optional[str] = None
    installed_tools: List[str] = []
    system_info: Optional[Dict] = None
    added_at: str = ""


class TestResult(BaseModel):
    """Result of a connection test."""
    server_id: str
    status: str  # online, offline, error
    message: str
    latency_ms: Optional[float] = None
    system_info: Optional[Dict] = None


class ToolScanResult(BaseModel):
    """Result of scanning for installed tools."""
    server_id: str
    tools_found: List[str]
    tools_missing: List[str]
    details: Dict[str, str] = {}  # tool -> version string



# SSH helper (_run_ssh_command, _ssh_user_known_hosts_null,
# _format_ssh_exception) + HostKeyMismatch moved to
# app.core.plugins.ssh in Phase 2.2. Hashcat used to reach across to
# this plugin's module to import _run_ssh_command; the new home at the
# core layer removes that cross-plugin dependency.


# ============================================================================
# RemoteServersPlugin
# ============================================================================

class RemoteServersPlugin(PluginBase):
    """Plugin for managing remote server connections."""

    def __init__(self):
        self._data_store: Optional[PluginDataStore] = None
        self._credential_store: Optional[EncryptedCredentialStore] = None
        self._host_key_store: Optional[HostKeyStore] = None
        self._connection_timeout: int = 10
        self._command_timeout: int = 30
        self._known_tools: List[str] = [
            "hashcat", "john", "nmap", "hydra", "gobuster", "nikto",
            "sqlmap", "nuclei", "masscan", "ffuf", "wfuzz",
            "crackmapexec", "responder", "impacket-secretsdump",
            "kerbrute", "bloodhound-python", "enum4linux",
        ]

    async def initialize(self, settings: dict) -> None:
        """Initialize the plugin."""
        self._connection_timeout = settings.get("connection_timeout", 10)
        self._command_timeout = settings.get("command_timeout", 30)
        self._known_tools = settings.get("known_tools", self._known_tools)

        from app.config import settings as app_config
        self._data_store = PluginDataStore(self.manifest, Path(app_config.data_dir))
        self._credential_store = EncryptedCredentialStore(self._data_store)
        self._host_key_store = HostKeyStore(self._data_store)
        logger.info(
            "Remote Servers plugin initialized (credential encryption: %s, host-key pinning: on)",
            "on" if self._credential_store.encryption_enabled else "OFF (plaintext)",
        )

    def get_host_key_store(self) -> Optional[HostKeyStore]:
        """Exposed for other plugins (hashcat) that SSH through registered
        servers and need to participate in host-key pinning for this
        server_id."""
        return self._host_key_store

    async def shutdown(self) -> None:
        """Clean up."""
        pass

    async def health_check(self) -> dict:
        """Return plugin health status."""
        server_count = len(await self._data_store.list_keys("servers")) if self._data_store else 0

        # Check if asyncssh is available
        try:
            import asyncssh
            ssh_backend = "asyncssh"
        except ImportError:
            ssh_backend = "subprocess"

        return {
            "status": "ok",
            "plugin": "remote_servers",
            "server_count": server_count,
            "ssh_backend": ssh_backend,
        }

    # ---- Internal helpers ----

    async def _get_server(self, server_id: str) -> Optional[dict]:
        """Load server data from store."""
        return await self._data_store.load("servers", server_id)

    async def _save_server(self, server_id: str, data: dict) -> None:
        """Save server data to store."""
        await self._data_store.save("servers", server_id, data)

    async def _get_credentials(self, server_id: str) -> Optional[dict]:
        """Load credentials. Goes through EncryptedCredentialStore so
        Fernet decryption (and transparent upgrade from legacy plaintext)
        happens automatically."""
        if self._credential_store is None:
            return None
        return await self._credential_store.load(server_id)

    async def _save_credentials(self, server_id: str, creds: dict) -> None:
        """Save credentials through EncryptedCredentialStore so they hit
        disk encrypted when CYBEROPS_CREDENTIALS_KEY is configured."""
        if self._credential_store is None:
            return
        await self._credential_store.save(server_id, creds)

    async def _test_connection(self, server_data: dict, creds: dict) -> TestResult:
        """Test SSH connectivity to a server."""
        server_id = server_data["id"]
        host = creds["host"]
        port = creds["port"]
        username = creds["username"]

        import time
        start = time.monotonic()

        result = await _run_ssh_command(
            self.manifest,
            host=host, port=port, username=username,
            password=creds.get("password"),
            private_key=creds.get("private_key"),
            passphrase=creds.get("passphrase"),
            command="uname -a && hostname && uptime",
            timeout=self._connection_timeout,
            host_key_store=self._host_key_store,
            server_id=server_id,
        )

        latency = round((time.monotonic() - start) * 1000, 1)

        if result.status == "completed":
            lines = (result.output or "").split("\n")
            system_info = {
                "uname": lines[0] if len(lines) > 0 else "",
                "hostname": lines[1].strip() if len(lines) > 1 else "",
                "uptime": lines[2].strip() if len(lines) > 2 else "",
            }
            # Update server status
            server_data["status"] = "online"
            server_data["last_seen"] = datetime.utcnow().isoformat()
            server_data["system_info"] = system_info
            await self._save_server(server_id, server_data)

            return TestResult(
                server_id=server_id,
                status="online",
                message=f"Connected successfully ({latency}ms)",
                latency_ms=latency,
                system_info=system_info,
            )
        else:
            server_data["status"] = "offline" if result.status == "timeout" else "error"
            await self._save_server(server_id, server_data)

            return TestResult(
                server_id=server_id,
                status=server_data["status"],
                message=result.error or "Connection failed",
                latency_ms=latency,
            )

    async def _scan_tools(self, server_data: dict, creds: dict) -> ToolScanResult:
        """Scan a server for installed tools."""
        server_id = server_data["id"]

        # Build a single command that checks all tools at once
        # Uses 'which' or 'command -v' to find each tool
        check_commands = " && ".join(
            f'echo "CHECK:{tool}:$(command -v {tool} 2>/dev/null || echo NOT_FOUND)"'
            for tool in self._known_tools
        )

        result = await _run_ssh_command(
            self.manifest,
            host=creds["host"], port=creds["port"], username=creds["username"],
            password=creds.get("password"),
            private_key=creds.get("private_key"),
            passphrase=creds.get("passphrase"),
            command=check_commands,
            timeout=self._command_timeout,
            host_key_store=self._host_key_store,
            server_id=server_id,
        )

        found = []
        missing = []
        details = {}

        if result.status == "completed" and result.output:
            for line in result.output.split("\n"):
                line = line.strip()
                if line.startswith("CHECK:"):
                    parts = line.split(":", 2)
                    if len(parts) == 3:
                        tool = parts[1]
                        path = parts[2]
                        if path != "NOT_FOUND":
                            found.append(tool)
                            details[tool] = path
                        else:
                            missing.append(tool)
        else:
            # If SSH failed, all tools are unknown
            missing = list(self._known_tools)

        # Try to get versions for found tools
        if found:
            version_commands = " && ".join(
                f'echo "VER:{tool}:$({tool} --version 2>&1 | head -1 || echo unknown)"'
                for tool in found
            )
            ver_result = await _run_ssh_command(
                self.manifest,
                host=creds["host"], port=creds["port"], username=creds["username"],
                password=creds.get("password"),
                private_key=creds.get("private_key"),
                passphrase=creds.get("passphrase"),
                command=version_commands,
                timeout=self._command_timeout,
                host_key_store=self._host_key_store,
                server_id=server_id,
            )
            if ver_result.status == "completed" and ver_result.output:
                for line in ver_result.output.split("\n"):
                    line = line.strip()
                    if line.startswith("VER:"):
                        parts = line.split(":", 2)
                        if len(parts) == 3:
                            details[parts[1]] = f"{details.get(parts[1], '')} ({parts[2].strip()})"

        # Update server record
        server_data["installed_tools"] = found
        server_data["last_seen"] = datetime.utcnow().isoformat()
        server_data["status"] = "online"
        await self._save_server(server_id, server_data)

        return ToolScanResult(
            server_id=server_id,
            tools_found=found,
            tools_missing=missing,
            details=details,
        )

    # ---- Public API for other plugins ----

    async def find_servers_with_tool(self, tool_name: str) -> List[dict]:
        """Find all servers that have a specific tool installed.

        This is the primary API for other plugins to use:
            registry = request.app.state.plugin_registry
            remote_servers = registry.get("remote_servers")
            servers = await remote_servers.find_servers_with_tool("hashcat")
        """
        if not self._data_store:
            return []

        servers = []
        keys = await self._data_store.list_keys("servers")
        for key in keys:
            server = await self._data_store.load("servers", key)
            if server and tool_name in server.get("installed_tools", []):
                # Return server info + credentials for connecting. Route
                # through the credential store so encryption / legacy
                # plaintext migration runs transparently.
                creds = await self._get_credentials(key)
                servers.append({
                    "id": server["id"],
                    "name": server["name"],
                    "host": creds["host"] if creds else server.get("host", ""),
                    "port": creds.get("port", 22) if creds else 22,
                    "username": creds["username"] if creds else "",
                    "status": server.get("status", "unknown"),
                    "last_seen": server.get("last_seen"),
                })
        return servers

    async def get_server_credentials(self, server_id: str) -> Optional[dict]:
        """Get full credentials for a server. Used by other plugins to connect.

        Returns dict with host, port, username, password/private_key.
        """
        return await self._get_credentials(server_id)

    # ---- Routes ----

    def get_routes(self) -> APIRouter:
        """Create API routes for the remote servers plugin."""
        router = APIRouter(prefix="/api/plugins/remote_servers", tags=["remote_servers"])
        plugin = self

        @router.get("/health")
        async def plugin_health():
            """Check plugin health."""
            return await plugin.health_check()

        @router.post("/servers", response_model=ServerInfo)
        async def add_server(request: AddServerRequest):
            """Add a new remote server."""
            server_id = str(uuid4())[:8]  # Short IDs for readability

            # Store server metadata (no secrets)
            server_data = {
                "id": server_id,
                "name": request.name,
                "host": request.credentials.host,
                "port": request.credentials.port,
                "username": request.credentials.username,
                "auth_method": request.credentials.auth_method,
                "tags": request.tags,
                "notes": request.notes,
                "status": "unknown",
                "last_seen": None,
                "installed_tools": [],
                "system_info": None,
                "added_at": datetime.utcnow().isoformat(),
            }
            await plugin._save_server(server_id, server_data)

            # Store credentials separately
            creds = request.credentials.model_dump()
            await plugin._save_credentials(server_id, creds)

            logger.info(f"Added remote server: {request.name} ({request.credentials.host})")
            return ServerInfo(**server_data)

        @router.get("/servers", response_model=List[ServerInfo])
        async def list_servers():
            """List all registered servers."""
            keys = await plugin._data_store.list_keys("servers")
            servers = []
            for key in keys:
                data = await plugin._data_store.load("servers", key)
                if data:
                    servers.append(ServerInfo(**data))
            return servers

        @router.get("/servers/{server_id}", response_model=ServerInfo)
        async def get_server(server_id: str):
            """Get a server by ID."""
            data = await plugin._get_server(server_id)
            if not data:
                raise HTTPException(status_code=404, detail="Server not found")
            return ServerInfo(**data)

        @router.put("/servers/{server_id}", response_model=ServerInfo)
        async def update_server(server_id: str, request: UpdateServerRequest):
            """Update a server."""
            data = await plugin._get_server(server_id)
            if not data:
                raise HTTPException(status_code=404, detail="Server not found")

            if request.name is not None:
                data["name"] = request.name
            if request.tags is not None:
                data["tags"] = request.tags
            if request.notes is not None:
                data["notes"] = request.notes

            if request.credentials is not None:
                data["host"] = request.credentials.host
                data["port"] = request.credentials.port
                data["username"] = request.credentials.username
                data["auth_method"] = request.credentials.auth_method
                # Merge so omitted password/private_key does not wipe stored secrets
                existing_creds = await plugin._get_credentials(server_id) or {}
                new_creds = request.credentials.model_dump()
                merged = {**existing_creds, **new_creds}
                if not (new_creds.get("private_key") or "").strip():
                    merged["private_key"] = existing_creds.get("private_key")
                if not (new_creds.get("password") or "").strip():
                    merged["password"] = existing_creds.get("password")
                if not (new_creds.get("passphrase") or "").strip():
                    merged["passphrase"] = existing_creds.get("passphrase")
                await plugin._save_credentials(server_id, merged)

            await plugin._save_server(server_id, data)
            return ServerInfo(**data)

        @router.delete("/servers/{server_id}")
        async def delete_server(server_id: str):
            """Remove a server."""
            data = await plugin._get_server(server_id)
            if not data:
                raise HTTPException(status_code=404, detail="Server not found")

            await plugin._data_store.delete("servers", server_id)
            if plugin._credential_store is not None:
                await plugin._credential_store.delete(server_id)
            # Clear any pinned host key too - the server_id is being retired.
            if plugin._host_key_store is not None:
                await plugin._host_key_store.clear(server_id)
            logger.info(f"Removed remote server: {data.get('name')} ({server_id})")
            return {"status": "deleted", "server_id": server_id}

        @router.post("/servers/{server_id}/rekey")
        async def rekey_server(server_id: str):
            """Clear the pinned SSH host key for this server.

            Use this when the server's key was legitimately rotated (OS
            reinstall, manual regeneration, etc.). The next successful
            connection will TOFU-capture the new key. If you're seeing a
            mismatch error but did NOT rotate the key, do NOT rekey - you
            may be mid-MITM.
            """
            data = await plugin._get_server(server_id)
            if not data:
                raise HTTPException(status_code=404, detail="Server not found")
            if plugin._host_key_store is None:
                raise HTTPException(status_code=503, detail="Host key store unavailable")
            cleared = await plugin._host_key_store.clear(server_id)
            return {
                "status": "rekeyed" if cleared else "no_pin_present",
                "server_id": server_id,
            }

        @router.post("/servers/{server_id}/test", response_model=TestResult)
        async def test_connection(server_id: str):
            """Test SSH connection to a server."""
            data = await plugin._get_server(server_id)
            if not data:
                raise HTTPException(status_code=404, detail="Server not found")

            creds = await plugin._get_credentials(server_id)
            if not creds:
                raise HTTPException(status_code=400, detail="No credentials found for this server")

            return await plugin._test_connection(data, creds)

        @router.post("/servers/{server_id}/scan", response_model=ToolScanResult)
        async def scan_tools(server_id: str):
            """Scan a server for installed security tools."""
            data = await plugin._get_server(server_id)
            if not data:
                raise HTTPException(status_code=404, detail="Server not found")

            creds = await plugin._get_credentials(server_id)
            if not creds:
                raise HTTPException(status_code=400, detail="No credentials found for this server")

            # Test connection first
            test = await plugin._test_connection(data, creds)
            if test.status != "online":
                raise HTTPException(
                    status_code=503,
                    detail=f"Server is not reachable: {test.message}"
                )

            return await plugin._scan_tools(data, creds)

        @router.get("/discover/{tool_name}")
        async def discover_tool(tool_name: str):
            """Find all servers that have a specific tool installed.

            This is the endpoint other plugins use to find remote execution targets.
            """
            servers = await plugin.find_servers_with_tool(tool_name)
            return {
                "tool": tool_name,
                "servers": servers,
                "count": len(servers),
            }

        @router.post("/servers/{server_id}/exec")
        async def execute_command(server_id: str, command: str):
            """Execute a command on a remote server.

            Used by other plugins to run tool commands remotely.
            """
            data = await plugin._get_server(server_id)
            if not data:
                raise HTTPException(status_code=404, detail="Server not found")

            creds = await plugin._get_credentials(server_id)
            if not creds:
                raise HTTPException(status_code=400, detail="No credentials found")

            result = await _run_ssh_command(
                plugin.manifest,
                host=creds["host"], port=creds["port"], username=creds["username"],
                password=creds.get("password"),
                private_key=creds.get("private_key"),
                passphrase=creds.get("passphrase"),
                command=command,
                timeout=plugin._command_timeout,
                host_key_store=plugin._host_key_store,
                server_id=server_id,
            )
            return result

        return router

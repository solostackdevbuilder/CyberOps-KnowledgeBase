"""
Hashcat password cracking plugin.

Supports two execution modes:
- Local: runs hashcat as a subprocess on this machine
- Remote: submits jobs to a remote HTTP agent on a cracking rig

The plugin provides:
- POST /api/plugins/hashcat/crack - Submit a hash to crack
- GET  /api/plugins/hashcat/jobs/{job_id} - Check job status
- GET  /api/plugins/hashcat/hash-types - List supported hash types
- GET  /api/plugins/hashcat/input-schema - Get input form schema
"""
import logging
import re
import shlex
from datetime import datetime
from pathlib import Path
from typing import Optional
from uuid import uuid4

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, field_validator

from app.core.plugins.base import JobStatus, ToolPlugin, ToolResult
from app.core.plugins.data_store import PluginDataStore
from app.core.plugins.execution import LocalCLIAdapter, RemoteAgentAdapter

# ---------------------------------------------------------------------------
# Open hardening items (documented here so the review surface is not lost):
# - SSH host-key pinning: _run_ssh_command still sets known_hosts=None.
#   Move to trust-on-first-use with per-server pinning.
# - Credential-at-rest encryption: remote_servers credentials are plaintext
#   JSON under backend/data/plugins/remote_servers/credentials/. Wrap with
#   `keyring` or a user-supplied passphrase before shipping to untrusted
#   environments.
# - Plugin signature verification: PluginManifest.signature exists but
#   PluginRegistry.load() never checks it. Until it does, the plugin tree
#   is an authenticated RCE surface for anyone with write access to
#   backend/app/plugins/.
# ---------------------------------------------------------------------------

# A wordlist/rules argument must be either a safe basename or an absolute path
# containing only safe path characters. No shell metacharacters, no traversal.
_WORDLIST_RE = re.compile(r"^(?:[A-Za-z0-9_.\-]+|/[A-Za-z0-9_./\-]+)$")
# Hashcat masks accept placeholders (?a, ?d, ?l, ?u, ?s, ?b, ?1..?4) and
# literal alphanumerics plus a handful of safe punctuation. Spaces and shell
# metacharacters are rejected.
_MASK_RE = re.compile(r"^[A-Za-z0-9?._\-]+$")

logger = logging.getLogger(__name__)


# ============================================================================
# Hash type mapping
# ============================================================================

HASH_TYPES = {
    "md5": {"code": "0", "name": "MD5", "example": "8743b52063cd84097a65d1633f5c74f5"},
    "sha1": {"code": "100", "name": "SHA1", "example": "b89eaac7e61417341b710b727768294d0e6a277b"},
    "sha256": {"code": "1400", "name": "SHA-256", "example": "127e6fbfe24a750e72930c220a8e138275656b8e5d8f48a98c3c92df2caba935"},
    "sha512": {"code": "1700", "name": "SHA-512", "example": ""},
    "ntlm": {"code": "1000", "name": "NTLM", "example": "b4b9b02e6f09a9bd760f388b67351e2b"},
    "bcrypt": {"code": "3200", "name": "bcrypt", "example": "$2a$05$LhayLxezLhK1LhWvKxCyLOj0j1u.Kj0jZ0pEmm134uzrQlFvQJLF6"},
    "sha512crypt": {"code": "1800", "name": "sha512crypt (Unix)", "example": "$6$rounds=5000$salt$hash"},
    "md5crypt": {"code": "500", "name": "md5crypt (Unix)", "example": "$1$salt$hash"},
    "mysql": {"code": "300", "name": "MySQL4.1/5", "example": ""},
    "mssql": {"code": "1731", "name": "MSSQL (2012+)", "example": ""},
    "kerberos_tgs": {"code": "13100", "name": "Kerberoasting TGS-REP", "example": ""},
    "kerberos_asrep": {"code": "18200", "name": "AS-REP Roasting", "example": ""},
    "netntlmv2": {"code": "5600", "name": "NetNTLMv2", "example": ""},
    "wpa": {"code": "22000", "name": "WPA-PBKDF2-PMKID+EAPOL", "example": ""},
}

ATTACK_MODES = {
    "dictionary": {"code": "0", "name": "Dictionary (wordlist)", "description": "Try every word in a wordlist"},
    "combinator": {"code": "1", "name": "Combinator", "description": "Combine words from two wordlists"},
    "brute_force": {"code": "3", "name": "Brute Force (mask)", "description": "Try all combinations matching a pattern"},
    "rule_based": {"code": "0", "name": "Rule-based", "description": "Dictionary attack with mutation rules"},
}


# ============================================================================
# Request/Response models
# ============================================================================

class CrackRequest(BaseModel):
    """Request to crack a hash."""
    hash_value: str = Field(..., min_length=1, max_length=8192, description="The hash to crack")
    hash_type: str = Field(default="auto", max_length=32, description="Hash type (md5, sha1, ntlm, etc.) or 'auto' to detect")
    attack_mode: str = Field(default="dictionary", max_length=32, description="Attack mode: dictionary, brute_force, combinator, rule_based")
    wordlist: Optional[str] = Field(None, max_length=256, description="Wordlist path or basename (default: rockyou.txt)")
    mask: Optional[str] = Field(None, max_length=128, description="Mask pattern for brute force (e.g., ?a?a?a?a?a?a)")
    rules: Optional[str] = Field(None, max_length=256, description="Rules file for rule-based attacks")
    server_id: Optional[str] = Field(None, max_length=128, description="Remote server ID to run on (from Remote Servers plugin)")

    @field_validator("wordlist", "rules")
    @classmethod
    def _validate_wordlist_or_rules(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        if ".." in v:
            raise ValueError("path traversal (..) is not allowed")
        if not _WORDLIST_RE.match(v):
            raise ValueError(
                "must be a basename or absolute path using only [A-Za-z0-9_./-]"
            )
        return v

    @field_validator("mask")
    @classmethod
    def _validate_mask(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        if not _MASK_RE.match(v):
            raise ValueError(
                "mask may only contain letters, digits, ? and ._-; shell "
                "metacharacters are rejected"
            )
        return v


class CrackResponse(BaseModel):
    """Response from a crack submission."""
    job_id: str
    status: str
    hash_value: str
    hash_type: str
    attack_mode: str
    result: Optional[ToolResult] = None
    message: str


# ============================================================================
# HashcatPlugin
# ============================================================================

class HashcatPlugin(ToolPlugin):
    """Hashcat password cracking plugin."""

    def __init__(self):
        self._execution_mode: str = "local"
        self._local_adapter: Optional[LocalCLIAdapter] = None
        self._remote_adapter: Optional[RemoteAgentAdapter] = None
        self._data_store: Optional[PluginDataStore] = None
        self._default_wordlist: str = "rockyou.txt"
        self._max_runtime: int = 3600
        self._hashcat_available: bool = False

    async def initialize(self, settings: dict) -> None:
        """Initialize hashcat plugin with settings."""
        self._execution_mode = settings.get("execution_mode", "local")
        self._default_wordlist = settings.get("default_wordlist", "rockyou.txt")
        self._max_runtime = settings.get("max_runtime_seconds", 3600)

        # Set up data store
        from app.config import settings as app_config
        self._data_store = PluginDataStore(self.manifest, Path(app_config.data_dir))

        if self._execution_mode == "local":
            self._local_adapter = LocalCLIAdapter(self.manifest)
            self._hashcat_available = await self._local_adapter.check_available(
                "hashcat", "hashcat --version"
            )
            if self._hashcat_available:
                logger.info("Hashcat plugin: local hashcat binary found")
            else:
                logger.warning(
                    "Hashcat plugin: hashcat binary not found locally. "
                    "Install hashcat or switch to remote mode."
                )
        elif self._execution_mode == "remote":
            agent_url = settings.get("agent_url")
            if not agent_url:
                logger.error("Hashcat plugin: remote mode requires agent_url in settings")
                return
            self._remote_adapter = RemoteAgentAdapter(
                self.manifest,
                agent_url=agent_url,
                api_key=settings.get("agent_api_key"),
            )
            logger.info(f"Hashcat plugin: configured for remote agent at {agent_url}")

    async def shutdown(self) -> None:
        """Clean up resources."""
        if self._remote_adapter:
            await self._remote_adapter.close()

    async def execute(self, params: dict) -> ToolResult:
        """Execute a hashcat crack job."""
        hash_value = params.get("hash_value", "")
        hash_type = params.get("hash_type", "auto")
        attack_mode = params.get("attack_mode", "dictionary")
        wordlist = params.get("wordlist") or self._default_wordlist
        mask = params.get("mask")
        server_id = params.get("server_id")

        # Resolve hash type code
        if hash_type == "auto":
            hash_type_code = None
        elif hash_type in HASH_TYPES:
            hash_type_code = HASH_TYPES[hash_type]["code"]
        else:
            return ToolResult(status="failed", error=f"Unknown hash type: {hash_type}")

        # Resolve attack mode
        if attack_mode not in ATTACK_MODES:
            return ToolResult(status="failed", error=f"Unknown attack mode: {attack_mode}")
        attack_code = ATTACK_MODES[attack_mode]["code"]

        # If a remote server is specified, SSH the command there
        if server_id:
            return await self._execute_on_server(
                server_id, hash_value, hash_type_code, attack_code, wordlist, mask
            )

        if self._execution_mode == "local":
            return await self._execute_local(
                hash_value, hash_type_code, attack_code, wordlist, mask
            )
        elif self._execution_mode == "remote":
            return await self._execute_remote(params)
        else:
            return ToolResult(status="failed", error=f"Invalid execution mode: {self._execution_mode}")

    async def _execute_local(
        self, hash_value: str, hash_type_code: Optional[str],
        attack_code: str, wordlist: str, mask: Optional[str]
    ) -> ToolResult:
        """Run hashcat locally."""
        if not self._hashcat_available:
            return ToolResult(
                status="failed",
                error="Hashcat binary not available. Install hashcat or switch to remote mode."
            )

        args = []
        if hash_type_code:
            args.extend(["-m", hash_type_code])
        args.extend(["-a", attack_code])
        args.append("--force")  # Ignore warnings
        args.append("--potfile-disable")  # Don't use potfile for isolated runs
        args.append(hash_value)

        # For dictionary/rule attacks, append wordlist
        if attack_code in ("0", "1"):
            args.append(wordlist)
        # For brute force, append mask
        elif attack_code == "3" and mask:
            args.append(mask)

        return await self._local_adapter.execute(
            "hashcat", args, timeout=self._max_runtime
        )

    def _build_hashcat_command(
        self, hash_value: str, hash_type_code: Optional[str],
        attack_code: str, wordlist: str, mask: Optional[str],
    ) -> str:
        """Build the hashcat CLI command string.

        The returned string is passed to asyncssh.conn.run() which executes
        it via the remote shell, so every user-controlled field MUST be
        shell-quoted. Input fields are additionally validated by
        CrackRequest (see _WORDLIST_RE / _MASK_RE) but shlex.quote is the
        authoritative defense.
        """
        parts = ["hashcat"]
        if hash_type_code:
            parts.extend(["-m", shlex.quote(hash_type_code)])
        parts.extend(["-a", shlex.quote(attack_code)])
        parts.append("--force")
        parts.append("--potfile-disable")
        parts.append(shlex.quote(hash_value))

        if attack_code in ("0", "1"):
            if wordlist and not wordlist.startswith("/"):
                wordlist = f"/usr/share/wordlists/{wordlist}"
            parts.append(shlex.quote(wordlist))
        elif attack_code == "3" and mask:
            parts.append(shlex.quote(mask))

        return " ".join(parts)

    async def _execute_on_server(
        self, server_id: str, hash_value: str, hash_type_code: Optional[str],
        attack_code: str, wordlist: str, mask: Optional[str],
    ) -> ToolResult:
        """Run hashcat on a remote server via the Remote Servers plugin."""
        from app.core.plugins.registry import PluginRegistry

        # Get the remote_servers plugin from the registry
        # We need to import at call time to avoid circular imports
        try:
            from app.main import plugin_registry
            remote_plugin = plugin_registry.get("remote_servers")
        except Exception:
            remote_plugin = None

        if not remote_plugin:
            return ToolResult(
                status="failed",
                error="Remote Servers plugin is not loaded. Cannot execute on remote server."
            )

        # Get credentials for the server
        creds = await remote_plugin.get_server_credentials(server_id)
        if not creds:
            return ToolResult(
                status="failed",
                error=f"No credentials found for server {server_id}"
            )

        # Build the hashcat command
        cmd = self._build_hashcat_command(hash_value, hash_type_code, attack_code, wordlist, mask)
        logger.info(f"Executing hashcat on remote server {server_id}: {cmd}")

        # SSH to the server and run the command. Thread the remote_servers
        # plugin's host key store through so our SSH call participates in
        # the same TOFU pinning policy the operator set up over there - a
        # mismatch here means the same MITM story as a direct test/scan.
        host_key_store = None
        if hasattr(remote_plugin, "get_host_key_store"):
            host_key_store = remote_plugin.get_host_key_store()

        from app.core.plugins.ssh import _run_ssh_command
        result = await _run_ssh_command(
            self.manifest,
            host=creds["host"],
            port=creds.get("port", 22),
            username=creds["username"],
            password=creds.get("password"),
            private_key=creds.get("private_key"),
            passphrase=creds.get("passphrase"),
            command=cmd,
            timeout=self._max_runtime,
            host_key_store=host_key_store,
            server_id=server_id,
        )
        return result

    async def _execute_remote(self, params: dict) -> ToolResult:
        """Submit job to remote agent."""
        if not self._remote_adapter:
            return ToolResult(
                status="failed",
                error="Remote agent not configured. Set agent_url in plugin settings."
            )
        try:
            job_id = await self._remote_adapter.submit_job("hashcat", params)
            return ToolResult(status="submitted", job_id=job_id)
        except Exception as e:
            return ToolResult(status="failed", error=f"Failed to submit remote job: {e}")

    async def get_status(self, job_id: str) -> JobStatus:
        """Check status of a crack job."""
        # Check local data store first
        job_data = await self._data_store.load("jobs", job_id)
        if job_data:
            return JobStatus(
                job_id=job_id,
                status=job_data.get("status", "unknown"),
                message=job_data.get("message"),
                result=ToolResult(**job_data["result"]) if job_data.get("result") else None,
            )

        # Check remote agent
        if self._remote_adapter:
            try:
                return await self._remote_adapter.get_status(job_id)
            except Exception as e:
                return JobStatus(
                    job_id=job_id,
                    status="unknown",
                    message=f"Failed to check status: {e}",
                )

        return JobStatus(job_id=job_id, status="not_found", message="Job not found")

    def get_input_schema(self) -> dict:
        """Return JSON Schema for the crack input form."""
        return {
            "type": "object",
            "title": "Hashcat Password Cracker",
            "description": "Submit a hash for cracking",
            "properties": {
                "hash_value": {
                    "type": "string",
                    "title": "Hash",
                    "description": "The hash value to crack",
                },
                "hash_type": {
                    "type": "string",
                    "title": "Hash Type",
                    "enum": ["auto"] + list(HASH_TYPES.keys()),
                    "default": "auto",
                    "description": "Hash algorithm type",
                },
                "attack_mode": {
                    "type": "string",
                    "title": "Attack Mode",
                    "enum": list(ATTACK_MODES.keys()),
                    "default": "dictionary",
                    "description": "Attack strategy",
                },
                "wordlist": {
                    "type": "string",
                    "title": "Wordlist",
                    "default": self._default_wordlist,
                    "description": "Wordlist for dictionary attacks",
                },
                "mask": {
                    "type": "string",
                    "title": "Mask",
                    "description": "Mask pattern for brute force (e.g., ?a?a?a?a?a?a)",
                },
            },
            "required": ["hash_value"],
        }

    def get_routes(self) -> APIRouter:
        """Create API routes for the hashcat plugin."""
        router = APIRouter(prefix="/api/plugins/hashcat", tags=["hashcat"])
        plugin = self  # Capture reference for closures

        @router.post("/crack", response_model=CrackResponse)
        async def crack_hash(request: CrackRequest) -> CrackResponse:
            """Submit a hash for cracking."""
            job_id = str(uuid4())

            # Execute the crack
            result = await plugin.execute(request.model_dump())

            # Parse cracked passwords from hashcat output
            cracked_passwords = []
            effective_status = result.status
            if result.status == "completed" and result.output:
                import re
                # Hashcat outputs cracked hashes as "hash:password" - the hash
                # is always hex chars. Match lines that look like hex_hash:plaintext.
                # Split on \r and \n because hashcat uses \r for progress updates
                # which can concatenate the cracked line with status output.
                crack_pattern = re.compile(r'^([a-fA-F0-9]{16,}):(.+)$')
                for line in re.split(r'[\r\n]+', result.output):
                    line = line.strip()
                    m = crack_pattern.match(line)
                    if m:
                        cracked_passwords.append({
                            "hash": m.group(1),
                            "password": m.group(2),
                        })
                # Check if hashcat exhausted the keyspace without cracking
                if "Status...........: Exhausted" in result.output:
                    effective_status = "exhausted"
                elif cracked_passwords:
                    effective_status = "cracked"

            # Store job in data store
            job_data = {
                "job_id": job_id,
                "hash_value": request.hash_value,
                "hash_type": request.hash_type,
                "attack_mode": request.attack_mode,
                "status": effective_status,
                "cracked_passwords": cracked_passwords,
                "submitted_at": datetime.utcnow().isoformat(),
                "result": result.model_dump() if result else None,
            }
            if plugin._data_store:
                await plugin._data_store.save("jobs", job_id, job_data)

            # Determine message
            if effective_status == "cracked":
                pw_list = ", ".join(p['password'] for p in cracked_passwords)
                message = f"Password found: {pw_list}"
            elif effective_status == "exhausted":
                message = "Exhausted wordlist - no match found"
            elif result.status == "completed":
                message = "Completed (no match found)"
            elif result.status == "submitted":
                message = f"Job submitted to remote agent (job_id: {result.job_id})"
                job_id = result.job_id or job_id
            elif result.status == "timeout":
                message = "Crack timed out - try a smaller search space or remote mode"
            else:
                message = result.error or "Crack failed"

            return CrackResponse(
                job_id=job_id,
                status=effective_status,
                hash_value=request.hash_value,
                hash_type=request.hash_type,
                attack_mode=request.attack_mode,
                result=result,
                message=message,
            )

        @router.get("/jobs/{job_id}")
        async def get_job_status(job_id: str):
            """Check status of a crack job."""
            status = await plugin.get_status(job_id)
            if status.status == "not_found":
                raise HTTPException(status_code=404, detail="Job not found")
            return status

        @router.get("/hash-types")
        async def list_hash_types():
            """List all supported hash types."""
            return {
                "hash_types": {
                    k: {"name": v["name"], "code": v["code"], "example": v["example"]}
                    for k, v in HASH_TYPES.items()
                }
            }

        @router.get("/attack-modes")
        async def list_attack_modes():
            """List all supported attack modes."""
            return {
                "attack_modes": {
                    k: {"name": v["name"], "description": v["description"]}
                    for k, v in ATTACK_MODES.items()
                }
            }

        @router.get("/input-schema")
        async def get_input_schema():
            """Get the JSON Schema for the crack input form."""
            return plugin.get_input_schema()

        @router.get("/health")
        async def plugin_health():
            """Check hashcat plugin health."""
            health = await plugin.health_check()
            health["execution_mode"] = plugin._execution_mode
            health["hashcat_available"] = plugin._hashcat_available
            if plugin._remote_adapter:
                health["agent_reachable"] = await plugin._remote_adapter.health_check()
            return health

        @router.get("/jobs")
        async def list_jobs(limit: int = 20):
            """List recent crack jobs."""
            if not plugin._data_store:
                return {"jobs": []}
            keys = await plugin._data_store.list_keys("jobs")
            jobs = []
            for key in sorted(keys, reverse=True)[:limit]:
                job = await plugin._data_store.load("jobs", key)
                if job:
                    jobs.append({
                        "job_id": job.get("job_id"),
                        "hash_value": job.get("hash_value", "")[:20] + "...",
                        "hash_type": job.get("hash_type"),
                        "status": job.get("status"),
                        "cracked_passwords": job.get("cracked_passwords", []),
                        "submitted_at": job.get("submitted_at"),
                    })
            return {"jobs": jobs}

        @router.delete("/jobs")
        async def clear_jobs():
            """Clear all crack job history."""
            if not plugin._data_store:
                return {"cleared": 0}
            count = await plugin._data_store.clear_collection("jobs")
            return {"cleared": count}

        return router

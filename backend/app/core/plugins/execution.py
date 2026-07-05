"""
Execution adapters for tool plugins.
LocalCLIAdapter runs tools as subprocesses.
RemoteAgentAdapter talks to a remote HTTP agent.

Both adapters require the owning plugin's manifest on construction and
enforce capability declarations (SHELL_EXECUTE, NETWORK_OUTBOUND) against
it. See core/plugins/capabilities.py for the enforcement model and its
limits (it's an audit layer, not a sandbox).
"""
import asyncio
import logging
from typing import Optional

import httpx

from app.core.plugins.base import JobStatus, PluginManifest, ToolResult
from app.core.plugins.capabilities import (
    NETWORK_OUTBOUND,
    SHELL_EXECUTE,
    require,
)

logger = logging.getLogger(__name__)


class LocalCLIAdapter:
    """Executes tools as local subprocesses.

    Construction requires the calling plugin's manifest to declare
    SHELL_EXECUTE. A plugin that omits it from manifest.json cannot
    instantiate this adapter - the check runs here, not at each call,
    so load-time failures surface mis-declarations early.
    """

    def __init__(self, manifest: PluginManifest):
        require(manifest, SHELL_EXECUTE)
        self._manifest = manifest

    async def execute(
        self,
        binary: str,
        args: list,
        timeout: int = 300,
        cwd: Optional[str] = None,
    ) -> ToolResult:
        """Run a tool binary with arguments.

        Args:
            binary: Path or name of the executable
            args: Command-line arguments
            timeout: Timeout in seconds
            cwd: Working directory

        Returns:
            ToolResult with stdout, stderr, and return code
        """
        logger.info(f"Executing locally: {binary} {' '.join(args)}")
        try:
            proc = await asyncio.create_subprocess_exec(
                binary,
                *args,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=cwd,
            )
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(), timeout=timeout
            )
            return ToolResult(
                status="completed" if proc.returncode == 0 else "failed",
                output=stdout.decode(errors="replace") if stdout else None,
                error=stderr.decode(errors="replace") if stderr and proc.returncode != 0 else None,
                return_code=proc.returncode,
            )
        except asyncio.TimeoutError:
            logger.warning(f"Tool {binary} timed out after {timeout}s")
            try:
                proc.kill()
            except Exception:
                pass
            return ToolResult(
                status="timeout",
                error=f"Process timed out after {timeout} seconds",
            )
        except FileNotFoundError:
            return ToolResult(
                status="failed",
                error=f"Binary not found: {binary}",
            )
        except Exception as e:
            logger.error(f"Failed to execute {binary}: {e}")
            return ToolResult(
                status="failed",
                error=str(e),
            )

    async def check_available(self, binary: str, check_command: str) -> bool:
        """Verify a tool is installed and accessible.

        Args:
            binary: Not used directly - check_command is the full command
            check_command: Command to run (e.g., "hashcat --version")

        Returns:
            True if the tool is available
        """
        try:
            parts = check_command.split()
            proc = await asyncio.create_subprocess_exec(
                *parts,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await asyncio.wait_for(proc.communicate(), timeout=10)
            return proc.returncode == 0
        except (FileNotFoundError, asyncio.TimeoutError, Exception):
            return False


class RemoteAgentAdapter:
    """Executes tools on a remote HTTP agent server.

    The agent is a lightweight FastAPI app deployed on a cracking rig
    or other tool server. It accepts job submissions and returns results.

    Expected agent API:
        POST /jobs          - Submit a job, returns {job_id: str}
        GET  /jobs/{id}     - Get job status
        GET  /jobs/{id}/result - Get job result
        DELETE /jobs/{id}   - Cancel a job
        GET  /health        - Health check
    """

    def __init__(
        self,
        manifest: PluginManifest,
        agent_url: str,
        api_key: Optional[str] = None,
        timeout: float = 30.0,
    ):
        require(manifest, NETWORK_OUTBOUND)
        self._manifest = manifest
        headers = {}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        self.agent_url = agent_url.rstrip("/")
        self.client = httpx.AsyncClient(
            base_url=self.agent_url,
            headers=headers,
            timeout=timeout,
        )

    async def submit_job(self, tool_name: str, params: dict) -> str:
        """Submit a job to the remote agent.

        Returns:
            job_id string
        """
        logger.info(f"Submitting remote job: {tool_name} to {self.agent_url}")
        resp = await self.client.post("/jobs", json={
            "tool": tool_name,
            "params": params,
        })
        resp.raise_for_status()
        return resp.json()["job_id"]

    async def get_status(self, job_id: str) -> JobStatus:
        """Check status of a remote job."""
        resp = await self.client.get(f"/jobs/{job_id}")
        resp.raise_for_status()
        data = resp.json()
        return JobStatus(
            job_id=job_id,
            status=data.get("status", "unknown"),
            progress=data.get("progress"),
            message=data.get("message"),
            result=ToolResult(**data["result"]) if data.get("result") else None,
        )

    async def get_result(self, job_id: str) -> ToolResult:
        """Get the result of a completed remote job."""
        resp = await self.client.get(f"/jobs/{job_id}/result")
        resp.raise_for_status()
        return ToolResult(**resp.json())

    async def cancel_job(self, job_id: str) -> bool:
        """Cancel a running remote job."""
        try:
            resp = await self.client.delete(f"/jobs/{job_id}")
            return resp.status_code == 200
        except Exception:
            return False

    async def health_check(self) -> bool:
        """Check if the remote agent is reachable."""
        try:
            resp = await self.client.get("/health")
            return resp.status_code == 200
        except Exception:
            return False

    async def close(self) -> None:
        """Close the HTTP client."""
        await self.client.aclose()

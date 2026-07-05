"""
Browser Extension plugin.

Companion Chrome extension that captures the visible tab and attaches the PNG
to a session with URL + page title as source metadata. Reuses the existing
red_team session screenshot upload flow (and its vision-based text extraction)
but gates access behind a pairing token and accepts structured URL/title fields
rather than overloading the description.

Endpoints (all under /api/plugins/browser_extension):
- GET  /health                -> plugin status + heartbeat
- POST /token/rotate          -> generate + return a new pairing token
- GET  /sessions              -> [{id, title}] list for the extension picker
- POST /captures              -> multipart capture upload (token-gated)
- GET  /download              -> zip of the extension/ directory for install
"""
import io
import logging
import secrets
import zipfile
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter, Depends, File, Form, Header, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.core.plugins.base import PluginBase
from app.core.plugins.data_store import PluginDataStore

logger = logging.getLogger(__name__)


# ============================================================================
# Response models
# ============================================================================


class HealthResponse(BaseModel):
    status: str
    plugin: str
    token_configured: bool
    last_heartbeat: Optional[str] = None
    captures_total: int = 0


class TokenResponse(BaseModel):
    token: str


class SessionSummary(BaseModel):
    id: str
    title: str


class CaptureResponse(BaseModel):
    success: bool
    screenshot_path: str
    session_id: str
    extraction_status: Optional[str] = None
    warning: Optional[str] = None


# ============================================================================
# Plugin implementation
# ============================================================================


class BrowserExtensionPlugin(PluginBase):
    """Plugin that backs the companion Chrome extension."""

    def __init__(self):
        self._data_store: Optional[PluginDataStore] = None

    async def initialize(self, settings: dict) -> None:
        from app.config import settings as app_config
        self._data_store = PluginDataStore(self.manifest, Path(app_config.data_dir))
        logger.info("Browser Extension plugin initialized")

    async def shutdown(self) -> None:
        pass

    # ---- State helpers ----

    async def _get_token(self) -> Optional[str]:
        doc = await self._data_store.load("config", "token")
        return doc.get("value") if doc else None

    async def _set_token(self, token: str) -> None:
        await self._data_store.save("config", "token", {"value": token})

    async def _record_heartbeat(self) -> None:
        await self._data_store.save(
            "config", "heartbeat", {"at": datetime.utcnow().isoformat()}
        )

    async def _get_heartbeat(self) -> Optional[str]:
        doc = await self._data_store.load("config", "heartbeat")
        return doc.get("at") if doc else None

    async def _incr_capture_count(self) -> None:
        doc = await self._data_store.load("config", "stats") or {"captures_total": 0}
        doc["captures_total"] = int(doc.get("captures_total", 0)) + 1
        await self._data_store.save("config", "stats", doc)

    async def _get_capture_count(self) -> int:
        doc = await self._data_store.load("config", "stats")
        return int(doc.get("captures_total", 0)) if doc else 0

    async def health_check(self) -> dict:
        return {
            "status": "ok",
            "plugin": "browser_extension",
            "token_configured": bool(await self._get_token()),
            "last_heartbeat": await self._get_heartbeat(),
            "captures_total": await self._get_capture_count(),
        }

    # ---- Routes ----

    def get_routes(self) -> APIRouter:
        router = APIRouter(prefix="/api/plugins/browser_extension", tags=["browser_extension"])
        plugin = self

        async def require_token(x_plugin_token: Optional[str] = Header(None)) -> None:
            stored = await plugin._get_token()
            if not stored:
                raise HTTPException(
                    status_code=401,
                    detail="No pairing token configured. Rotate one from the plugin page first.",
                )
            if not x_plugin_token or not secrets.compare_digest(x_plugin_token, stored):
                raise HTTPException(status_code=401, detail="Invalid pairing token")
            await plugin._record_heartbeat()

        @router.get("/health", response_model=HealthResponse)
        async def plugin_health():
            state = await plugin.health_check()
            return HealthResponse(**state)

        @router.post("/token/rotate", response_model=TokenResponse)
        async def rotate_token():
            """Generate a new pairing token. The previous token is invalidated."""
            new_token = secrets.token_urlsafe(32)
            await plugin._set_token(new_token)
            logger.info("Browser extension pairing token rotated")
            return TokenResponse(token=new_token)

        @router.get("/sessions", response_model=List[SessionSummary])
        async def list_sessions_for_extension(_: None = Depends(require_token)):
            """Lightweight session list for the extension's dropdown picker."""
            from app.core.storage.storage_factory import get_storage
            from app.core.storage.settings_store import SettingsStore

            settings_store = SettingsStore()
            app_settings = await settings_store.load_settings()
            storage = get_storage(app_settings)
            sessions = await storage.list_sessions()
            return [
                SessionSummary(id=s.id, title=s.title)
                for s in sorted(sessions, key=lambda s: s.updated_at, reverse=True)
            ]

        @router.post("/captures", response_model=CaptureResponse)
        async def create_capture(
            session_id: str = Form(...),
            file: UploadFile = File(...),
            url: Optional[str] = Form(None),
            title: Optional[str] = Form(None),
            description: Optional[str] = Form(None),
            _: None = Depends(require_token),
        ):
            """Attach a captured screenshot to a session with source metadata."""
            from app.modules.red_team.routes import upload_screenshot

            response = await upload_screenshot(
                session_id=session_id,
                file=file,
                description=description,
                source_url=url,
                source_title=title,
            )
            await plugin._incr_capture_count()
            return CaptureResponse(
                success=response.success,
                screenshot_path=response.screenshot_path,
                session_id=session_id,
                extraction_status=response.extraction.get("extraction_status") if response.extraction else None,
                warning=response.warning,
            )

        @router.get("/download")
        async def download_extension():
            """Stream the extension/ directory as a zip for one-click install."""
            ext_dir = Path(__file__).parent / "extension"
            if not ext_dir.exists():
                raise HTTPException(status_code=500, detail="Extension source not found on server")

            buf = io.BytesIO()
            with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
                for path in ext_dir.rglob("*"):
                    if path.is_file():
                        zf.write(path, arcname=path.relative_to(ext_dir))
            buf.seek(0)

            return StreamingResponse(
                buf,
                media_type="application/zip",
                headers={"Content-Disposition": 'attachment; filename="cyops-capture.zip"'},
            )

        return router

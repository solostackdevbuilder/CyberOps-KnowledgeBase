"""
Screenshot routes on sessions_router.

Owns three endpoints under /api/sessions/{id}/screenshots/*:
  POST .                 - upload + vision extraction
  POST ./{file}/extract  - manual re-extraction
  GET  ./{file}          - serve the image file

`upload_screenshot` (the route handler) is ALSO imported as a function
reference by app/plugins/browser_extension/plugin.py, which uses it to
funnel Chrome-extension captures through the same storage + extraction
path as the in-app uploader. The package's __init__.py re-exports the
name from this module so the plugin's import path keeps working.

sessions_router still lives in _legacy.py until Phase 2.1h; this module
imports it from there.
"""
import json
import logging
from datetime import datetime
from typing import Optional

import aiofiles
import aiofiles.os as aios
from fastapi import File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel

from app.config import settings
from app.core.services.image_service import process_screenshot
from app.core.services.llm_factory import get_llm_service
from app.core.storage.settings_store import SettingsStore
from app.core.storage.storage_factory import get_storage
from app.integrations.event_notifier import notify_event
from app.modules.red_team.models import ScreenshotExtraction, SessionUpdate
from app.modules.red_team.routes.sessions import sessions_router
from app.utils.file_handler import save_screenshot
from app.core.exceptions import RedTeamKBError

logger = logging.getLogger(__name__)


class ScreenshotUploadResponse(BaseModel):
    """Response model for screenshot upload with extraction results."""
    success: bool
    screenshot_path: str
    extraction: dict
    warning: Optional[str] = None


@sessions_router.post("/{session_id}/screenshots", status_code=200)
async def upload_screenshot(
    session_id: str,
    file: UploadFile = File(...),
    description: str = Form(None),
    source_url: Optional[str] = Form(None),
    source_title: Optional[str] = Form(None),
) -> ScreenshotUploadResponse:
    """
    Upload a screenshot for a session and automatically extract text using vision capabilities.

    Args:
        session_id: Session ID to associate screenshot with
        file: Image file to upload
        description: Optional description of the screenshot

    Returns:
        Response with screenshot path and extraction results
    """
    # Get storage from settings
    settings_store = SettingsStore()
    app_settings = await settings_store.load_settings()
    storage = get_storage(app_settings)

    # Verify session exists
    session = await storage.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail=f"Session {session_id} not found")

    try:
        # Save screenshot
        screenshot = await save_screenshot(
            file,
            session_id,
            description,
            source_url=source_url,
            source_title=source_title,
        )

        # Get screenshot path
        screenshot_path = settings.screenshots_dir / screenshot.filename

        # Add screenshot to session
        session.screenshots.append(screenshot)
        session.updated_at = screenshot.timestamp

        # Initialize screenshot_extractions if not exists
        if not hasattr(session, 'screenshot_extractions') or session.screenshot_extractions is None:
            session.screenshot_extractions = []

        # Initialize metadata if not exists
        if not hasattr(session, 'metadata') or session.metadata is None:
            session.metadata = {}
        if "screenshot_texts" not in session.metadata:
            session.metadata["screenshot_texts"] = []

        # Process screenshot with vision extraction
        extraction_result = None
        warning = None

        try:
            # Get LLM service
            llm_service = get_llm_service(app_settings)

            # Process screenshot
            extraction_result = await process_screenshot(
                session_id=session_id,
                screenshot_path=str(screenshot_path),
                filename=screenshot.filename,
                llm_service=llm_service
            )

            # Add extraction to session
            session.screenshot_extractions.append(extraction_result)

            # If extraction successful and has text, add to metadata
            if extraction_result.extraction_status == "success" and extraction_result.extracted_text:
                if not isinstance(session.metadata["screenshot_texts"], list):
                    session.metadata["screenshot_texts"] = []
                session.metadata["screenshot_texts"].append(extraction_result.extracted_text)

            # Set warning if not supported
            if extraction_result.extraction_status == "not_supported":
                warning = "Selected LLM does not support vision"

        except Exception as e:
            # Log error but don't fail the upload
            logger.error(f"Failed to extract text from screenshot: {e}", exc_info=True)
            warning = f"Text extraction failed: {str(e)}"
            # Create a failed extraction result
            extraction_result = ScreenshotExtraction(
                filename=screenshot.filename,
                path=str(screenshot_path),
                uploaded_at=datetime.utcnow(),
                extracted_text=None,
                analysis=None,
                extraction_status="failed",
                error_message=str(e)
            )
            session.screenshot_extractions.append(extraction_result)

        # Update session in storage
        # We need to update the session metadata to include the new screenshot and extraction
        # Since SessionUpdate doesn't have screenshots field, we'll update the session directly
        # For JSON store, we need to handle this specially
        if hasattr(storage, 'file_store'):
            # JSON store - update file directly
            from app.core.storage.json_store import JSONStore
            if isinstance(storage, JSONStore):
                session_file = storage.file_store.sessions_dir / f"{session_id}.json"
                session_dict = session.model_dump(mode="json")
                # Keep terminal_content out of metadata JSON - canonical
                # copy lives in the encrypted .txt file only.
                session_dict["terminal_content"] = ""
                session_dict["created_at"] = session.created_at.isoformat()
                session_dict["updated_at"] = session.updated_at.isoformat()
                for scr in session_dict.get("screenshots", []):
                    if "timestamp" in scr:
                        scr["timestamp"] = scr["timestamp"].isoformat() if isinstance(scr["timestamp"], datetime) else scr["timestamp"]
                # Handle screenshot_extractions
                if "screenshot_extractions" in session_dict:
                    for ext in session_dict["screenshot_extractions"]:
                        if "uploaded_at" in ext:
                            if isinstance(ext["uploaded_at"], datetime):
                                ext["uploaded_at"] = ext["uploaded_at"].isoformat()
                            elif isinstance(ext["uploaded_at"], (int, float)):
                                # Handle timestamp
                                ext["uploaded_at"] = datetime.fromtimestamp(ext["uploaded_at"]).isoformat()

                async with aiofiles.open(session_file, "w", encoding="utf-8") as f:
                    await f.write(json.dumps(session_dict, indent=2, ensure_ascii=False))
            else:
                # MongoDB or other - use update_session
                # Create a dummy update to trigger save
                await storage.update_session(session_id, SessionUpdate(title=session.title))
        else:
            # MongoDB or other - update directly
            await storage.update_session(session_id, SessionUpdate(title=session.title))

        # Build extraction response
        extraction_dict = {
            "filename": extraction_result.filename if extraction_result else screenshot.filename,
            "extracted_text": extraction_result.extracted_text if extraction_result else None,
            "analysis": extraction_result.analysis if extraction_result else None,
            "extraction_status": extraction_result.extraction_status if extraction_result else "failed",
            "error_message": extraction_result.error_message if extraction_result else None
        }

        # Get operation name for notification
        operation_name = "Unknown"
        if session.operation_id:
            operation = await storage.get_operation(session.operation_id)
            if operation:
                operation_name = operation.name

        # Send webhook notification
        await notify_event("session.screenshot_uploaded", {
            "session_id": session.id,
            "session_title": session.title,
            "operation_id": session.operation_id,
            "operation_name": operation_name,
            "filename": screenshot.filename,
        })

        return ScreenshotUploadResponse(
            success=True,
            screenshot_path=f"/screenshots/{screenshot.filename}",
            extraction=extraction_dict,
            warning=warning
        )

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise RedTeamKBError("Failed to upload screenshot") from e


@sessions_router.post("/{session_id}/screenshots/{filename}/extract")
async def re_extract_screenshot(session_id: str, filename: str) -> dict:
    """
    Manually trigger re-extraction of text from a screenshot.
    Useful if extraction failed initially or user switched to a better LLM model.

    Args:
        session_id: Session ID
        filename: Screenshot filename

    Returns:
        Updated extraction result
    """
    # Get storage from settings
    settings_store = SettingsStore()
    app_settings = await settings_store.load_settings()
    storage = get_storage(app_settings)

    # Verify session exists
    session = await storage.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail=f"Session {session_id} not found")

    # Find screenshot extraction
    extraction = None
    extraction_index = -1
    if hasattr(session, 'screenshot_extractions') and session.screenshot_extractions:
        for idx, ext in enumerate(session.screenshot_extractions):
            if ext.filename == filename:
                extraction = ext
                extraction_index = idx
                break

    if not extraction:
        raise HTTPException(status_code=404, detail=f"Screenshot extraction not found for {filename}")

    # Get screenshot path
    screenshot_path = settings.screenshots_dir / filename
    if not screenshot_path.exists():
        raise HTTPException(status_code=404, detail=f"Screenshot file not found: {filename}")

    try:
        # Get LLM service
        llm_service = get_llm_service(app_settings)

        # Process screenshot again
        new_extraction = await process_screenshot(
            session_id=session_id,
            screenshot_path=str(screenshot_path),
            filename=filename,
            llm_service=llm_service
        )

        # Update extraction in session
        if extraction_index >= 0:
            session.screenshot_extractions[extraction_index] = new_extraction

        # Update metadata if extraction successful
        if not hasattr(session, 'metadata') or session.metadata is None:
            session.metadata = {}
        if "screenshot_texts" not in session.metadata:
            session.metadata["screenshot_texts"] = []

        # Remove old text if it existed
        if extraction.extracted_text and extraction.extracted_text in session.metadata["screenshot_texts"]:
            session.metadata["screenshot_texts"].remove(extraction.extracted_text)

        # Add new text if successful
        if new_extraction.extraction_status == "success" and new_extraction.extracted_text:
            if not isinstance(session.metadata["screenshot_texts"], list):
                session.metadata["screenshot_texts"] = []
            if new_extraction.extracted_text not in session.metadata["screenshot_texts"]:
                session.metadata["screenshot_texts"].append(new_extraction.extracted_text)

        # Save session
        await storage.update_session(session_id, SessionUpdate(title=session.title))

        # Return updated extraction
        return {
            "filename": new_extraction.filename,
            "extracted_text": new_extraction.extracted_text,
            "analysis": new_extraction.analysis,
            "extraction_status": new_extraction.extraction_status,
            "error_message": new_extraction.error_message
        }

    except Exception as e:
        raise RedTeamKBError("Failed to re-extract screenshot") from e


@sessions_router.get("/{session_id}/screenshots/{filename}")
async def get_screenshot(session_id: str, filename: str) -> FileResponse:
    """
    Retrieve a screenshot file.

    Args:
        session_id: Session ID
        filename: Screenshot filename

    Returns:
        File response with the image
    """
    # Get storage from settings
    settings_store = SettingsStore()
    app_settings = await settings_store.load_settings()
    storage = get_storage(app_settings)

    # Verify session exists
    session = await storage.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail=f"Session {session_id} not found")

    # Check if screenshot exists in session
    screenshot_exists = any(s.filename == filename for s in session.screenshots)
    if not screenshot_exists:
        raise HTTPException(status_code=404, detail=f"Screenshot {filename} not found")

    # Get file path (screenshots are stored as files)
    file_path = settings.screenshots_dir / filename

    # Check if file exists on disk
    if not await aios.path.exists(file_path):
        raise HTTPException(status_code=404, detail=f"Screenshot file {filename} not found on disk")

    return FileResponse(
        path=str(file_path),
        media_type="image/png",  # Default, could be improved with proper MIME type detection
        filename=filename
    )

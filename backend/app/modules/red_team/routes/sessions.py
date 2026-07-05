"""
Session CRUD routes.

Owns the 6 session-level endpoints under /api/sessions/*:
  POST /extract     - LLM-extract targets/tools/findings from terminal
  POST ""           - create
  GET  ""           - list with pagination + search
  GET  /{id}        - fetch one with full terminal content
  PUT  /{id}        - update
  DELETE /{id}      - delete

This module also owns the `sessions_router` object itself.
Screenshots (routes/screenshots.py) and FAA (routes/faa.py) import and
decorate the same router for endpoints that nest under /api/sessions/.

Session mutations (create/update/delete) call
`invalidate_insights_for_operation` (from routes/insights.py) to keep
the insights cache in step with session data.
"""
import logging
from typing import List, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from app.core.services.llm_factory import get_llm_service
from app.core.storage.settings_store import SettingsStore
from app.core.storage.storage_factory import get_storage
from app.integrations.event_notifier import notify_event
from app.modules.red_team.models import (
    Session,
    SessionCreate,
    SessionUpdate,
)
from app.core.exceptions import RedTeamKBError
from app.modules.red_team.routes.insights import invalidate_insights_for_operation

logger = logging.getLogger(__name__)


sessions_router = APIRouter(prefix="/api/sessions", tags=["sessions"])

__all__ = ["sessions_router"]


class ExtractRequest(BaseModel):
    """Request model for metadata extraction."""
    terminal_content: str


class PaginatedSessions(BaseModel):
    """Paginated sessions response."""
    items: List[Session]
    total: int
    page: int
    page_size: int
    total_pages: int


@sessions_router.post("/extract")
async def extract_metadata(request: ExtractRequest) -> dict:
    """
    Extract metadata from terminal content using configured LLM provider.

    Args:
        request: Request body with terminal_content

    Returns:
        Dictionary with extracted targets, tools, and findings
    """
    try:
        settings_store = SettingsStore()
        app_settings = await settings_store.load_settings()

        if not app_settings.llm_config:
            raise HTTPException(
                status_code=503,
                detail="LLM service not configured. Please configure LLM settings."
            )

        llm_service = get_llm_service(app_settings)
        metadata = await llm_service.extract_metadata(request.terminal_content)
        return metadata
    except HTTPException:
        raise
    except Exception as e:
        raise RedTeamKBError("Failed to extract metadata") from e


@sessions_router.post("", response_model=Session, status_code=201)
async def create_session(session_data: SessionCreate) -> Session:
    """
    Create a new session with terminal content and optional screenshots.
    Requires operation_id to link session to an operation.

    Args:
        session_data: Session creation data (must include operation_id)

    Returns:
        Created session object
    """
    try:
        # Get storage from settings
        settings_store = SettingsStore()
        app_settings = await settings_store.load_settings()
        storage = get_storage(app_settings)

        # Verify operation exists
        operation = await storage.get_operation(session_data.operation_id)
        if not operation:
            raise HTTPException(
                status_code=404,
                detail=f"Operation {session_data.operation_id} not found"
            )

        # Create session
        session = await storage.create_session(session_data)

        # Link session to operation
        await storage.add_session_to_operation(session_data.operation_id, session.id)

        # Send webhook notification
        await notify_event("session.created", {
            "id": session.id,
            "title": session.title,
            "description": session.description,
            "operation_id": session.operation_id,
            "operation_name": operation.name,
            "operator_name": session.operator_name,
        })

        # Invalidate insights cache for this operation
        # New session data means cached insights are stale
        await invalidate_insights_for_operation(session_data.operation_id)

        return session
    except HTTPException:
        raise
    except Exception as e:
        raise RedTeamKBError("Failed to create session") from e


@sessions_router.get("")
async def list_sessions(
    operation_id: Optional[str] = Query(None, description="Filter sessions by operation ID"),
    page: int = Query(1, ge=1, description="Page number (1-indexed)"),
    page_size: int = Query(50, ge=1, le=100, description="Items per page (max 100)"),
    search: Optional[str] = Query(None, description="Search in title, tags, tools, findings, terminal content, and screenshot text")
) -> PaginatedSessions:
    """
    List all sessions with pagination (metadata only, terminal content not loaded for performance).
    Can filter by operation_id and search.

    Args:
        operation_id: Optional operation ID to filter sessions
        page: Page number (1-indexed)
        page_size: Number of items per page
        search: Optional search term (searches title, tags, tools, findings, terminal, screenshots)

    Returns:
        Paginated list of session objects
    """
    try:
        # Get storage from settings
        settings_store = SettingsStore()
        app_settings = await settings_store.load_settings()
        storage = get_storage(app_settings)

        if operation_id:
            # Verify operation exists
            operation = await storage.get_operation(operation_id)
            if not operation:
                raise HTTPException(status_code=404, detail=f"Operation {operation_id} not found")

            # Load sessions for this operation
            sessions = []
            for session_id in operation.session_ids:
                session = await storage.get_session(session_id)
                if session:
                    sessions.append(session)
        else:
            # Return all sessions
            sessions = await storage.list_sessions()

        # Apply search filter if provided - searches across multiple fields
        if search:
            search_lower = search.lower()
            filtered_sessions = []
            for s in sessions:
                # Search in title
                if search_lower in s.title.lower():
                    filtered_sessions.append(s)
                    continue
                # Search in tags
                if any(search_lower in tag.lower() for tag in (s.tags or [])):
                    filtered_sessions.append(s)
                    continue
                # Search in tools
                if any(search_lower in tool.lower() for tool in (s.tools or [])):
                    filtered_sessions.append(s)
                    continue
                # Search in findings
                if any(search_lower in finding.lower() for finding in (s.findings or [])):
                    filtered_sessions.append(s)
                    continue
                # Search in terminal content
                if s.terminal_content and search_lower in s.terminal_content.lower():
                    filtered_sessions.append(s)
                    continue
                # Search in screenshot extracted text
                if s.metadata and s.metadata.get("screenshot_texts"):
                    if any(search_lower in txt.lower() for txt in s.metadata["screenshot_texts"]):
                        filtered_sessions.append(s)
                        continue
            sessions = filtered_sessions

        # Sort by created_at descending (most recent first)
        sessions.sort(key=lambda x: x.created_at, reverse=True)

        # Calculate pagination
        total = len(sessions)
        total_pages = (total + page_size - 1) // page_size if total > 0 else 1
        start_idx = (page - 1) * page_size
        end_idx = start_idx + page_size

        paginated_items = sessions[start_idx:end_idx]

        return PaginatedSessions(
            items=paginated_items,
            total=total,
            page=page,
            page_size=page_size,
            total_pages=total_pages
        )
    except HTTPException:
        raise
    except Exception as e:
        raise RedTeamKBError("Failed to list sessions") from e


@sessions_router.get("/{session_id}", response_model=Session)
async def get_session(session_id: str) -> Session:
    """
    Get a specific session by ID with full terminal content.

    Args:
        session_id: Unique session identifier

    Returns:
        Session object with full data
    """
    # Get storage from settings
    settings_store = SettingsStore()
    app_settings = await settings_store.load_settings()
    storage = get_storage(app_settings)

    session = await storage.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail=f"Session {session_id} not found")
    return session


@sessions_router.put("/{session_id}", response_model=Session)
async def update_session(session_id: str, update_data: SessionUpdate) -> Session:
    """
    Update an existing session.

    Args:
        session_id: Unique session identifier
        update_data: Fields to update

    Returns:
        Updated session object
    """
    # Get storage from settings
    settings_store = SettingsStore()
    app_settings = await settings_store.load_settings()
    storage = get_storage(app_settings)

    session = await storage.update_session(session_id, update_data)
    if not session:
        raise HTTPException(status_code=404, detail=f"Session {session_id} not found")

    # Get operation name for notification
    operation_name = "Unknown"
    if session.operation_id:
        operation = await storage.get_operation(session.operation_id)
        if operation:
            operation_name = operation.name

    # Send webhook notification
    await notify_event("session.updated", {
        "id": session.id,
        "title": session.title,
        "description": session.description,
        "operation_id": session.operation_id,
        "operation_name": operation_name,
    })

    # Invalidate insights cache for this operation
    # Updated session data means cached insights are stale
    if session.operation_id:
        await invalidate_insights_for_operation(session.operation_id)

    return session


@sessions_router.delete("/{session_id}", status_code=204)
async def delete_session(session_id: str) -> None:
    """
    Delete a session and all associated files.
    Also removes the session from its parent operation.

    Args:
        session_id: Unique session identifier
    """
    # Get storage from settings
    settings_store = SettingsStore()
    app_settings = await settings_store.load_settings()
    storage = get_storage(app_settings)

    # Get session to find its operation_id
    session = await storage.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail=f"Session {session_id} not found")

    # Store operation_id before deletion for cache invalidation
    operation_id = session.operation_id

    # Remove session from operation
    if operation_id:
        await storage.remove_session_from_operation(operation_id, session_id)

    # Delete session
    deleted = await storage.delete_session(session_id)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Session {session_id} not found")

    # Invalidate insights cache for this operation
    # Deleted session data means cached insights are stale
    if operation_id:
        await invalidate_insights_for_operation(operation_id)

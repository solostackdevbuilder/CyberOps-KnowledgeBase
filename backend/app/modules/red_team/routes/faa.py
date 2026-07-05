"""
Findings and Actions (FAA) routes.

The FAA concern spans two routers:
- `faa_router` at /api/faa/* owns CRUD on individual items (get/put/
  delete/create by faa_id).
- `sessions_router` hosts session-scoped FAA endpoints that live under
  /api/sessions/{id}/faa/* (analyze, list items, export to CSV).

This module owns all FAA route handlers regardless of which router they
attach to. The sessions-scoped routes import `sessions_router` from
_legacy while sessions routes live there; after Phase 2.1f lands, the
import path will flip to routes.sessions.
"""
import logging
from datetime import datetime
from typing import Dict, List, Literal, Optional, cast

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel

from app.core.services.llm_factory import get_llm_service
from app.core.storage.settings_store import SettingsStore
from app.core.storage.storage_factory import get_storage
from app.modules.red_team.models import (
    FAAItem,
    FAAItemCreate,
    FAAItemUpdate,
)
from app.core.exceptions import RedTeamKBError
from app.modules.red_team.routes.sessions import sessions_router
from app.modules.red_team.services import export_session_faa_csv
from app.modules.red_team.services_validated import (
    ValidationConfig,
    analyze_session_for_faa_validated,
)

logger = logging.getLogger(__name__)


faa_router = APIRouter(prefix="/api/faa", tags=["faa"])


# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------


class FAAAnalysisResponse(BaseModel):
    """Response model for FAA analysis with validation info."""
    items: List[FAAItem]
    validation_summary: Dict
    warnings: List[str]
    dropped_count: int


# ---------------------------------------------------------------------------
# Session-scoped FAA routes (attach to sessions_router)
# ---------------------------------------------------------------------------


@sessions_router.post("/{session_id}/faa/analyze", response_model=FAAAnalysisResponse)
async def analyze_session_faa(session_id: str) -> FAAAnalysisResponse:
    """
    Analyze a session and classify activities as actions or findings.
    Uses hallucination guard to validate LLM outputs.

    Args:
        session_id: Session ID to analyze

    Returns:
        FAAAnalysisResponse with validated items and validation summary
    """
    try:
        # Get storage and LLM service
        settings_store = SettingsStore()
        app_settings = await settings_store.load_settings()
        storage = get_storage(app_settings)
        llm_service = get_llm_service(app_settings)

        # Verify session exists
        session = await storage.get_session(session_id)
        if not session:
            raise HTTPException(
                status_code=404,
                detail=f"Session {session_id} not found"
            )

        # Analyze session with hallucination guard validation
        result = await analyze_session_for_faa_validated(
            session_id,
            storage,
            llm_service,
            config=ValidationConfig(
                STRICT_MITRE_VALIDATION=True,
                MIN_CONFIDENCE_AUTO_ACCEPT=0.7,
                MIN_CONFIDENCE_INCLUDE=0.3,
                ENABLE_AUTO_CORRECTION=True
            )
        )

        faa_items = result["items"]
        validation_summary = result["validation_summary"]
        warnings = result["warnings"]
        dropped_items = result["dropped_items"]

        # Log validation results
        logger.info(
            f"FAA analysis complete: {len(faa_items)} validated items, "
            f"{len(dropped_items)} dropped, {len(warnings)} warnings"
        )
        if warnings:
            logger.warning(f"FAA validation warnings: {warnings[:5]}")

        # Save validated FAA items
        if faa_items:
            await storage.save_faa_items(session_id, faa_items)

        return FAAAnalysisResponse(
            items=faa_items,
            validation_summary=validation_summary,
            warnings=warnings,
            dropped_count=len(dropped_items)
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to analyze session for FAA: {e}")
        raise RedTeamKBError("Failed to analyze session") from e


@sessions_router.get("/{session_id}/faa", response_model=List[FAAItem])
async def get_session_faa_items(
    session_id: str,
    classification: Optional[str] = Query(None, description="Filter by classification (action/finding)"),
    mitre_technique: Optional[str] = Query(None, description="Filter by MITRE technique"),
    severity: Optional[str] = Query(None, description="Filter by severity (for findings)")
) -> List[FAAItem]:
    """
    Get all FAA items for a session with optional filters.

    Args:
        session_id: Session ID
        classification: Optional filter by classification
        mitre_technique: Optional filter by MITRE technique
        severity: Optional filter by severity

    Returns:
        List of FAA items
    """
    try:
        # Get storage
        settings_store = SettingsStore()
        app_settings = await settings_store.load_settings()
        storage = get_storage(app_settings)

        # Verify session exists
        session = await storage.get_session(session_id)
        if not session:
            raise HTTPException(
                status_code=404,
                detail=f"Session {session_id} not found"
            )

        # Get FAA items with filters
        faa_items = await storage.list_faa_items(
            session_id=session_id,
            classification=classification,
            mitre_technique=mitre_technique,
            severity=severity
        )

        return faa_items

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get FAA items: {e}")
        raise RedTeamKBError("Failed to get FAA items") from e


@sessions_router.get("/{session_id}/faa/export")
async def export_session_faa(
    session_id: str,
    format: str = Query(default="csv", description="Export format (csv)"),
    classification: Optional[str] = Query(
        default=None,
        description="If 'finding' or 'action', export only that classification "
        "(findings use the extended template columns). Omit for all items.",
    ),
) -> Response:
    """
    Export all FAA items from a session to CSV.

    Args:
        session_id: Session ID to export
        format: Export format (currently only csv supported)
        classification: Optional filter: finding, action, or None for all

    Returns:
        CSV file download
    """
    try:
        if classification is not None and classification not in ("finding", "action"):
            raise HTTPException(
                status_code=400,
                detail="classification must be 'finding', 'action', or omitted",
            )
        class_filter: Optional[Literal["finding", "action"]] = cast(
            Optional[Literal["finding", "action"]], classification
        )

        # Get storage
        settings_store = SettingsStore()
        app_settings = await settings_store.load_settings()
        storage = get_storage(app_settings)

        # Verify session exists
        session = await storage.get_session(session_id)
        if not session:
            raise HTTPException(
                status_code=404,
                detail=f"Session {session_id} not found"
            )

        # Generate CSV
        csv_content = await export_session_faa_csv(
            session_id, storage, classification=class_filter
        )

        # Generate filename
        session_title_safe = "".join(c for c in session.title if c.isalnum() or c in (' ', '-', '_')).strip()[:50]
        session_title_safe = session_title_safe.replace(' ', '_')
        date_str = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        suffix = ""
        if classification == "finding":
            suffix = "_findings"
        elif classification == "action":
            suffix = "_actions"
        filename = f"session_{session_title_safe}_faa{suffix}_{date_str}.csv"

        # Return CSV file
        return Response(
            content=csv_content,
            media_type="text/csv",
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"'
            }
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to export session FAA: {e}")
        raise RedTeamKBError("Failed to export FAA") from e


# ---------------------------------------------------------------------------
# Item-scoped FAA routes on faa_router
# ---------------------------------------------------------------------------


@faa_router.get("/{faa_id}", response_model=FAAItem)
async def get_faa_item(
    faa_id: str,
    session_id: str = Query(..., description="Session ID to locate the item")
) -> FAAItem:
    """
    Get a single FAA item by ID.

    Args:
        faa_id: FAA item ID
        session_id: Session ID to locate the item

    Returns:
        FAA item object
    """
    try:
        # Get storage
        settings_store = SettingsStore()
        app_settings = await settings_store.load_settings()
        storage = get_storage(app_settings)

        # Get FAA item
        faa_item = await storage.get_faa_item(faa_id, session_id)
        if not faa_item:
            raise HTTPException(
                status_code=404,
                detail=f"FAA item {faa_id} not found"
            )

        return faa_item

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get FAA item: {e}")
        raise RedTeamKBError("Failed to get FAA item") from e


@faa_router.put("/{faa_id}", response_model=FAAItem)
async def update_faa_item(
    faa_id: str,
    update_data: FAAItemUpdate,
    session_id: str = Query(..., description="Session ID to locate the item")
) -> FAAItem:
    """
    Update an existing FAA item.

    Args:
        faa_id: FAA item ID
        update_data: Fields to update
        session_id: Session ID to locate the item

    Returns:
        Updated FAA item
    """
    try:
        # Get storage
        settings_store = SettingsStore()
        app_settings = await settings_store.load_settings()
        storage = get_storage(app_settings)

        # Update FAA item
        faa_item = await storage.update_faa_item(faa_id, session_id, update_data)
        if not faa_item:
            raise HTTPException(
                status_code=404,
                detail=f"FAA item {faa_id} not found"
            )

        return faa_item

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update FAA item: {e}")
        raise RedTeamKBError("Failed to update FAA item") from e


@faa_router.delete("/{faa_id}")
async def delete_faa_item(
    faa_id: str,
    session_id: str = Query(..., description="Session ID to locate the item")
) -> dict:
    """
    Delete an FAA item.

    Args:
        faa_id: FAA item ID
        session_id: Session ID to locate the item

    Returns:
        Success message
    """
    try:
        # Get storage
        settings_store = SettingsStore()
        app_settings = await settings_store.load_settings()
        storage = get_storage(app_settings)

        # Delete FAA item
        deleted = await storage.delete_faa_item(faa_id, session_id)
        if not deleted:
            raise HTTPException(
                status_code=404,
                detail=f"FAA item {faa_id} not found"
            )

        return {"message": "FAA item deleted successfully"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to delete FAA item: {e}")
        raise RedTeamKBError("Failed to delete FAA item") from e


@faa_router.post("", response_model=FAAItem, status_code=201)
async def create_faa_item(faa_data: FAAItemCreate) -> FAAItem:
    """
    Manually create a new FAA item.

    Args:
        faa_data: FAA item creation data

    Returns:
        Created FAA item
    """
    try:
        # Get storage
        settings_store = SettingsStore()
        app_settings = await settings_store.load_settings()
        storage = get_storage(app_settings)

        # Verify session exists
        session = await storage.get_session(faa_data.session_id)
        if not session:
            raise HTTPException(
                status_code=404,
                detail=f"Session {faa_data.session_id} not found"
            )

        # Create FAA item
        faa_item = await storage.create_faa_item(faa_data)

        return faa_item

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to create FAA item: {e}")
        raise RedTeamKBError("Failed to create FAA item") from e

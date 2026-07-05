"""
Operation CRUD routes (/api/operations) and operation-scoped FAA export.

Operations are the top-level container in the red-team domain - each
session belongs to exactly one operation. This module owns the
operations_router: create/list/get/update/delete operations, summary
endpoint with session counts, and CSV export of all FAA items under
an operation.

The /operations/{id}/faa/export route lives here because it's attached
to operations_router (shares the prefix); the rest of the FAA surface
lives in routes/faa.py.
"""
import logging
from datetime import datetime
from typing import List, Literal, Optional, cast

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel

from app.core.storage.settings_store import SettingsStore
from app.core.storage.storage_factory import get_storage
from app.integrations.event_notifier import notify_event
from app.modules.red_team.models import (
    Operation,
    OperationCreate,
    OperationUpdate,
    Session,
)
from app.core.exceptions import RedTeamKBError
from app.modules.red_team.services import export_operation_faa_csv

logger = logging.getLogger(__name__)


operations_router = APIRouter(prefix="/api/operations", tags=["operations"])


# ---------------------------------------------------------------------------
# Response models scoped to operations routes
# ---------------------------------------------------------------------------


class OperationSummary(BaseModel):
    """Summary model for operation with session count."""
    id: str
    name: str
    session_count: int
    status: str


class PaginatedOperations(BaseModel):
    """Paginated operations response."""
    items: List[Operation]
    total: int
    page: int
    page_size: int
    total_pages: int


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------


@operations_router.post("", response_model=Operation, status_code=201)
async def create_operation(operation_data: OperationCreate) -> Operation:
    """
    Create a new operation.

    Args:
        operation_data: Operation creation data

    Returns:
        Created operation object
    """
    try:
        settings_store = SettingsStore()
        app_settings = await settings_store.load_settings()
        storage = get_storage(app_settings)
        operation = await storage.create_operation(operation_data)

        # Send webhook notification
        await notify_event("operation.created", {
            "id": operation.id,
            "name": operation.name,
            "description": operation.description,
            "status": operation.status,
        })

        return operation
    except Exception as e:
        raise RedTeamKBError("Failed to create operation") from e


@operations_router.get("")
async def list_operations(
    page: int = Query(1, ge=1, description="Page number (1-indexed)"),
    page_size: int = Query(50, ge=1, le=100, description="Items per page (max 100)"),
    status: Optional[str] = Query(None, description="Filter by status (active/archived)")
) -> PaginatedOperations:
    """
    List all operations with pagination.

    Args:
        page: Page number (1-indexed)
        page_size: Number of items per page
        status: Optional status filter

    Returns:
        Paginated list of operation objects
    """
    try:
        settings_store = SettingsStore()
        app_settings = await settings_store.load_settings()
        storage = get_storage(app_settings)
        operations = await storage.list_operations()

        # Apply status filter if provided
        if status:
            operations = [op for op in operations if op.status == status]

        # Sort by created_at descending (most recent first)
        operations.sort(key=lambda x: x.created_at, reverse=True)

        # Calculate pagination
        total = len(operations)
        total_pages = (total + page_size - 1) // page_size if total > 0 else 1
        start_idx = (page - 1) * page_size
        end_idx = start_idx + page_size

        paginated_items = operations[start_idx:end_idx]

        return PaginatedOperations(
            items=paginated_items,
            total=total,
            page=page,
            page_size=page_size,
            total_pages=total_pages
        )
    except Exception as e:
        raise RedTeamKBError("Failed to list operations") from e


@operations_router.get("/summary", response_model=List[OperationSummary])
async def get_operations_summary() -> List[OperationSummary]:
    """
    Get summary of all operations with session counts.
    This endpoint is useful for frontend dropdowns showing operation statistics.

    Returns:
        List of operation summaries with session counts
    """
    try:
        settings_store = SettingsStore()
        app_settings = await settings_store.load_settings()
        storage = get_storage(app_settings)

        # Get all operations
        operations = await storage.list_operations()

        # Get all sessions to count sessions per operation
        all_sessions = await storage.list_sessions()

        # Build operation ID to session count mapping
        operation_session_counts: dict[str, int] = {}
        for session in all_sessions:
            if session.operation_id:
                operation_session_counts[session.operation_id] = (
                    operation_session_counts.get(session.operation_id, 0) + 1
                )

        # Build summary list
        summaries = []
        for operation in operations:
            session_count = operation_session_counts.get(operation.id, len(operation.session_ids))
            summaries.append(OperationSummary(
                id=operation.id,
                name=operation.name,
                session_count=session_count,
                status=operation.status
            ))

        return summaries
    except Exception as e:
        raise RedTeamKBError("Failed to get operations summary") from e


@operations_router.get("/{operation_id}", response_model=Operation)
async def get_operation(operation_id: str) -> Operation:
    """
    Get a specific operation by ID.

    Args:
        operation_id: Unique operation identifier

    Returns:
        Operation object
    """
    settings_store = SettingsStore()
    app_settings = await settings_store.load_settings()
    storage = get_storage(app_settings)
    operation = await storage.get_operation(operation_id)
    if not operation:
        raise HTTPException(status_code=404, detail=f"Operation {operation_id} not found")
    return operation


@operations_router.get("/{operation_id}/sessions", response_model=List[Session])
async def get_operation_sessions(operation_id: str) -> List[Session]:
    """
    Get all sessions belonging to a specific operation.

    Args:
        operation_id: Unique operation identifier

    Returns:
        List of session objects
    """
    settings_store = SettingsStore()
    app_settings = await settings_store.load_settings()
    storage = get_storage(app_settings)

    # Verify operation exists
    operation = await storage.get_operation(operation_id)
    if not operation:
        raise HTTPException(status_code=404, detail=f"Operation {operation_id} not found")

    # Load all sessions for this operation
    sessions = []
    for session_id in operation.session_ids:
        session = await storage.get_session(session_id)
        if session:
            sessions.append(session)

    return sessions


@operations_router.put("/{operation_id}", response_model=Operation)
async def update_operation(operation_id: str, update_data: OperationUpdate) -> Operation:
    """
    Update an existing operation.

    Args:
        operation_id: Unique operation identifier
        update_data: Fields to update

    Returns:
        Updated operation object
    """
    settings_store = SettingsStore()
    app_settings = await settings_store.load_settings()
    storage = get_storage(app_settings)
    operation = await storage.update_operation(operation_id, update_data)
    if not operation:
        raise HTTPException(status_code=404, detail=f"Operation {operation_id} not found")

    # Send webhook notification
    await notify_event("operation.updated", {
        "id": operation.id,
        "name": operation.name,
        "description": operation.description,
        "status": operation.status,
    })

    return operation


@operations_router.delete("/{operation_id}", status_code=204)
async def delete_operation(
    operation_id: str,
    delete_sessions: bool = Query(False, description="Whether to delete associated sessions")
) -> None:
    """
    Delete an operation and optionally its sessions.

    Args:
        operation_id: Unique operation identifier
        delete_sessions: If True, also delete all sessions in this operation
    """
    settings_store = SettingsStore()
    app_settings = await settings_store.load_settings()
    storage = get_storage(app_settings)

    # Get operation to check session_ids
    operation = await storage.get_operation(operation_id)
    if not operation:
        raise HTTPException(status_code=404, detail=f"Operation {operation_id} not found")

    # Delete sessions if requested
    if delete_sessions:
        for session_id in operation.session_ids:
            try:
                await storage.delete_session(session_id)
            except Exception as e:
                # Log but don't fail if session deletion fails
                print(f"Warning: Failed to delete session {session_id}: {e}")

    # Delete operation
    deleted = await storage.delete_operation(operation_id)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Operation {operation_id} not found")


# ---------------------------------------------------------------------------
# Operation-scoped FAA export (the rest of FAA lives in routes/faa.py)
# ---------------------------------------------------------------------------


@operations_router.get("/{operation_id}/faa/export")
async def export_operation_faa(
    operation_id: str,
    format: str = Query(default="csv", description="Export format (csv)"),
    classification: Optional[str] = Query(
        default=None,
        description="If 'finding' or 'action', export only that classification "
        "(findings use the extended template columns). Omit for all items.",
    ),
) -> Response:
    """
    Export all FAA items from an operation to CSV.

    Args:
        operation_id: Operation ID to export
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

        # Verify operation exists
        operation = await storage.get_operation(operation_id)
        if not operation:
            raise HTTPException(
                status_code=404,
                detail=f"Operation {operation_id} not found"
            )

        # Generate CSV
        csv_content = await export_operation_faa_csv(
            operation_id, storage, classification=class_filter
        )

        # Generate filename
        operation_name_safe = "".join(c for c in operation.name if c.isalnum() or c in (' ', '-', '_')).strip()[:50]
        operation_name_safe = operation_name_safe.replace(' ', '_')
        date_str = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        suffix = ""
        if classification == "finding":
            suffix = "_findings"
        elif classification == "action":
            suffix = "_actions"
        filename = f"operation_{operation_name_safe}_faa{suffix}_{date_str}.csv"

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
        logger.error(f"Failed to export operation FAA: {e}")
        raise RedTeamKBError("Failed to export FAA") from e

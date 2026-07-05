"""
Query routes (/api/query).

LLM-backed question answering over red-team session data. The main
endpoint (`POST /api/query`) runs the user's question through the
hallucination-guarded validation pipeline in services_validated,
carrying confidence + validation warnings back to the frontend.

Cache endpoints (GET /history, GET /cache/{id}, DELETE /cache/{id}) are
backed by QueryCacheStore, which sits under app.core.storage.
"""
import logging
from typing import Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, ConfigDict

from app.config import settings
from app.core.services.llm_factory import get_llm_service
from app.core.storage.query_cache_store import QueryCacheStore
from app.core.storage.settings_store import SettingsStore
from app.core.storage.storage_factory import get_storage
from app.modules.red_team.models import Session
from app.modules.red_team.services_validated import query_with_validation
from app.modules.red_team.storage import build_query_context
from app.core.exceptions import RedTeamKBError

logger = logging.getLogger(__name__)


query_router = APIRouter(prefix="/api/query", tags=["query"])


# ---------------------------------------------------------------------------
# Request/response models scoped to query
# ---------------------------------------------------------------------------


class SessionSource(BaseModel):
    """Source session information for query response."""
    session_id: str
    session_title: str
    operation_id: Optional[str]
    operation_name: Optional[str]
    timestamp: str


class QueryRequest(BaseModel):
    """Request model for query endpoint."""
    question: str
    operation_id: Optional[str] = None
    session_ids: Optional[List[str]] = None

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "question": "What ports were scanned in the recent sessions?",
                "operation_id": "op-123",
                "session_ids": ["session-123", "session-456"]
            }
        }
    )


class QueryResponse(BaseModel):
    """Response model for query endpoint."""
    answer: str
    sources: List[SessionSource] = []
    scope: str  # "all" or operation name
    session_count: int
    operation_count: Optional[int] = None  # Only for "all" scope
    # Validation fields (hallucination guard)
    confidence: Optional[float] = None  # 0.0 to 1.0
    validation_warnings: Optional[List[str]] = None
    recommended_action: Optional[str] = None  # "accept", "review", "reject"

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "answer": "Based on the session logs, ports 22, 80, 443, and 8080 were scanned...",
                "sources": [],
                "scope": "all",
                "session_count": 45,
                "operation_count": 3
            }
        }
    )


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@query_router.post("", response_model=QueryResponse)
async def query_sessions(request: QueryRequest) -> QueryResponse:
    """
    Query the knowledge base using configured LLM provider with context from sessions.

    Args:
        request: Query request with question, optional operation_id, and optional session IDs

    Returns:
        Query response with LLM's answer, sources, and scope information
    """
    # Validate query
    if not request.question or not request.question.strip():
        raise HTTPException(status_code=400, detail="Question cannot be empty")

    # Validate operation_id format if provided
    operation_id = request.operation_id
    if operation_id and operation_id.strip() == "":
        raise HTTPException(status_code=400, detail="Invalid operation ID")

    # Normalize operation_id: treat None and "all" as querying all operations
    if operation_id and operation_id.strip().lower() == "all":
        operation_id = None

    try:
        # Get settings and storage
        settings_store = SettingsStore()
        app_settings = await settings_store.load_settings()
        storage = get_storage(app_settings)

        # Get LLM service
        if not app_settings.llm_config:
            raise HTTPException(
                status_code=503,
                detail="LLM service not configured. Please configure LLM settings."
            )

        llm_service = get_llm_service(app_settings, storage=storage)

        # Determine scope and load sessions
        scope = "all"
        operation_name = None
        operation_count = None
        sessions: List[Session] = []

        if request.session_ids:
            # Load specific sessions (ignore operation_id when session_ids are provided)
            logger.info(f"Query received: \"{request.question[:50]}...\" | Scope: Specific Sessions | Count: {len(request.session_ids)}")
            for session_id in request.session_ids[:settings.max_context_sessions]:
                session = await storage.get_session(session_id)
                if session:
                    sessions.append(session)
        elif operation_id:
            # Load all sessions from specific operation
            # Verify operation exists
            operation = await storage.get_operation(operation_id)
            if not operation:
                raise HTTPException(status_code=404, detail="Operation not found")

            operation_name = operation.name
            scope = operation_name

            # Load all sessions from this operation
            all_sessions = await storage.list_sessions()
            sessions = [s for s in all_sessions if s.operation_id == operation_id]

            if not sessions:
                raise HTTPException(
                    status_code=404,
                    detail="No sessions found for this operation"
                )

            # Sort by timestamp descending (most recent first)
            sessions.sort(key=lambda x: x.created_at, reverse=True)

            # Load full terminal content for all sessions
            full_sessions = []
            for session in sessions:
                full_session = await storage.get_session(session.id)
                if full_session:
                    full_sessions.append(full_session)
            sessions = full_sessions

            logger.info(
                f"Query received: \"{request.question[:50]}...\" | "
                f"Scope: Operation {operation_name} | Sessions: {len(sessions)}"
            )
        else:
            # Load recent sessions across all operations
            all_sessions = await storage.list_sessions()
            # Sort by timestamp descending (most recent first)
            all_sessions.sort(key=lambda x: x.created_at, reverse=True)
            # Limit to MAX_CONTEXT_SESSIONS
            limited_sessions = all_sessions[:settings.max_context_sessions]

            # Load full terminal content
            full_sessions = []
            for session in limited_sessions:
                full_session = await storage.get_session(session.id)
                if full_session:
                    full_sessions.append(full_session)
            sessions = full_sessions

            # Count unique operations
            unique_operations = {s.operation_id for s in sessions if s.operation_id}
            operation_count = len(unique_operations)

            operation_names = []
            for op_id in unique_operations:
                try:
                    op = await storage.get_operation(op_id)
                    if op:
                        operation_names.append(op.name)
                except Exception:
                    pass

            logger.info(
                f"Query received: \"{request.question[:50]}...\" | "
                f"Scope: All Operations | Sessions: {len(sessions)} | Operations: {operation_count}"
            )
            if operation_names:
                logger.info(f"Operations involved: {', '.join(operation_names)}")

        if not sessions:
            raise HTTPException(
                status_code=404,
                detail="No sessions available for query"
            )

        # Build context using helper function
        include_operation_names = (operation_id is None and not request.session_ids)
        context = await build_query_context(sessions, include_operation_names, storage)

        # Query LLM with hallucination guard validation
        query_result = await query_with_validation(
            question=request.question,
            context=context,
            llm_service=llm_service,
            scope="all" if operation_id is None else "single",
            operation_name=operation_name
        )

        answer = query_result["answer"]
        validation_confidence = query_result.get("confidence", None)
        validation_warnings = query_result.get("warnings", [])
        recommended_action = query_result.get("recommended_action", None)

        # Log validation info
        if validation_confidence is not None:
            logger.info(
                f"Query response validated: confidence={validation_confidence:.2f}, "
                f"action={recommended_action}"
            )
            if validation_warnings:
                logger.warning(f"Query validation warnings: {validation_warnings[:3]}")

        # Build sources list
        sources: List[SessionSource] = []
        for session in sessions:
            session_operation_name = None
            if session.operation_id:
                try:
                    op = await storage.get_operation(session.operation_id)
                    if op:
                        session_operation_name = op.name
                except Exception:
                    pass

            sources.append(SessionSource(
                session_id=session.id,
                session_title=session.title,
                operation_id=session.operation_id,
                operation_name=session_operation_name,
                timestamp=session.created_at.isoformat()
            ))

        response = QueryResponse(
            answer=answer,
            sources=sources,
            scope=scope,
            session_count=len(sessions),
            operation_count=operation_count,
            confidence=validation_confidence,
            validation_warnings=validation_warnings if validation_warnings else None,
            recommended_action=recommended_action
        )

        # Save query to cache
        try:
            cache_store = QueryCacheStore()
            response_dict = response.model_dump(mode="json")
            await cache_store.save_query(
                question=request.question,
                operation_id=operation_id,
                response=response_dict
            )
        except Exception as cache_error:
            # Log cache error but don't fail the query
            logger.warning(f"Failed to cache query: {cache_error}")

        return response
    except HTTPException:
        raise
    except ValueError as e:
        raise RedTeamKBError("Internal server error") from e
    except RuntimeError as e:
        raise RedTeamKBError("Internal server error") from e
    except Exception as e:
        logger.exception(f"Failed to process query: {e}")
        raise RedTeamKBError("Failed to process query") from e


@query_router.get("/history")
async def get_query_history(limit: int = Query(10, ge=1, le=50)) -> List[Dict]:
    """
    Get the latest query history.

    Args:
        limit: Maximum number of queries to return (default: 10, max: 50)

    Returns:
        List of query cache entries with id, question, operation_id, and created_at
    """
    try:
        cache_store = QueryCacheStore()
        queries = await cache_store.list_queries(limit=limit)

        # Return simplified version for history (without full response)
        history = []
        for query in queries:
            history.append({
                "id": query.get("id"),
                "question": query.get("question"),
                "operation_id": query.get("operation_id"),
                "created_at": query.get("created_at"),
            })

        return history
    except Exception as e:
        logger.exception(f"Failed to get query history: {e}")
        raise RedTeamKBError("Failed to get query history") from e


@query_router.get("/cache/{cache_id}")
async def get_cached_query(cache_id: str) -> QueryResponse:
    """
    Get a cached query result by ID.

    Args:
        cache_id: The cache entry ID

    Returns:
        The cached query response
    """
    try:
        cache_store = QueryCacheStore()
        cache_entry = await cache_store.get_query(cache_id)

        if not cache_entry:
            raise HTTPException(status_code=404, detail="Cached query not found")

        # Return the cached response
        response_data = cache_entry.get("response")
        if not response_data:
            raise HTTPException(status_code=404, detail="Cached response not found")

        return QueryResponse(**response_data)
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Failed to get cached query: {e}")
        raise RedTeamKBError("Failed to get cached query") from e


@query_router.delete("/cache/{cache_id}", status_code=204)
async def delete_cached_query(cache_id: str) -> None:
    """
    Delete a cached query result by ID.

    Args:
        cache_id: The cache entry ID
    """
    try:
        cache_store = QueryCacheStore()
        deleted = await cache_store.delete_query(cache_id)

        if not deleted:
            raise HTTPException(status_code=404, detail="Cached query not found")
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Failed to delete cached query: {e}")
        raise RedTeamKBError("Failed to delete cached query") from e

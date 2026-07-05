"""
Insights routes (/api/insights/*) + cache helpers.

Insights combine general statistics (counts, timelines, top tools) with
LLM-generated expert analysis (kill-chain position, recommendations,
risk assessment). Both are expensive to compute, so results are cached
at two levels:
  - `_insights_cache` - in-memory dict keyed by operation-set hash
  - `CACHE_DIR` - on-disk JSON files persisting across restarts, reloaded
    at startup via `_load_cache_from_disk`

Session mutations in routes/sessions.py call
`invalidate_insights_for_operation` to keep the cache in step with
fresh session data. team.py calls `_load_cache_from_disk` and
`_invalidate_cache` during app startup to rehydrate memory from disk
and drop expired entries.

All three helpers are re-exported by the package __init__ so external
callers keep working unchanged.
"""
import hashlib
import json
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Optional, Union

import aiofiles
import aiofiles.os as aios
from fastapi import APIRouter, HTTPException, Query

from app.config import settings
from app.core.services.llm_factory import get_llm_service
from app.core.storage.settings_store import SettingsStore
from app.core.storage.storage_factory import get_storage
from app.integrations.event_notifier import notify_event
from app.modules.red_team.models import (
    CachedInsights,
    InsightsGenerateRequest,
    InsightsResponse,
    Session,
)
from app.modules.red_team.services import (
    create_empty_analysis,
    generate_general_insights,
)
from app.modules.red_team.services_validated import generate_expert_analysis_validated

logger = logging.getLogger(__name__)


insights_router = APIRouter(prefix="/api/insights", tags=["insights"])


# ---------------------------------------------------------------------------
# Cache state
# ---------------------------------------------------------------------------


# In-memory cache for insights
_insights_cache: dict[str, CachedInsights] = {}
# Cache expiry: 24 hours (1440 minutes) - insights don't change frequently
CACHE_EXPIRY_MINUTES = 1440

# Persistent cache directory
CACHE_DIR = Path(settings.data_dir) / "insights_cache"


# ---------------------------------------------------------------------------
# Cache helpers
# ---------------------------------------------------------------------------


def _generate_cache_key(operation_ids: Union[List[str], str]) -> str:
    """
    Generate a cache key from operation IDs.

    Args:
        operation_ids: List of operation IDs or "all"

    Returns:
        Cache key string
    """
    if isinstance(operation_ids, str):
        key_str = operation_ids
    else:
        # Sort to ensure consistent keys
        key_str = ",".join(sorted(operation_ids))

    return hashlib.md5(key_str.encode()).hexdigest()


async def _load_cache_from_disk() -> None:
    """
    Load cached insights from disk on startup.
    """
    try:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)

        if not CACHE_DIR.exists():
            return

        # Load all cache files
        for cache_file in CACHE_DIR.glob("*.json"):
            try:
                async with aiofiles.open(cache_file, 'r') as f:
                    content = await f.read()
                    data = json.loads(content)

                    # Parse datetime fields
                    cached_at = datetime.fromisoformat(data['cached_at'])
                    expires_at = datetime.fromisoformat(data['expires_at'])

                    # Check if expired
                    if datetime.utcnow() > expires_at:
                        cache_file.unlink()  # Delete expired cache
                        continue

                    # Reconstruct InsightsResponse
                    insights = InsightsResponse(**data['insights'])

                    # Reconstruct CachedInsights
                    cached = CachedInsights(
                        insights=insights,
                        cache_key=data['cache_key'],
                        cached_at=cached_at,
                        expires_at=expires_at
                    )

                    _insights_cache[data['cache_key']] = cached
                    logger.info(f"Loaded cached insights from {cache_file.name}")
            except Exception as e:
                logger.warning(f"Failed to load cache file {cache_file}: {e}")
                # Delete corrupted cache file
                try:
                    cache_file.unlink()
                except Exception:
                    pass
    except Exception as e:
        logger.error(f"Failed to load cache from disk: {e}", exc_info=True)


async def _get_cached_insights(cache_key: str) -> Optional[InsightsResponse]:
    """
    Get cached insights if available and not expired.
    Checks both in-memory and disk cache.

    Args:
        cache_key: Cache key

    Returns:
        Cached insights if available and valid, None otherwise
    """
    # Check in-memory cache first
    if cache_key in _insights_cache:
        cached = _insights_cache[cache_key]

        # Check if expired
        if datetime.utcnow() > cached.expires_at:
            logger.info(f"Cache expired for key {cache_key}")
            del _insights_cache[cache_key]
            # Also delete from disk
            await _delete_cache_file_async(cache_key)
            return None

        logger.info(f"Returning cached insights for key {cache_key}")
        return cached.insights

    # Try loading from disk using async I/O
    cache_file = CACHE_DIR / f"{cache_key}.json"
    if cache_file.exists():
        try:
            async with aiofiles.open(cache_file, 'r', encoding='utf-8') as f:
                content = await f.read()
                data = json.loads(content)

                # Parse datetime fields
                cached_at = datetime.fromisoformat(data['cached_at'])
                expires_at = datetime.fromisoformat(data['expires_at'])

                # Check if expired
                if datetime.utcnow() > expires_at:
                    await aios.remove(str(cache_file))
                    return None

                # Reconstruct InsightsResponse
                insights = InsightsResponse(**data['insights'])

                # Reconstruct CachedInsights and add to memory cache
                cached = CachedInsights(
                    insights=insights,
                    cache_key=data['cache_key'],
                    cached_at=cached_at,
                    expires_at=expires_at
                )

                _insights_cache[cache_key] = cached
                logger.info(f"Loaded and returning cached insights from disk for key {cache_key}")
                return cached.insights
        except Exception as e:
            logger.warning(f"Failed to load cache from disk for key {cache_key}: {e}")
            # Delete corrupted cache file
            try:
                await aios.remove(str(cache_file))
            except Exception:
                pass

    return None


async def _delete_cache_file_async(cache_key: str) -> None:
    """Delete cache file from disk asynchronously."""
    try:
        cache_file = CACHE_DIR / f"{cache_key}.json"
        if cache_file.exists():
            await aios.remove(str(cache_file))
    except Exception as e:
        logger.warning(f"Failed to delete cache file for key {cache_key}: {e}")


async def invalidate_insights_for_operation(operation_id: str) -> None:
    """
    Invalidate cached insights that include a specific operation.

    Called when sessions are created/updated/deleted to ensure insights
    reflect the latest data.

    Args:
        operation_id: The operation ID whose insights cache should be invalidated
    """
    # Generate cache keys that could include this operation
    # 1. Single operation key
    single_op_key = _generate_cache_key([operation_id])

    # 2. "all" operations key
    all_ops_key = _generate_cache_key("all")

    # Invalidate both from memory and disk
    keys_to_invalidate = [single_op_key, all_ops_key]

    for cache_key in keys_to_invalidate:
        # Remove from memory cache
        if cache_key in _insights_cache:
            del _insights_cache[cache_key]
            logger.info(f"Invalidated in-memory insights cache for key {cache_key}")

        # Remove from disk
        await _delete_cache_file_async(cache_key)

    # Also check for any multi-operation keys that might include this operation
    # These would have the operation_id as part of a comma-separated list
    # We scan all cache files and check if operation_id is in their key pattern
    try:
        if CACHE_DIR.exists():
            for cache_file in CACHE_DIR.glob("*.json"):
                try:
                    async with aiofiles.open(cache_file, 'r', encoding='utf-8') as f:
                        content = await f.read()
                        data = json.loads(content)

                        # Check if this cache includes the operation
                        # We can't easily determine this from the hash key alone,
                        # but we can be conservative and invalidate all multi-operation caches
                        # A more sophisticated approach would store the operation IDs in the cache
                        cache_key = data.get('cache_key', '')
                        if cache_key and cache_key not in keys_to_invalidate:
                            # For safety, invalidate any cache that isn't single-op or "all"
                            # This is conservative but ensures correctness
                            if cache_key in _insights_cache:
                                del _insights_cache[cache_key]
                            await aios.remove(str(cache_file))
                            logger.info(f"Invalidated multi-operation insights cache {cache_file.name}")
                except Exception as e:
                    logger.warning(f"Error checking cache file {cache_file}: {e}")
    except Exception as e:
        logger.warning(f"Error scanning cache directory: {e}")

    logger.info(f"Insights cache invalidated for operation {operation_id}")


def _delete_cache_file(cache_key: str) -> None:
    """Delete cache file from disk."""
    try:
        cache_file = CACHE_DIR / f"{cache_key}.json"
        if cache_file.exists():
            cache_file.unlink()
    except Exception as e:
        logger.warning(f"Failed to delete cache file for key {cache_key}: {e}")


async def _cache_insights(cache_key: str, insights: InsightsResponse) -> None:
    """
    Cache insights with expiration (both in-memory and on disk).

    Args:
        cache_key: Cache key
        insights: Insights response to cache
    """
    expires_at = datetime.utcnow() + timedelta(minutes=CACHE_EXPIRY_MINUTES)

    cached = CachedInsights(
        insights=insights,
        cache_key=cache_key,
        cached_at=datetime.utcnow(),
        expires_at=expires_at
    )

    # Store in memory
    _insights_cache[cache_key] = cached
    logger.info(f"Cached insights in memory for key {cache_key}, expires at {expires_at}")

    # Store on disk
    try:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        cache_file = CACHE_DIR / f"{cache_key}.json"

        # Serialize to JSON
        cache_data = {
            "insights": insights.model_dump(mode='json'),
            "cache_key": cache_key,
            "cached_at": cached.cached_at.isoformat(),
            "expires_at": cached.expires_at.isoformat()
        }

        async with aiofiles.open(cache_file, 'w') as f:
            await f.write(json.dumps(cache_data, indent=2))

        logger.info(f"Cached insights to disk for key {cache_key}")
    except Exception as e:
        logger.error(f"Failed to cache insights to disk for key {cache_key}: {e}", exc_info=True)


def _invalidate_cache() -> None:
    """
    Invalidate all expired cache entries.
    Also clears cache files that have old expiry times (< 24 hours from creation).
    """
    # Clear expired entries from memory
    now = datetime.utcnow()
    expired_keys = [
        key for key, cached in _insights_cache.items()
        if now > cached.expires_at
    ]
    for key in expired_keys:
        del _insights_cache[key]
        _delete_cache_file(key)

    # Also check disk for old cache files (created with 5-minute expiry)
    # Delete any cache files that expire too soon (less than 20 hours from now)
    try:
        if CACHE_DIR.exists():
            for cache_file in CACHE_DIR.glob("*.json"):
                try:
                    with open(cache_file, 'r') as f:
                        data = json.load(f)
                        expires_at = datetime.fromisoformat(data.get('expires_at', ''))

                        # If cache expires in less than 20 hours, it was likely created with old 5-min expiry
                        # Delete it so it can be regenerated with new 24-hour expiry
                        time_until_expiry = (expires_at - now).total_seconds() / 3600  # hours
                        if time_until_expiry < 20:
                            cache_file.unlink()
                            logger.info(f"Deleted old cache file {cache_file.name} (expired or short expiry)")
                except Exception as e:
                    logger.warning(f"Error checking cache file {cache_file}: {e}")
    except Exception as e:
        logger.warning(f"Error invalidating cache files: {e}")

    if expired_keys:
        logger.info(f"Invalidated {len(expired_keys)} expired cache entries")


async def _load_sessions_for_operations(
    operation_ids: Union[List[str], str],
    storage
) -> tuple[List[Session], List[str]]:
    """
    Load all sessions for the specified operations.

    Args:
        operation_ids: List of operation IDs or "all"
        storage: Storage instance

    Returns:
        Tuple of (sessions list, operation names list)

    Raises:
        HTTPException: If operation not found or no sessions found
    """
    sessions = []
    operation_names = []

    if operation_ids == "all":
        # Load all operations
        operations = await storage.list_operations()
        operation_ids_list = [op.id for op in operations]
        operation_names = [op.name for op in operations]

        logger.info(f"Loading sessions from all {len(operations)} operations")
    else:
        # Load specific operations
        if isinstance(operation_ids, str):
            operation_ids_list = [operation_ids]
        else:
            operation_ids_list = operation_ids

        logger.info(f"Loading sessions from {len(operation_ids_list)} operations")

    # Load sessions from each operation
    for operation_id in operation_ids_list:
        operation = await storage.get_operation(operation_id)
        if not operation:
            raise HTTPException(
                status_code=404,
                detail=f"Operation {operation_id} not found"
            )

        operation_names.append(operation.name)

        # Load sessions for this operation
        for session_id in operation.session_ids:
            session = await storage.get_session(session_id)
            if session:
                sessions.append(session)

    if not sessions:
        raise HTTPException(
            status_code=404,
            detail="No sessions found for the specified operations"
        )

    logger.info(f"Loaded {len(sessions)} sessions from {len(operation_names)} operations")
    return sessions, operation_names


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@insights_router.post("/generate", response_model=InsightsResponse)
async def generate_insights(
    request: InsightsGenerateRequest,
    force_refresh: bool = Query(False, description="Force refresh even if cache exists")
) -> InsightsResponse:
    """
    Generate insights (general statistics and expert analysis) for specified operations.

    Args:
        request: Request with operation_ids (list or "all")
        force_refresh: If True, regenerate insights even if cached version exists

    Returns:
        InsightsResponse with general insights and expert analysis
    """
    start_time = datetime.utcnow()

    try:
        # Generate cache key
        cache_key = _generate_cache_key(request.operation_ids)

        # Check cache first (unless force_refresh is True)
        if not force_refresh:
            cached = await _get_cached_insights(cache_key)
            if cached:
                logger.info("Returning cached insights")
                return cached
        else:
            logger.info("Force refresh requested, bypassing cache")
            # Delete existing cache if force_refresh
            if cache_key in _insights_cache:
                del _insights_cache[cache_key]
            _delete_cache_file(cache_key)

        # Get storage and settings
        settings_store = SettingsStore()
        app_settings = await settings_store.load_settings()
        storage = get_storage(app_settings)

        # Load sessions
        sessions, operation_names = await _load_sessions_for_operations(
            request.operation_ids,
            storage
        )

        logger.info(
            f"Generating insights for {len(sessions)} sessions "
            f"from {len(operation_names)} operations"
        )

        # Generate general insights (fast, no LLM needed)
        general_insights = await generate_general_insights(sessions)

        # Generate expert analysis (requires LLM) - with hallucination guard
        expert_analysis = None
        validation_warnings = []
        if app_settings.llm_config:
            try:
                llm_service = get_llm_service(app_settings)
                # Use validated expert analysis with hallucination guard
                analysis_result = await generate_expert_analysis_validated(
                    sessions,
                    llm_service,
                    operation_names
                )
                expert_analysis = analysis_result["analysis"]
                validation_warnings = analysis_result.get("warnings", [])

                # Log validation info
                if analysis_result.get("validation_result"):
                    confidence = analysis_result.get("overall_confidence", 0)
                    action = analysis_result.get("recommended_action", "unknown")
                    logger.info(
                        f"Expert analysis generated using {app_settings.llm_provider.value} "
                        f"(confidence: {confidence:.2f}, action: {action})"
                    )
                    if validation_warnings:
                        logger.warning(f"Validation warnings: {validation_warnings[:3]}")
                else:
                    logger.info(f"Expert analysis generated using {app_settings.llm_provider.value}")
            except Exception as e:
                logger.error(f"Failed to generate expert analysis: {e}", exc_info=True)
                # Continue without expert analysis
                expert_analysis = create_empty_analysis(
                    f"Expert analysis unavailable: {str(e)}"
                )
        else:
            logger.warning("LLM not configured, skipping expert analysis")
            expert_analysis = create_empty_analysis(
                "LLM service not configured. Please configure LLM settings to enable expert analysis."
            )

        # Build response
        scope = request.operation_ids if isinstance(request.operation_ids, str) else request.operation_ids
        insights_response = InsightsResponse(
            general_insights=general_insights,
            expert_analysis=expert_analysis,
            scope=scope,
            generated_at=datetime.utcnow()
        )

        # Cache the response
        await _cache_insights(cache_key, insights_response)

        # Send webhook notification
        operation_name_str = ", ".join(operation_names) if operation_names else "Unknown"
        await notify_event("insights.generated", {
            "operation_ids": request.operation_ids if isinstance(request.operation_ids, list) else [request.operation_ids],
            "operation_name": operation_name_str,
            "session_count": len(sessions),
        })

        elapsed = (datetime.utcnow() - start_time).total_seconds()
        logger.info(f"Insights generation completed in {elapsed:.2f} seconds")

        return insights_response

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to generate insights: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to generate insights: {str(e)}"
        )


@insights_router.get("/cache")
async def get_cached_insights(
    operation_ids: Optional[str] = None
) -> Optional[dict]:
    """
    Get cached insights if available (without regenerating).

    Args:
        operation_ids: Comma-separated operation IDs or "all" (as query parameter)

    Returns:
        CachedInsights dict if available and not expired, None otherwise
    """
    # Clean up expired cache entries
    _invalidate_cache()

    if not operation_ids:
        return None

    # Parse operation_ids (could be "all" or comma-separated list)
    if operation_ids == "all":
        op_ids = "all"
    else:
        op_ids = [op_id.strip() for op_id in operation_ids.split(",")]

    # Generate cache key
    cache_key = _generate_cache_key(op_ids)

    # Get cached insights (checks both memory and disk)
    cached_insights = await _get_cached_insights(cache_key)

    if cached_insights:
        # Get metadata from in-memory cache or disk
        if cache_key in _insights_cache:
            cached = _insights_cache[cache_key]
            return {
                "insights": cached.insights.model_dump(mode='json'),
                "cache_key": cached.cache_key,
                "cached_at": cached.cached_at.isoformat(),
                "expires_at": cached.expires_at.isoformat()
            }
        else:
            # Load from disk to get metadata using async I/O
            cache_file = CACHE_DIR / f"{cache_key}.json"
            if cache_file.exists():
                try:
                    async with aiofiles.open(cache_file, 'r', encoding='utf-8') as f:
                        content = await f.read()
                        data = json.loads(content)
                        return {
                            "insights": data['insights'],
                            "cache_key": data['cache_key'],
                            "cached_at": data['cached_at'],
                            "expires_at": data['expires_at']
                        }
                except Exception as e:
                    logger.warning(f"Failed to load cache metadata from disk: {e}")

    return None

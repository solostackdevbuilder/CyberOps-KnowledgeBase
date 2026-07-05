"""
MITRE ATT&CK Detection Strategies API routes.

This module owns the /api/detection-strategies router. Unlike the other
red-team routers (operations, sessions, query, insights, faa), this one
is mounted directly on the FastAPI app by the TeamRegistry rather than
via the aggregated `router` in _legacy.py - so it lives independently
and has no cross-router helpers to worry about.

The underlying data comes from `app.modules.red_team.detection_strategies`,
which holds the DetectionStrategyService + MITRE data parsing. This
module is pure HTTP glue.
"""
import logging
from typing import List, Optional

from fastapi import APIRouter, HTTPException, Query

from app.core.storage.settings_store import SettingsStore
from app.core.storage.storage_factory import get_storage
from app.modules.red_team.detection_strategies import get_detection_strategy_service
from app.core.exceptions import RedTeamKBError

logger = logging.getLogger(__name__)


detection_strategies_router = APIRouter(
    prefix="/api/detection-strategies", tags=["detection-strategies"]
)


@detection_strategies_router.get("", response_model=List[dict])
async def list_detection_strategies(
    technique_id: Optional[str] = Query(None, description="Filter by MITRE ATT&CK technique ID (e.g., T1046)"),
    platform: Optional[str] = Query(None, description="Filter by platform (Windows, Linux, macOS, etc.)"),
    search: Optional[str] = Query(None, description="Search by name")
) -> List[dict]:
    """
    List all detection strategies with optional filters.

    Args:
        technique_id: Filter by MITRE ATT&CK technique ID
        platform: Filter by platform
        search: Search by strategy name

    Returns:
        List of detection strategies
    """
    try:
        service = get_detection_strategy_service()

        if technique_id:
            strategies = service.get_strategies_for_technique(technique_id)
        elif search:
            strategies = service.find_strategies_by_name(search)
        else:
            strategies = service.get_all_strategies()

        # Filter by platform if specified
        if platform:
            strategies = [
                s for s in strategies
                if platform.lower() in [p.lower() for p in s.platforms]
            ]

        return [s.model_dump() for s in strategies]
    except Exception as e:
        logger.error(f"Failed to list detection strategies: {e}")
        raise RedTeamKBError("Failed to list detection strategies") from e


@detection_strategies_router.get("/{strategy_id}", response_model=dict)
async def get_detection_strategy(strategy_id: str) -> dict:
    """
    Get a specific detection strategy by ID.

    Args:
        strategy_id: Detection strategy ID (e.g., DET0210)

    Returns:
        Detection strategy details
    """
    try:
        service = get_detection_strategy_service()

        strategy = service.get_strategy(strategy_id)
        if not strategy:
            raise HTTPException(
                status_code=404,
                detail=f"Detection strategy {strategy_id} not found"
            )

        return strategy.model_dump()
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get detection strategy: {e}")
        raise RedTeamKBError("Failed to get detection strategy") from e


@detection_strategies_router.get("/technique/{technique_id}", response_model=List[dict])
async def get_strategies_for_technique(technique_id: str) -> List[dict]:
    """
    Get all detection strategies for a specific MITRE ATT&CK technique.

    Args:
        technique_id: MITRE ATT&CK technique ID (e.g., T1046)

    Returns:
        List of detection strategies
    """
    try:
        service = get_detection_strategy_service()

        strategies = service.get_strategies_for_technique(technique_id)
        return [s.model_dump() for s in strategies]
    except Exception as e:
        logger.error(f"Failed to get strategies for technique: {e}")
        raise RedTeamKBError("Failed to get strategies") from e


@detection_strategies_router.post("/coverage-gaps", response_model=List[str])
async def get_coverage_gaps(technique_ids: List[str]) -> List[str]:
    """
    Identify techniques that have no detection strategies.

    Args:
        technique_ids: List of MITRE ATT&CK technique IDs to check

    Returns:
        List of technique IDs that have no detection strategies
    """
    try:
        service = get_detection_strategy_service()

        gaps = service.get_coverage_gaps(technique_ids)
        return gaps
    except Exception as e:
        logger.error(f"Failed to get coverage gaps: {e}")
        raise RedTeamKBError("Failed to get coverage gaps") from e


@detection_strategies_router.post("/operation/{operation_id}/coverage", response_model=dict)
async def get_operation_detection_coverage(operation_id: str) -> dict:
    """
    Get detection coverage analysis for an operation.

    Args:
        operation_id: Operation ID to analyze

    Returns:
        Coverage analysis including strategies, gaps, and recommendations
    """
    try:
        # Get storage
        settings_store = SettingsStore()
        app_settings = await settings_store.load_settings()
        storage = get_storage(app_settings)

        # Get operation
        operation = await storage.get_operation(operation_id)
        if not operation:
            raise HTTPException(
                status_code=404,
                detail=f"Operation {operation_id} not found"
            )

        # Get all sessions for the operation
        sessions = []
        for session_id in operation.session_ids:
            session = await storage.get_session(session_id)
            if session:
                sessions.append(session)

        # Get all FAA items for these sessions
        strategy_service = get_detection_strategy_service()

        all_techniques = set()
        techniques_with_strategies = set()
        techniques_without_strategies = set()
        all_strategy_ids = set()

        for session in sessions:
            try:
                faa_items = await storage.list_faa_items(session.id)
                for item in faa_items:
                    if item.mitre_technique:
                        try:
                            technique_id = strategy_service.extract_technique_id(item.mitre_technique)
                            if technique_id:
                                all_techniques.add(technique_id)
                                if item.detection_strategy_ids and len(item.detection_strategy_ids) > 0:
                                    techniques_with_strategies.add(technique_id)
                                    all_strategy_ids.update(item.detection_strategy_ids)
                                else:
                                    # Check if strategies exist even if not linked
                                    try:
                                        strategies = strategy_service.get_strategies_for_technique(technique_id)
                                        if strategies and len(strategies) > 0:
                                            techniques_with_strategies.add(technique_id)
                                            all_strategy_ids.update([s.id for s in strategies])
                                        else:
                                            techniques_without_strategies.add(technique_id)
                                    except Exception as e:
                                        logger.warning(f"Failed to get strategies for technique {technique_id}: {e}")
                                        techniques_without_strategies.add(technique_id)
                        except Exception as e:
                            logger.warning(f"Failed to extract technique ID from '{item.mitre_technique}': {e}")
                            continue
            except Exception as e:
                logger.warning(f"Failed to get FAA items for session {session.id}: {e}")
                continue

        # Get strategy details
        strategies = [strategy_service.get_strategy(sid) for sid in all_strategy_ids if strategy_service.get_strategy(sid)]

        # Get defensive guidance for techniques without strategies
        techniques_without_strategies_list = list(techniques_without_strategies)
        defensive_guidance = []
        for technique_id in techniques_without_strategies_list:
            guidance = strategy_service.get_defensive_guidance(technique_id)
            if guidance:
                defensive_guidance.append({
                    "technique_id": technique_id,
                    **guidance
                })
            else:
                # Default guidance if not in map
                defensive_guidance.append({
                    "technique_id": technique_id,
                    "title": f"Technique {technique_id}",
                    "what_to_check": [
                        f"Monitor for activities related to {technique_id}",
                        "Review MITRE ATT&CK documentation for detection guidance",
                        "Implement custom detection based on technique behavior"
                    ],
                    "monitoring": [
                        "Process execution logs",
                        "Network traffic logs",
                        "Authentication and access logs"
                    ],
                    "prevention": [
                        "Implement defense-in-depth strategies",
                        "Monitor and alert on suspicious activities",
                        "Review and update security controls"
                    ],
                    "mitre_url": f"https://attack.mitre.org/techniques/{technique_id}"
                })

        return {
            "operation_id": operation_id,
            "total_techniques": len(all_techniques),
            "techniques_with_strategies": len(techniques_with_strategies),
            "techniques_without_strategies": len(techniques_without_strategies),
            "coverage_percentage": (len(techniques_with_strategies) / len(all_techniques) * 100) if all_techniques else 0,
            "techniques_without_strategies_list": techniques_without_strategies_list,
            "detection_strategies": [s.model_dump() for s in strategies],
            "defensive_guidance": defensive_guidance,
            "recommendations": [
                f"Consider implementing custom detection for technique {t}"
                for t in techniques_without_strategies
            ] if techniques_without_strategies else []
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get operation coverage: {e}", exc_info=True)
        raise RedTeamKBError("Failed to get coverage") from e

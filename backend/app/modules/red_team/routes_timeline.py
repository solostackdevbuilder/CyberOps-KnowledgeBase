"""
Timeline and Command Analysis routes for red team operations.
Extracted from app/routes.py to consolidate routing.
"""
import logging
from datetime import datetime
from typing import Dict, List, Optional, Union

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from app.config import settings
from app.core.storage.settings_store import SettingsStore
from app.core.storage.storage_factory import get_storage
from app.core.services.llm_factory import get_llm_service
from app.modules.red_team.services import generate_expert_analysis
from app.utils.command_extractor import (
    extract_commands, analyze_command_frequency,
    detect_command_patterns, build_command_timeline
)
from app.core.exceptions import RedTeamKBError

logger = logging.getLogger(__name__)

# Create routers
timeline_router = APIRouter(prefix="/api/timeline", tags=["timeline"])
commands_router = APIRouter(prefix="/api/commands", tags=["commands"])


# ============================================================================
# Timeline Response Models
# ============================================================================

class TimelineEvent(BaseModel):
    """Timeline event model."""
    id: str
    title: str
    type: str  # 'operation' or 'session'
    start_time: str
    end_time: Optional[str] = None
    operation_id: Optional[str] = None
    operation_name: Optional[str] = None
    status: Optional[str] = None
    metadata: Optional[dict] = None


class TimelineResponse(BaseModel):
    """Timeline response model."""
    events: List[TimelineEvent]
    start_date: str
    end_date: str
    total_operations: int
    total_sessions: int


class NetworkNode(BaseModel):
    """Network diagram node."""
    id: str
    label: str
    type: str  # 'target', 'operation', 'session'
    metadata: Optional[dict] = None


class NetworkEdge(BaseModel):
    """Network diagram edge."""
    from_id: str
    to_id: str
    label: Optional[str] = None
    type: Optional[str] = None


class NetworkDiagramResponse(BaseModel):
    """Network diagram response."""
    nodes: List[NetworkNode]
    edges: List[NetworkEdge]


# ============================================================================
# Timeline Routes
# ============================================================================


@timeline_router.get("/operations", response_model=TimelineResponse)
async def get_operations_timeline(
    operation_id: Optional[str] = Query(None, description="Filter by operation ID")
) -> TimelineResponse:
    """
    Get timeline of operations and sessions.
    
    Args:
        operation_id: Optional operation ID to filter by
        
    Returns:
        TimelineResponse with events
    """
    try:
        settings_store = SettingsStore()
        app_settings = await settings_store.load_settings()
        storage = get_storage(app_settings)
        
        events = []
        operations = await storage.list_operations()
        
        if operation_id:
            operations = [op for op in operations if op.id == operation_id]
            if not operations:
                raise HTTPException(status_code=404, detail=f"Operation {operation_id} not found")
        
        # Get all sessions
        all_sessions = await storage.list_sessions()
        
        for operation in operations:
            # Add operation event
            events.append(TimelineEvent(
                id=operation.id,
                title=operation.name,
                type="operation",
                start_time=operation.created_at.isoformat(),
                end_time=None,
                operation_id=operation.id,
                operation_name=operation.name,
                status=operation.status,
                metadata={"description": operation.description}
            ))
            
            # Add session events for this operation
            op_sessions = [s for s in all_sessions if s.operation_id == operation.id]
            for session in op_sessions:
                events.append(TimelineEvent(
                    id=session.id,
                    title=session.title,
                    type="session",
                    start_time=session.created_at.isoformat(),
                    end_time=session.updated_at.isoformat() if session.updated_at != session.created_at else None,
                    operation_id=operation.id,
                    operation_name=operation.name,
                    status=None,
                    metadata={
                        "tags": session.tags,
                        "targets": session.targets,
                        "tools": session.tools
                    }
                ))
        
        # Sort by start time
        events.sort(key=lambda e: e.start_time)
        
        # Calculate date range
        if events:
            start_date = min(e.start_time for e in events)
            end_date = max(e.start_time for e in events)
        else:
            now = datetime.utcnow().isoformat()
            start_date = now
            end_date = now
        
        return TimelineResponse(
            events=events,
            start_date=start_date,
            end_date=end_date,
            total_operations=len(operations),
            total_sessions=len([e for e in events if e.type == "session"])
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Failed to get operations timeline: {e}")
        raise RedTeamKBError("Failed to get timeline") from e


@timeline_router.get("/network", response_model=NetworkDiagramResponse)
async def get_network_diagram(
    operation_id: Optional[str] = Query(None, description="Filter by operation ID")
) -> NetworkDiagramResponse:
    """
    Get network diagram data showing relationships between operations, sessions, and targets.
    
    Args:
        operation_id: Optional operation ID to filter by
        
    Returns:
        NetworkDiagramResponse with nodes and edges
    """
    try:
        settings_store = SettingsStore()
        app_settings = await settings_store.load_settings()
        storage = get_storage(app_settings)
        
        nodes = []
        edges = []
        target_nodes = {}  # Track unique targets
        
        operations = await storage.list_operations()
        
        if operation_id:
            operations = [op for op in operations if op.id == operation_id]
            if not operations:
                raise HTTPException(status_code=404, detail=f"Operation {operation_id} not found")
        
        # Get all sessions
        all_sessions = await storage.list_sessions()
        
        for operation in operations:
            # Add operation node
            nodes.append(NetworkNode(
                id=operation.id,
                label=operation.name,
                type="operation",
                metadata={"status": operation.status}
            ))
            
            # Add session nodes and edges
            op_sessions = [s for s in all_sessions if s.operation_id == operation.id]
            for session in op_sessions:
                nodes.append(NetworkNode(
                    id=session.id,
                    label=session.title,
                    type="session",
                    metadata={"tools": session.tools, "tags": session.tags}
                ))
                
                # Edge from operation to session
                edges.append(NetworkEdge(
                    from_id=operation.id,
                    to_id=session.id,
                    label="contains",
                    type="operation_session"
                ))
                
                # Add target nodes and edges
                if session.targets:
                    for target in session.targets:
                        target_id = f"target_{target}"
                        if target_id not in target_nodes:
                            target_nodes[target_id] = NetworkNode(
                                id=target_id,
                                label=target,
                                type="target",
                                metadata={}
                            )
                        
                        # Edge from session to target
                        edges.append(NetworkEdge(
                            from_id=session.id,
                            to_id=target_id,
                            label="targets",
                            type="session_target"
                        ))
        
        # Add target nodes
        nodes.extend(target_nodes.values())
        
        return NetworkDiagramResponse(nodes=nodes, edges=edges)
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Failed to get network diagram: {e}")
        raise RedTeamKBError("Failed to get network diagram") from e


@timeline_router.get("/kill-chain/{operation_id}")
async def get_kill_chain_timeline(operation_id: str) -> dict:
    """
    Get kill chain timeline for an operation.
    Shows progression through MITRE ATT&CK kill chain phases.
    
    Args:
        operation_id: Operation ID
        
    Returns:
        Dictionary with kill chain phase data and timeline
    """
    try:
        settings_store = SettingsStore()
        app_settings = await settings_store.load_settings()
        storage = get_storage(app_settings)
        
        # Verify operation exists
        operation = await storage.get_operation(operation_id)
        if not operation:
            raise HTTPException(status_code=404, detail=f"Operation {operation_id} not found")
        
        # Get sessions for this operation
        all_sessions = await storage.list_sessions()
        sessions = [s for s in all_sessions if s.operation_id == operation_id]
        
        kill_chain_phases = [
            "Reconnaissance", "Initial Access", "Execution", "Privilege Escalation",
            "Persistence", "Defense Evasion", "Credential Access", "Discovery",
            "Lateral Movement", "Collection", "Exfiltration", "Impact"
        ]
        
        if not sessions:
            # Return empty kill chain
            return {
                "operation_id": operation_id,
                "operation_name": operation.name,
                "phases": {phase: {"status": "not_started", "sessions": []} for phase in kill_chain_phases},
                "current_phase": None,
                "timeline": []
            }
        
        # Generate insights to get kill chain data
        llm_service = None
        if app_settings.llm_config:
            try:
                llm_service = get_llm_service(app_settings)
            except Exception:
                pass
        
        kill_chain_progress = {}
        timeline_events = []
        
        if llm_service:
            try:
                expert_analysis = await generate_expert_analysis(sessions, llm_service, [operation.name])
                kill_chain_progress = expert_analysis.kill_chain_progress
                
                # Build timeline from sessions
                for session in sessions:
                    timeline_events.append({
                        "session_id": session.id,
                        "session_title": session.title,
                        "timestamp": session.created_at.isoformat(),
                        "tools": session.tools or [],
                        "targets": session.targets or [],
                        "findings": session.findings or []
                    })
            except Exception as e:
                logger.warning(f"Failed to generate expert analysis for kill chain: {e}")
        
        # If no kill chain data, create default structure
        if not kill_chain_progress:
            kill_chain_progress = {phase: "not_started" for phase in kill_chain_phases}
        
        # Build phase data with session assignments
        phases_data = {}
        for phase, status in kill_chain_progress.items():
            phases_data[phase] = {
                "status": status,
                "sessions": []  # Could be enhanced to map sessions to phases
            }
        
        return {
            "operation_id": operation_id,
            "operation_name": operation.name,
            "phases": phases_data,
            "current_phase": None,  # Could be extracted from expert analysis
            "timeline": sorted(timeline_events, key=lambda x: x["timestamp"])
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Failed to get kill chain timeline: {e}")
        raise RedTeamKBError("Failed to get kill chain timeline") from e


# ============================================================================
# Command Analysis Routes
# ============================================================================


class CommandAnalysisResponse(BaseModel):
    """Response model for command analysis."""
    total_commands: int
    unique_commands: int
    command_frequency: Dict[str, int]
    top_commands: List[Dict[str, Union[int, str]]]
    patterns: List[Dict]
    timeline: List[Dict]
    sessions_analyzed: int


@commands_router.get("/analyze")
async def analyze_commands(
    operation_id: Optional[str] = Query(None, description="Filter by operation ID"),
    session_ids: Optional[str] = Query(None, description="Comma-separated session IDs")
) -> CommandAnalysisResponse:
    """
    Analyze commands from sessions.
    
    Args:
        operation_id: Optional operation ID to filter by
        session_ids: Optional comma-separated list of session IDs
        
    Returns:
        CommandAnalysisResponse with frequency, patterns, and timeline
    """
    try:
        settings_store = SettingsStore()
        app_settings = await settings_store.load_settings()
        storage = get_storage(app_settings)
        
        # Get sessions to analyze
        sessions_to_analyze = []
        
        if session_ids:
            # Analyze specific sessions
            session_id_list = [s.strip() for s in session_ids.split(',')]
            for session_id in session_id_list:
                session = await storage.get_session(session_id)
                if session:
                    sessions_to_analyze.append(session)
        elif operation_id:
            # Analyze all sessions in operation
            operation = await storage.get_operation(operation_id)
            if not operation:
                raise HTTPException(status_code=404, detail=f"Operation {operation_id} not found")
            
            all_sessions = await storage.list_sessions()
            sessions_to_analyze = [s for s in all_sessions if s.operation_id == operation_id]
        else:
            # Analyze all sessions
            sessions_to_analyze = await storage.list_sessions()
        
        if not sessions_to_analyze:
            raise HTTPException(
                status_code=404,
                detail="No sessions found to analyze"
            )
        
        # Extract commands from all sessions
        all_commands = []
        for session in sessions_to_analyze:
            try:
                commands = extract_commands(session.terminal_content, session.id)
                all_commands.extend(commands)
            except Exception as e:
                logger.warning(f"Failed to extract commands from session {session.id}: {e}")
                continue
        
        # Analyze commands
        command_frequency = analyze_command_frequency(all_commands)
        patterns = detect_command_patterns(all_commands, min_sequence_length=2)
        timeline = build_command_timeline(all_commands)
        
        # Get top commands
        top_commands = sorted(
            [
                {"command": cmd, "count": count}
                for cmd, count in command_frequency.items()
            ],
            key=lambda x: x["count"],
            reverse=True
        )[:20]  # Top 20
        
        return CommandAnalysisResponse(
            total_commands=len(all_commands),
            unique_commands=len(command_frequency),
            command_frequency=command_frequency,
            top_commands=top_commands,
            patterns=patterns,
            timeline=timeline,
            sessions_analyzed=len(sessions_to_analyze)
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Failed to analyze commands: {e}")
        raise RedTeamKBError("Failed to analyze commands") from e


@commands_router.get("/session/{session_id}")
async def get_session_commands(session_id: str) -> dict:
    """
    Extract and return commands from a specific session.
    
    Args:
        session_id: Session ID
        
    Returns:
        Dictionary with extracted commands
    """
    try:
        settings_store = SettingsStore()
        app_settings = await settings_store.load_settings()
        storage = get_storage(app_settings)
        
        session = await storage.get_session(session_id)
        if not session:
            raise HTTPException(status_code=404, detail=f"Session {session_id} not found")
        
        commands = extract_commands(session.terminal_content, session_id)
        
        return {
            "session_id": session_id,
            "session_title": session.title,
            "total_commands": len(commands),
            "commands": [
                {
                    "command": cmd.command,
                    "base_command": cmd.base_command,
                    "arguments": cmd.arguments,
                    "line_number": cmd.line_number,
                    "context": cmd.context
                }
                for cmd in commands
            ]
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Failed to extract commands from session: {e}")
        raise RedTeamKBError("Failed to extract commands") from e


@commands_router.get("/frequency")
async def get_command_frequency(
    operation_id: Optional[str] = Query(None, description="Filter by operation ID")
) -> dict:
    """
    Get command frequency statistics.
    
    Args:
        operation_id: Optional operation ID to filter by
        
    Returns:
        Dictionary with frequency data
    """
    try:
        settings_store = SettingsStore()
        app_settings = await settings_store.load_settings()
        storage = get_storage(app_settings)
        
        # Get sessions
        if operation_id:
            operation = await storage.get_operation(operation_id)
            if not operation:
                raise HTTPException(status_code=404, detail=f"Operation {operation_id} not found")
            all_sessions = await storage.list_sessions()
            sessions = [s for s in all_sessions if s.operation_id == operation_id]
        else:
            sessions = await storage.list_sessions()
        
        # Extract and analyze commands
        all_commands = []
        for session in sessions:
            try:
                commands = extract_commands(session.terminal_content, session.id)
                all_commands.extend(commands)
            except Exception:
                continue
        
        frequency = analyze_command_frequency(all_commands)
        
        return {
            "frequency": frequency,
            "total_commands": len(all_commands),
            "unique_commands": len(frequency)
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Failed to get command frequency: {e}")
        raise RedTeamKBError("Failed to get command frequency") from e


@commands_router.get("/patterns")
async def get_command_patterns(
    operation_id: Optional[str] = Query(None, description="Filter by operation ID"),
    min_length: int = Query(2, description="Minimum pattern length")
) -> dict:
    """
    Detect command patterns/sequences.
    
    Args:
        operation_id: Optional operation ID to filter by
        min_length: Minimum sequence length to detect
        
    Returns:
        Dictionary with detected patterns
    """
    try:
        settings_store = SettingsStore()
        app_settings = await settings_store.load_settings()
        storage = get_storage(app_settings)
        
        # Get sessions
        if operation_id:
            operation = await storage.get_operation(operation_id)
            if not operation:
                raise HTTPException(status_code=404, detail=f"Operation {operation_id} not found")
            all_sessions = await storage.list_sessions()
            sessions = [s for s in all_sessions if s.operation_id == operation_id]
        else:
            sessions = await storage.list_sessions()
        
        # Extract and analyze commands
        all_commands = []
        for session in sessions:
            try:
                commands = extract_commands(session.terminal_content, session.id)
                all_commands.extend(commands)
            except Exception:
                continue
        
        patterns = detect_command_patterns(all_commands, min_sequence_length=min_length)
        
        return {
            "patterns": patterns,
            "total_patterns": len(patterns)
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Failed to detect command patterns: {e}")
        raise RedTeamKBError("Failed to detect command patterns") from e



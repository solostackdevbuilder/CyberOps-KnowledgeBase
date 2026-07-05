"""
Services for red team edition.
Consolidated from insights_service, expert_analysis_service, and extraction_service.

Generic analytics functions (extract_targets, extract_tools, etc.) have been moved
to app.core.services.analytics and are re-exported here for backward compatibility.
"""

import logging
from collections import Counter
from datetime import datetime
from typing import Dict, List, Literal, Optional

from app.modules.red_team.models import GeneralInsights
from app.modules.red_team.models import Session

logger = logging.getLogger(__name__)

# Re-export generic analytics functions from core for backward compatibility
from app.core.services.analytics import (  # noqa: F401
    extract_targets,
    extract_tools,
    extract_findings,
    build_timeline,
    summarize_sessions_for_llm,
    generate_general_insights,
)




# ============================================================================
# Services from app/services/expert_analysis_service.py
# ============================================================================

"""
Service for generating expert analysis using LLM.
"""
import asyncio
import json
import logging
from datetime import datetime
from typing import List, Optional

from app.modules.red_team.models import ExpertAnalysis, NextStep
from app.modules.red_team.models import Session
from app.modules.red_team.prompts import EXPERT_ANALYSIS_PROMPT
from app.core.services.base_llm import BaseLLM
# summarize_sessions_for_llm is defined above in this file

logger = logging.getLogger(__name__)

# Standard kill chain phases
KILL_CHAIN_PHASES = [
    "Reconnaissance",
    "Initial Access",
    "Execution",
    "Privilege Escalation",
    "Persistence",
    "Defense Evasion",
    "Credential Access",
    "Discovery",
    "Lateral Movement",
    "Collection",
    "Exfiltration",
    "Impact"
]


async def generate_expert_analysis(
    sessions: List[Session],
    llm_service: BaseLLM,
    operation_names: Optional[List[str]] = None
) -> ExpertAnalysis:
    """
    Generate expert analysis using LLM.
    
    Args:
        sessions: List of session objects to analyze
        llm_service: LLM service instance
        operation_names: Optional list of operation names for context
        
    Returns:
        ExpertAnalysis object with AI-powered assessment
        
    Raises:
        RuntimeError: If LLM call fails or response cannot be parsed
    """
    logger.info(f"Generating expert analysis from {len(sessions)} sessions")
    
    if not sessions:
        # Return empty analysis if no sessions
        return create_empty_analysis("No sessions available for analysis.")
    
    try:
        # Build context from sessions
        context = summarize_sessions_for_llm(sessions)
        
        # Add operation context if multiple operations
        if operation_names and len(operation_names) > 1:
            context = f"=== ANALYZING MULTIPLE OPERATIONS ===\nOperations: {', '.join(operation_names)}\n\n{context}"
        elif operation_names and len(operation_names) == 1:
            context = f"=== OPERATION: {operation_names[0]} ===\n\n{context}"
        
        # Build the question with the prompt instructions
        question = f"""{EXPERT_ANALYSIS_PROMPT}

Please analyze the session data provided in the context and return your analysis as JSON following the format specified above."""
        
        # Call LLM
        logger.info("Calling LLM for expert analysis...")
        start_time = datetime.utcnow()
        
        # Use the query method with prompt as question and session data as context
        response_text = await llm_service.query(
            question=question,
            context=context,
            scope="all" if operation_names and len(operation_names) > 1 else "single",
            operation_name=operation_names[0] if operation_names and len(operation_names) == 1 else None
        )
        
        elapsed = (datetime.utcnow() - start_time).total_seconds()
        logger.info(f"LLM response received in {elapsed:.2f} seconds")
        
        # Parse JSON response
        analysis_data = _parse_llm_response(response_text)
        
        # Validate and build ExpertAnalysis
        expert_analysis = await _build_expert_analysis(analysis_data, sessions)
        
        logger.info(
            f"Expert analysis generated: phase={expert_analysis.current_phase}, "
            f"confidence={expert_analysis.phase_confidence}"
        )
        
        return expert_analysis
        
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse LLM response as JSON: {e}")
        logger.debug(f"Response text: {response_text[:500] if 'response_text' in locals() else 'N/A'}")
        return create_empty_analysis(f"Failed to parse LLM response: {str(e)}")
    except Exception as e:
        logger.error(f"Failed to generate expert analysis: {e}", exc_info=True)
        return create_empty_analysis(f"LLM analysis failed: {str(e)}")


def _parse_llm_response(response_text: str) -> dict:
    """
    Parse LLM response text into JSON dictionary.
    
    Args:
        response_text: Raw response from LLM
        
    Returns:
        Parsed JSON dictionary
        
    Raises:
        json.JSONDecodeError: If response cannot be parsed
    """
    # Clean up response text
    response_text = response_text.strip()
    
    # Try to extract JSON from markdown code blocks if present
    if response_text.startswith("```"):
        # Extract JSON from code block
        lines = response_text.split("\n")
        json_lines = []
        in_json = False
        for line in lines:
            if line.strip().startswith("```"):
                if in_json:
                    break
                in_json = True
                # Skip language identifier if present
                if line.strip() != "```" and line.strip() != "```json":
                    continue
                continue
            if in_json:
                json_lines.append(line)
        response_text = "\n".join(json_lines)
    
    # Parse JSON
    try:
        return json.loads(response_text)
    except json.JSONDecodeError:
        # Try to find JSON object in the text
        start_idx = response_text.find("{")
        end_idx = response_text.rfind("}")
        if start_idx >= 0 and end_idx > start_idx:
            json_str = response_text[start_idx:end_idx + 1]
            return json.loads(json_str)
        raise


async def _build_expert_analysis(analysis_data: dict, sessions: List[Session]) -> ExpertAnalysis:
    """
    Build ExpertAnalysis object from parsed LLM response.
    
    Args:
        analysis_data: Parsed JSON from LLM
        sessions: List of sessions (for validation)
        
    Returns:
        ExpertAnalysis object
    """
    # Validate kill chain progress
    kill_chain_progress = {}
    for phase in KILL_CHAIN_PHASES:
        status = analysis_data.get("kill_chain_progress", {}).get(phase, "next")
        if status not in ["completed", "current", "next"]:
            status = "next"
        kill_chain_progress[phase] = status
    
    # Validate phase confidence
    phase_confidence = analysis_data.get("phase_confidence", "Medium")
    if phase_confidence not in ["High", "Medium", "Low"]:
        phase_confidence = "Medium"
    
    # Validate current phase
    current_phase = analysis_data.get("current_phase", "Reconnaissance")
    if current_phase not in KILL_CHAIN_PHASES:
        # Try to find a close match
        current_phase_lower = current_phase.lower()
        for phase in KILL_CHAIN_PHASES:
            if phase.lower() in current_phase_lower or current_phase_lower in phase.lower():
                current_phase = phase
                break
        else:
            current_phase = "Reconnaissance"
    
    # Parse next steps
    next_steps = []
    next_steps_data = analysis_data.get("next_steps", [])
    if isinstance(next_steps_data, list):
        for step_data in next_steps_data:
            if isinstance(step_data, dict):
                priority = step_data.get("priority", "Medium")
                if priority not in ["High", "Medium", "Low"]:
                    priority = "Medium"
                next_steps.append(NextStep(
                    step=step_data.get("step", ""),
                    priority=priority,
                    reasoning=step_data.get("reasoning", "")
                ))
    
    # Validate evidence sessions
    evidence_sessions = analysis_data.get("evidence_sessions", [])
    if isinstance(evidence_sessions, list):
        # Filter to only include session IDs that actually exist
        session_ids = {s.id for s in sessions}
        evidence_sessions = [sid for sid in evidence_sessions if sid in session_ids]
    else:
        evidence_sessions = []
    
    # Analyze detection strategies
    detection_risk_assessment = None
    recommended_detection_strategies = []
    detection_coverage_gaps = []
    
    try:
        from app.modules.red_team.detection_strategies import get_detection_strategy_service
        from app.core.storage.storage_factory import get_storage
        from app.core.storage.settings_store import SettingsStore
        
        strategy_service = get_detection_strategy_service()
        
        # Get all techniques from FAA items
        all_techniques = set()
        all_strategy_ids = set()
        
        # Try to get storage to access FAA items
        try:
            settings_store = SettingsStore()
            app_settings = await settings_store.load_settings()
            storage = get_storage(app_settings)
            
            for session in sessions:
                faa_items = await storage.list_faa_items(session.id)
                for item in faa_items:
                    if item.mitre_technique:
                        technique_id = strategy_service.extract_technique_id(item.mitre_technique)
                        if technique_id:
                            all_techniques.add(technique_id)
                            if item.detection_strategy_ids:
                                all_strategy_ids.update(item.detection_strategy_ids)
                            else:
                                # Check if strategies exist
                                strategies = strategy_service.get_strategies_for_technique(technique_id)
                                if strategies:
                                    all_strategy_ids.update([s.id for s in strategies])
        except Exception as e:
            logger.warning(f"Could not load FAA items for detection analysis: {e}")
        
        # Calculate coverage
        if all_techniques:
            techniques_with_strategies = set()
            for technique_id in all_techniques:
                strategies = strategy_service.get_strategies_for_technique(technique_id)
                if strategies:
                    techniques_with_strategies.add(technique_id)
                    all_strategy_ids.update([s.id for s in strategies])
                else:
                    detection_coverage_gaps.append(technique_id)
            
            coverage_percentage = (len(techniques_with_strategies) / len(all_techniques) * 100) if all_techniques else 0
            
            # Generate detection risk assessment
            if coverage_percentage >= 80:
                detection_risk_assessment = f"High detection risk: {coverage_percentage:.0f}% of techniques have detection strategies. Defenders have strong visibility."
            elif coverage_percentage >= 50:
                detection_risk_assessment = f"Medium detection risk: {coverage_percentage:.0f}% of techniques have detection strategies. Some activities may go undetected."
            else:
                detection_risk_assessment = f"Low detection risk: Only {coverage_percentage:.0f}% of techniques have detection strategies. Limited defender visibility."
            
            # Get strategy details
            recommended_detection_strategies = list(all_strategy_ids)
    except Exception as e:
        logger.warning(f"Failed to analyze detection strategies: {e}")
    
    # Build ExpertAnalysis
    return ExpertAnalysis(
        current_phase=current_phase,
        phase_confidence=phase_confidence,
        kill_chain_progress=kill_chain_progress,
        progress_summary=analysis_data.get("progress_summary", "Analysis in progress."),
        gaps_identified=analysis_data.get("gaps_identified", []),
        recommendations=analysis_data.get("recommendations", []),
        next_steps=next_steps,
        risk_assessment=analysis_data.get("risk_assessment", "Risk assessment pending."),
        detection_risk_assessment=detection_risk_assessment,
        recommended_detection_strategies=recommended_detection_strategies,
        detection_coverage_gaps=detection_coverage_gaps,
        evidence_sessions=evidence_sessions,
        generated_at=datetime.utcnow()
    )


def create_empty_analysis(error_message: str) -> ExpertAnalysis:
    """
    Create an empty ExpertAnalysis with error message.
    
    Args:
        error_message: Error message to include in analysis
        
    Returns:
        ExpertAnalysis object with default values
    """
    kill_chain_progress = {phase: "next" for phase in KILL_CHAIN_PHASES}
    
    return ExpertAnalysis(
        current_phase="Reconnaissance",
        phase_confidence="Low",
        kill_chain_progress=kill_chain_progress,
        progress_summary=error_message,
        gaps_identified=[],
        recommendations=[],
        next_steps=[],
        risk_assessment="Unable to assess risk due to analysis failure.",
        detection_risk_assessment=None,
        recommended_detection_strategies=[],
        detection_coverage_gaps=[],
        evidence_sessions=[],
        generated_at=datetime.utcnow()
    )




# ============================================================================
# Services from app/services/extraction_service.py
# ============================================================================

"""
Service for extracting metadata from terminal content using Claude API.
"""
import asyncio
import json
from typing import Dict, List

from anthropic import Anthropic, APIError

from app.config import settings


class ExtractionService:
    """Service for extracting metadata from terminal content using Claude API."""
    
    def __init__(self):
        """
        Initialize extraction service.
        
        Raises:
            ValueError: If API key is not configured
        """
        if not settings.anthropic_api_key or settings.anthropic_api_key == "your-key-here":
            raise ValueError(
                "ANTHROPIC_API_KEY is not configured. Please set it in your .env file."
            )
        self.client = Anthropic(api_key=settings.anthropic_api_key)
    
    async def extract_metadata(self, terminal_content: str) -> Dict[str, List[str]]:
        """
        Extract metadata from terminal content using Claude API.
        
        Extracts:
        - targets: IP addresses, domains, hostnames that were scanned/attacked
        - tools: Security tools that were used (nmap, metasploit, etc)
        - findings: Key discoveries, vulnerabilities, or important results
        
        Args:
            terminal_content: Terminal/command-line session content
            
        Returns:
            Dictionary with keys: targets, tools, findings (each is a list of strings)
            
        Raises:
            RuntimeError: If Claude API call fails
        """
        try:
            system_prompt = """Analyze this terminal/command-line session and extract:

1. Targets: IP addresses, domains, hostnames that were scanned/attacked

2. Tools: Security tools that were used (nmap, metasploit, etc)

3. Findings: Key discoveries, vulnerabilities, or important results

Return as JSON: {"targets": [], "tools": [], "findings": []}

Be concise and accurate. Only include items that are clearly present in the terminal content."""
            
            user_message = f"""Terminal session content:

{terminal_content}

---

Extract the targets, tools, and findings from this session. Return only valid JSON with the structure:
{{"targets": [], "tools": [], "findings": []}}"""
            
            # Call Claude API (run in thread pool since client is synchronous)
            loop = asyncio.get_event_loop()
            message = await loop.run_in_executor(
                None,
                lambda: self.client.messages.create(
                    model="claude-sonnet-4-5-20250929",
                    max_tokens=2048,
                    system=system_prompt,
                    messages=[
                        {
                            "role": "user",
                            "content": user_message
                        }
                    ]
                )
            )
            
            # Extract response text
            response_text = ""
            for content_block in message.content:
                if content_block.type == "text":
                    response_text += content_block.text
            
            # Parse JSON response
            try:
                # Try to extract JSON from the response (might be wrapped in markdown code blocks)
                response_text = response_text.strip()
                if response_text.startswith("```"):
                    # Extract JSON from code block
                    lines = response_text.split("\n")
                    json_lines = []
                    in_json = False
                    for line in lines:
                        if line.strip().startswith("```"):
                            if in_json:
                                break
                            in_json = True
                            continue
                        if in_json:
                            json_lines.append(line)
                    response_text = "\n".join(json_lines)
                
                extracted_data = json.loads(response_text)
                
                # Ensure all required keys exist
                result = {
                    "targets": extracted_data.get("targets", []),
                    "tools": extracted_data.get("tools", []),
                    "findings": extracted_data.get("findings", [])
                }
                
                # Validate types
                if not isinstance(result["targets"], list):
                    result["targets"] = []
                if not isinstance(result["tools"], list):
                    result["tools"] = []
                if not isinstance(result["findings"], list):
                    result["findings"] = []
                
                # Convert all items to strings
                result["targets"] = [str(item) for item in result["targets"]]
                result["tools"] = [str(item) for item in result["tools"]]
                result["findings"] = [str(item) for item in result["findings"]]
                
                return result
                
            except json.JSONDecodeError as e:
                raise RuntimeError(f"Failed to parse Claude response as JSON: {e}. Response: {response_text[:200]}")
            
        except APIError as e:
            raise RuntimeError(f"Claude API error: {e.message}") from e
        except Exception as e:
            raise RuntimeError(f"Failed to extract metadata: {e}") from e


# ============================================================================
# FAA (Findings and Actions) Services
# ============================================================================

from app.modules.red_team.models import FAAItem, FAAItemCreate
from app.modules.red_team.prompts import FAA_ANALYSIS_PROMPT
from app.core.storage.base_store import BaseStore
from uuid import uuid4

FAA_FINDINGS_EXPORT_COLUMNS = [
    "Title",
    "Finding",
    "Applications",
    "Devices",
    "Finding Source",
    "Effort",
    "Risk",
    "Originating System",
    "Mitigating Controls",
    "Recommended Remediation",
    "Fiscal Year",
    "ISPS Control",
    "Additional Controls",
    "Stakeholders",
    "Target Remediation Date",
    "Remediation Plan Summary",
    "Remediation Plan Updates",
    "Remediated Date",
    "Comments Subject",
    "Comments Details",
    "Tags",
    "Override Assignee (EMAIL)",
    "Override Division",
    "Override Finding Rating",
    "Override Generated From",
    "Override Mandated Date",
    "Test Name",
]

FAA_ACTIONS_EXPORT_COLUMNS = [
    "Op",
    "Title",
    "Description",
    "RCE Method",
    "Asset Identification",
    "Attack Narrative",
    "Internal",
    "Internally Developed",
    "Default Credentials",
    "Cloud",
    "Difficulty Index",
    "Target Type",
    "Quantity",
    "Performed At",
    "Op Objective",
    "Segment",
    "MITRE Attack Tactic",
    "MITRE Attack Technique",
    "MITRE Attack Subtechnique",
    "User",
    "Blue Team Viewed",
    "Successful?",
    "Goal?",
    "Blue Telemetry Available?",
    "Blue Detection Implemented?",
    "Red Endpoint Protection Observed?",
    "Blue Detected?",
    "Red Detected?",
    "Blue Detectable?",
]


def _faa_finding_title(content: str, max_len: int = 200) -> str:
    if not content:
        return ""
    line = content.strip().split("\n", 1)[0].strip()
    if len(line) > max_len:
        return line[: max_len - 1] + "\u2026"
    return line


# Leading characters that Excel/Google Sheets interpret as formula starters
# when opening a CSV. CSV injection reference:
# https://owasp.org/www-community/attacks/CSV_Injection
_CSV_FORMULA_STARTERS = ("=", "+", "-", "@", "|", "\t", "\r")


def _csv_safe(value: str) -> str:
    """Neutralize CSV formula injection by prefixing risky leading chars with "'".

    Values authored by users (FAA item content, notes, targets, MITRE tactic
    strings, etc.) flow into the FAA CSV export. A single spreadsheet open in
    Excel or Google Sheets will execute `=IMPORTXML(...)`, `=HYPERLINK(...)`,
    or `=cmd|'/c calc'!A0` unless the leading character is escaped. csv.writer
    with QUOTE_ALL wraps values in quotes but does not address formula
    interpretation, so this helper is the actual defense.
    """
    if not value:
        return value
    if value.startswith(_CSV_FORMULA_STARTERS):
        return "'" + value
    return value


def _csv_safe_row(row: List[str]) -> List[str]:
    """Apply _csv_safe to every cell in a row."""
    return [_csv_safe(cell) for cell in row]


def _faa_action_row(session: Optional[Session], item: FAAItem) -> List[str]:
    """
    One CSV data row using exactly FAA_ACTIONS_EXPORT_COLUMNS (in order).
    Unknown / unavailable values are empty strings; columns are never omitted.
    """
    op_name = ""
    targets = ""
    if session:
        if session.targets:
            targets = "; ".join(session.targets)

    mitre_tactic = item.mitre_tactic or ""
    mitre_technique = ""
    mitre_subtechnique = ""
    if item.mitre_technique:
        # e.g. "T1059.001 - Command and Scripting Interpreter: PowerShell"
        parts = item.mitre_technique.split(".")
        if len(parts) >= 2:
            mitre_technique = parts[0]
            mitre_subtechnique = item.mitre_technique
        else:
            mitre_technique = item.mitre_technique

    timestamp_str = (
        item.timestamp.isoformat()
        if isinstance(item.timestamp, datetime)
        else str(item.timestamp)
    )

    row: List[str] = [
        op_name,
        _faa_finding_title(item.content or ""),
        item.content or "",
        "",
        targets,
        item.output or "",
        "",
        "",
        "",
        "",
        "",
        "",
        "",
        timestamp_str,
        "",
        "",
        mitre_tactic,
        mitre_technique,
        mitre_subtechnique,
        "",
        "",
        "",
        "",
        "",
        "",
        "",
        "",
        "",
        "",
    ]
    expected = len(FAA_ACTIONS_EXPORT_COLUMNS)
    if len(row) != expected:
        raise ValueError(f"FAA action row has {len(row)} fields, expected {expected}")
    return _csv_safe_row(row)


def _faa_export_row(session: Optional[Session], item: FAAItem) -> List[str]:
    """
    One CSV data row using exactly FAA_FINDINGS_EXPORT_COLUMNS (in order).
    Unknown / unavailable values are empty strings; columns are never omitted.
    """
    targets = ""
    tags = ""
    if session:
        if session.targets:
            targets = "; ".join(session.targets)
        if session.tags:
            tags = "; ".join(session.tags)
    strategies = (
        "; ".join(item.detection_strategy_ids) if item.detection_strategy_ids else ""
    )
    row: List[str] = [
        _faa_finding_title(item.content or ""),
        item.content or "",
        "",
        "",
        str(item.source) if item.source is not None else "",
        "",
        item.severity or "",
        targets,
        strategies,
        item.notes or "",
        "",
        "",
        "",
        "",
        "",
        "",
        "",
        "",
        "",
        item.output or "",
        tags,
        "",
        "",
        "",
        "",
        "",
        item.mitre_technique or "",
    ]
    expected = len(FAA_FINDINGS_EXPORT_COLUMNS)
    if len(row) != expected:
        raise ValueError(f"FAA export row has {len(row)} fields, expected {expected}")
    return _csv_safe_row(row)


def _faa_csv_writer(output):
    import csv

    return csv.writer(
        output,
        quoting=csv.QUOTE_ALL,
        lineterminator="\n",
    )


async def analyze_session_for_faa(
    session_id: str,
    storage: BaseStore,
    llm_service: BaseLLM
) -> List[FAAItem]:
    """
    Analyze a session and classify activities as actions or findings.
    
    Args:
        session_id: Session ID to analyze
        storage: Storage instance to load session data
        llm_service: LLM service instance
        
    Returns:
        List of FAAItem objects with classifications
    """
    logger.info(f"Analyzing session {session_id} for FAA classification")
    
    try:
        # Load session with terminal content
        session = await storage.get_session(session_id)
        if not session:
            raise ValueError(f"Session {session_id} not found")
        
        # Build screenshot OCR text
        screenshot_text = ""
        if session.screenshot_extractions:
            screenshot_texts = []
            for extraction in session.screenshot_extractions:
                if extraction.extracted_text:
                    screenshot_texts.append(f"[{extraction.filename}]: {extraction.extracted_text}")
            screenshot_text = "\n".join(screenshot_texts)
        
        # Prepare prompt with session data
        prompt = FAA_ANALYSIS_PROMPT.format(
            terminal_content=session.terminal_content[:50000],  # Limit to 50k chars
            screenshot_text=screenshot_text[:50000] if screenshot_text else "No screenshot text available"
        )
        
        # Call LLM
        logger.info("Calling LLM for FAA analysis...")
        start_time = datetime.utcnow()
        
        response_text = await llm_service.query(
            question=prompt,
            context="",  # Context is already in the prompt
            scope="single",
            operation_name=None
        )
        
        elapsed = (datetime.utcnow() - start_time).total_seconds()
        logger.info(f"LLM response received in {elapsed:.2f} seconds")
        
        # Parse JSON response
        try:
            # Try to extract JSON from response (might have markdown code blocks)
            response_text = response_text.strip()
            if response_text.startswith("```"):
                # Remove markdown code blocks
                lines = response_text.split("\n")
                response_text = "\n".join(lines[1:-1]) if len(lines) > 2 else response_text
            elif response_text.startswith("```json"):
                lines = response_text.split("\n")
                response_text = "\n".join(lines[1:-1]) if len(lines) > 2 else response_text
            
            analysis_data = json.loads(response_text)
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse LLM response as JSON: {e}")
            logger.error(f"Response text: {response_text[:500]}")
            raise RuntimeError(f"LLM returned invalid JSON: {e}")
        
        # Build FAA items from LLM response
        faa_items = []
        now = datetime.utcnow()
        
        if "items" not in analysis_data:
            logger.warning("LLM response missing 'items' field")
            return faa_items
        
        for item_data in analysis_data["items"]:
            try:
                # Determine timestamp (use session created_at as fallback)
                timestamp = session.created_at
                if "timestamp" in item_data:
                    try:
                        timestamp = datetime.fromisoformat(item_data["timestamp"])
                    except (ValueError, TypeError):
                        pass
                
                # Determine source
                source = item_data.get("source", "terminal")
                if source not in ["terminal", "screenshot", "manual"]:
                    source = "terminal"
                
                # Get confidence score
                confidence_score = float(item_data.get("confidence_score", 0.7))
                confidence_score = max(0.0, min(1.0, confidence_score))  # Clamp to 0-1
                
                # Extract detection strategies for the technique
                detection_strategy_ids = []
                mitre_technique = item_data.get("mitre_technique")
                if mitre_technique:
                    try:
                        from app.modules.red_team.detection_strategies import get_detection_strategy_service
                        strategy_service = get_detection_strategy_service()
                        technique_id = strategy_service.extract_technique_id(mitre_technique)
                        if technique_id:
                            strategies = strategy_service.get_strategies_for_technique(technique_id)
                            detection_strategy_ids = [s.id for s in strategies]
                    except Exception as e:
                        logger.warning(f"Failed to link detection strategies for technique {mitre_technique}: {e}")
                
                # Create FAA item
                faa_item = FAAItem(
                    id=str(uuid4()),
                    session_id=session_id,
                    classification=item_data.get("classification", "action"),
                    content=item_data.get("content", "Unknown activity"),
                    output=item_data.get("output"),
                    mitre_technique=mitre_technique,
                    mitre_tactic=item_data.get("mitre_tactic"),
                    detection_strategy_ids=detection_strategy_ids,
                    severity=item_data.get("severity") if item_data.get("classification") == "finding" else None,
                    timestamp=timestamp,
                    source=source,
                    confidence_score=confidence_score,
                    manually_corrected=False,
                    notes=item_data.get("notes"),
                    created_at=now,
                    updated_at=now
                )
                
                faa_items.append(faa_item)
            except Exception as e:
                logger.warning(f"Failed to create FAA item from LLM response: {e}")
                continue
        
        logger.info(f"Generated {len(faa_items)} FAA items from analysis")
        return faa_items
        
    except Exception as e:
        logger.error(f"Failed to analyze session for FAA: {e}")
        raise RuntimeError(f"FAA analysis failed: {e}") from e


async def classify_single_activity(
    content: str,
    context: str,
    llm_service: BaseLLM
) -> FAAItem:
    """
    Classify a single command/activity.
    
    Args:
        content: Activity description
        context: Additional context
        llm_service: LLM service instance
        
    Returns:
        FAAItem object with classification
    """
    logger.info(f"Classifying single activity: {content[:50]}...")
    
    try:
        # Build a simplified prompt for single activity
        prompt = f"""Classify this red team activity as either "action" or "finding":

Activity: {content}
Context: {context}

Return JSON:
{{
  "classification": "action|finding",
  "mitre_technique": "T#### - Technique Name or null",
  "mitre_tactic": "Tactic Name or null",
  "severity": "critical|high|medium|low|null",
  "confidence_score": 0.0-1.0
}}

Return ONLY valid JSON."""
        
        # Call LLM
        response_text = await llm_service.query(
            question=prompt,
            context="",
            scope="single",
            operation_name=None
        )
        
        # Parse response
        response_text = response_text.strip()
        if response_text.startswith("```"):
            lines = response_text.split("\n")
            response_text = "\n".join(lines[1:-1]) if len(lines) > 2 else response_text
        
        analysis_data = json.loads(response_text)
        
        # Create FAA item (without session_id - caller should set it)
        now = datetime.utcnow()
        faa_item = FAAItem(
            id=str(uuid4()),
            session_id="",  # Caller should set this
            classification=analysis_data.get("classification", "action"),
            content=content,
            output=None,
            mitre_technique=analysis_data.get("mitre_technique"),
            mitre_tactic=analysis_data.get("mitre_tactic"),
            severity=analysis_data.get("severity") if analysis_data.get("classification") == "finding" else None,
            timestamp=now,
            source="manual",
            confidence_score=float(analysis_data.get("confidence_score", 0.8)),
            manually_corrected=False,
            notes=None,
            created_at=now,
            updated_at=now
        )
        
        return faa_item
        
    except Exception as e:
        logger.error(f"Failed to classify single activity: {e}")
        raise RuntimeError(f"Activity classification failed: {e}") from e


async def export_operation_faa_csv(
    operation_id: str,
    storage: BaseStore,
    classification: Optional[Literal["finding", "action"]] = None,
) -> str:
    """
    Export FAA items from an operation to CSV format.

    Every row uses the same fixed column set (FAA_FINDINGS_EXPORT_COLUMNS). Empty
    values are written as empty quoted fields so columns are never dropped.

    Args:
        operation_id: Operation ID to export
        storage: Storage instance
        classification: If set, include only findings or only actions. If None,
            export all items.

    Returns:
        CSV string with FAA items from all sessions in the operation
    """
    logger.info(
        f"Exporting FAA items for operation {operation_id} (classification={classification!r})"
    )

    try:
        # Get operation
        operation = await storage.get_operation(operation_id)
        if not operation:
            raise ValueError(f"Operation {operation_id} not found")

        # Get all sessions for the operation
        all_faa_items = []
        session_map = {}  # Map session_id to session for operator info

        for session_id in operation.session_ids:
            session = await storage.get_session(session_id)
            if session:
                session_map[session_id] = session
                # Get all FAA items for this session
                faa_items = await storage.list_faa_items(session_id)
                all_faa_items.extend(faa_items)

        if classification:
            all_faa_items = [i for i in all_faa_items if i.classification == classification]

        import io

        output = io.StringIO()
        writer = _faa_csv_writer(output)

        if classification == "action":
            writer.writerow(FAA_ACTIONS_EXPORT_COLUMNS)
            for item in all_faa_items:
                sess = session_map.get(item.session_id)
                writer.writerow(_faa_action_row(sess, item))
        else:
            writer.writerow(FAA_FINDINGS_EXPORT_COLUMNS)
            for item in all_faa_items:
                sess = session_map.get(item.session_id)
                writer.writerow(_faa_export_row(sess, item))

        csv_string = output.getvalue()
        output.close()

        logger.info(f"Exported {len(all_faa_items)} FAA items to CSV")
        return csv_string

    except Exception as e:
        logger.error(f"Failed to export FAA CSV: {e}")
        raise RuntimeError(f"FAA export failed: {e}") from e


async def export_session_faa_csv(
    session_id: str,
    storage: BaseStore,
    classification: Optional[Literal["finding", "action"]] = None,
) -> str:
    """
    Export FAA items from a single session to CSV format.

    Findings use FAA_FINDINGS_EXPORT_COLUMNS; actions use FAA_ACTIONS_EXPORT_COLUMNS.
    Empty values are written as empty quoted fields so columns are never dropped.

    Args:
        session_id: Session ID to export
        storage: Storage instance
        classification: If set, include only findings or only actions. If None,
            export all items using the findings column layout.

    Returns:
        CSV string with FAA items from the session
    """
    logger.info(
        f"Exporting FAA items for session {session_id} (classification={classification!r})"
    )

    try:
        # Get session
        session = await storage.get_session(session_id)
        if not session:
            raise ValueError(f"Session {session_id} not found")

        # Get all FAA items for this session
        faa_items = await storage.list_faa_items(session_id)

        if classification:
            faa_items = [i for i in faa_items if i.classification == classification]

        import io

        output = io.StringIO()
        writer = _faa_csv_writer(output)

        if classification == "action":
            writer.writerow(FAA_ACTIONS_EXPORT_COLUMNS)
            for item in faa_items:
                writer.writerow(_faa_action_row(session, item))
        else:
            writer.writerow(FAA_FINDINGS_EXPORT_COLUMNS)
            for item in faa_items:
                writer.writerow(_faa_export_row(session, item))

        csv_string = output.getvalue()
        output.close()

        logger.info(f"Exported {len(faa_items)} FAA items to CSV")
        return csv_string

    except Exception as e:
        logger.error(f"Failed to export session FAA CSV: {e}")
        raise RuntimeError(f"FAA export failed: {e}") from e




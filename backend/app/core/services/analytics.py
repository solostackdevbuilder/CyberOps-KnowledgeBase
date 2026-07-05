"""
Core analytics services.
Generic functions for extracting insights from sessions.
These are platform-level utilities used by all teams.
"""
import logging
from collections import Counter
from datetime import datetime
from typing import Dict, List

from app.core.models import GeneralInsights, Session

logger = logging.getLogger(__name__)


def extract_targets(sessions: List[Session]) -> List[str]:
    """
    Extract all unique targets from sessions.

    Args:
        sessions: List of session objects

    Returns:
        List of unique target strings
    """
    targets = set()
    for session in sessions:
        if session.targets:
            targets.update(session.targets)
    return sorted(list(targets))


def extract_tools(sessions: List[Session]) -> Dict[str, int]:
    """
    Extract all tools and their usage counts from sessions.

    Args:
        sessions: List of session objects

    Returns:
        Dictionary mapping tool names to usage counts
    """
    tool_counter = Counter()
    for session in sessions:
        if session.tools:
            tool_counter.update(session.tools)
    return dict(tool_counter)


def extract_findings(sessions: List[Session]) -> Dict[str, int]:
    """
    Extract all findings and their occurrence counts from sessions.

    Args:
        sessions: List of session objects

    Returns:
        Dictionary mapping findings to occurrence counts
    """
    finding_counter = Counter()
    for session in sessions:
        if session.findings:
            finding_counter.update(session.findings)
    return dict(finding_counter)


def build_timeline(sessions: List[Session]) -> List[dict]:
    """
    Build timeline data grouping sessions by date.

    Args:
        sessions: List of session objects

    Returns:
        List of dictionaries with date and session_count
    """
    date_counter = Counter()
    for session in sessions:
        # Extract date from created_at (YYYY-MM-DD format)
        date_str = session.created_at.date().isoformat()
        date_counter[date_str] += 1

    # Sort by date
    timeline = [
        {"date": date, "session_count": count}
        for date, count in sorted(date_counter.items())
    ]
    return timeline


def summarize_sessions_for_llm(sessions: List[Session], max_sessions: int = 50) -> str:
    """
    Summarize sessions for LLM context, prioritizing recent and important sessions.
    If there are too many sessions, summarize key information instead of full terminal logs.

    Args:
        sessions: List of session objects
        max_sessions: Maximum number of sessions to include in full detail

    Returns:
        Formatted string summarizing sessions for LLM
    """
    if not sessions:
        return "No sessions available for analysis."

    # Sort by updated_at (most recent first)
    sorted_sessions = sorted(sessions, key=lambda s: s.updated_at, reverse=True)

    # If we have too many sessions, summarize instead of including full terminal logs
    if len(sorted_sessions) > max_sessions:
        logger.info(f"Summarizing {len(sorted_sessions)} sessions (exceeding max of {max_sessions})")

        # Include full details for most recent sessions
        recent_sessions = sorted_sessions[:max_sessions]
        older_sessions = sorted_sessions[max_sessions:]

        summary_parts = []
        summary_parts.append(f"=== ANALYZING {len(sorted_sessions)} TOTAL SESSIONS ===\n")
        summary_parts.append(f"Showing full details for {len(recent_sessions)} most recent sessions.\n")
        summary_parts.append(f"Summarizing {len(older_sessions)} older sessions.\n\n")

        # Full details for recent sessions
        for session in recent_sessions:
            summary_parts.append(_format_session_for_llm(session, include_terminal=True))

        # Summary for older sessions
        summary_parts.append("\n=== OLDER SESSIONS SUMMARY ===\n")
        for session in older_sessions:
            summary_parts.append(_format_session_for_llm(session, include_terminal=False))

        return "\n".join(summary_parts)
    else:
        # Include all sessions with full details
        summary_parts = []
        summary_parts.append(f"=== ANALYZING {len(sorted_sessions)} SESSIONS ===\n\n")
        for session in sorted_sessions:
            summary_parts.append(_format_session_for_llm(session, include_terminal=True))
        return "\n".join(summary_parts)


def _format_session_for_llm(session: Session, include_terminal: bool = True) -> str:
    """
    Format a single session for LLM context.

    Args:
        session: Session object
        include_terminal: Whether to include full terminal content

    Returns:
        Formatted string
    """
    parts = []
    parts.append(f"=== Session: {session.title} ===")
    parts.append(f"ID: {session.id}")
    parts.append(f"Created: {session.created_at.isoformat()}")
    parts.append(f"Updated: {session.updated_at.isoformat()}")

    if session.operation_id:
        parts.append(f"Operation ID: {session.operation_id}")

    if session.operator_name:
        parts.append(f"Operator: {session.operator_name}")

    if session.description:
        parts.append(f"Description: {session.description}")

    if session.tags:
        parts.append(f"Tags: {', '.join(session.tags)}")

    if session.targets:
        parts.append(f"Targets: {', '.join(session.targets)}")

    if session.tools:
        parts.append(f"Tools: {', '.join(session.tools)}")

    if session.findings:
        parts.append(f"Findings: {', '.join(session.findings)}")

    if include_terminal:
        parts.append(f"\nTerminal Content:\n{session.terminal_content}")
    else:
        parts.append(f"\nTerminal Content: [Summarized - {len(session.terminal_content)} characters]")

    # Add screenshot extractions if available
    if hasattr(session, 'screenshot_extractions') and session.screenshot_extractions:
        parts.append("\nScreenshot Extractions:")
        for extraction in session.screenshot_extractions:
            if extraction.extracted_text:
                parts.append(f"  - [{extraction.filename}]: {extraction.extracted_text[:200]}...")
                if extraction.analysis:
                    parts.append(f"    Analysis: {extraction.analysis[:200]}...")

    # Add metadata screenshot texts if available
    if session.metadata and "screenshot_texts" in session.metadata:
        screenshot_texts = session.metadata.get("screenshot_texts", [])
        if screenshot_texts:
            parts.append(f"\nScreenshot Texts: {len(screenshot_texts)} extractions")

    parts.append("\n")
    return "\n".join(parts)


async def generate_general_insights(sessions: List[Session]) -> GeneralInsights:
    """
    Generate general insights (statistics) from sessions.

    Args:
        sessions: List of session objects to analyze

    Returns:
        GeneralInsights object with statistics
    """
    logger.info(f"Generating general insights from {len(sessions)} sessions")

    # Extract data
    targets_list = extract_targets(sessions)
    tools_dict = extract_tools(sessions)
    findings_dict = extract_findings(sessions)
    timeline_data = build_timeline(sessions)

    # Extract unique operators
    operators = set()
    for session in sessions:
        if session.operator_name:
            operators.add(session.operator_name)
    operators = sorted(list(operators))

    # Get top 10 tools
    top_tools = [
        {"name": tool, "count": count}
        for tool, count in Counter(tools_dict).most_common(10)
    ]

    # Get findings summary (sorted by count, descending)
    findings_summary = [
        {"finding": finding, "count": count}
        for finding, count in sorted(findings_dict.items(), key=lambda x: x[1], reverse=True)
    ]

    # Build GeneralInsights
    insights = GeneralInsights(
        total_sessions=len(sessions),
        total_targets=len(targets_list),
        total_findings=len(findings_dict),
        total_tools=len(tools_dict),
        top_tools=top_tools,
        targets_list=targets_list,
        findings_summary=findings_summary,
        operators=operators,
        timeline_data=timeline_data,
        generated_at=datetime.utcnow()
    )

    logger.info(
        f"General insights generated: {insights.total_sessions} sessions, "
        f"{insights.total_targets} targets, {insights.total_tools} tools"
    )

    return insights

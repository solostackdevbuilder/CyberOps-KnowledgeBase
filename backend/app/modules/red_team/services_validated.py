"""
Validated Services for Red Team Edition - Layer 3 of the anti-hallucination stack.

This module wraps services.py with HallucinationGuard validation. It is a
SIBLING of services.py, not a replacement. routes.py imports from both by
design:
- services.py for raw paths where latency matters and the caller can tolerate
  unvalidated LLM output (some timeline/query endpoints)
- this module for user-facing FAA + expert analysis where a hallucinated
  MITRE technique or fabricated IOC is worse than an extra validation pass
"""
import json
import logging
import re
from datetime import datetime
from typing import Dict, List, Optional, Set
from uuid import uuid4

from app.core.services.base_llm import BaseLLM
from app.core.storage.base_store import BaseStore
from app.modules.red_team.models import (
    ExpertAnalysis, FAAItem, NextStep, Session
)
from app.modules.red_team.prompts_v2 import (
    FAA_ANALYSIS_PROMPT_V2,
    EXPERT_ANALYSIS_PROMPT_V2,
    get_prompt
)
from app.utils.hallucination_guard import (
    HallucinationGuard,
    HallucinationGuardResult,
    MITREValidator,
    ConfidenceThresholdManager,
    validate_mitre_technique
)

logger = logging.getLogger(__name__)


# ============================================================================
# Configuration
# ============================================================================

from dataclasses import dataclass


@dataclass
class ValidationConfig:
    """Configuration for validation behavior."""
    
    # Whether to use v2 anti-hallucination prompts
    USE_V2_PROMPTS: bool = True
    
    # Whether to strictly validate MITRE techniques
    STRICT_MITRE_VALIDATION: bool = True
    
    # Minimum confidence to auto-accept
    MIN_CONFIDENCE_AUTO_ACCEPT: float = 0.7
    
    # Minimum confidence to include (below this, item is dropped)
    MIN_CONFIDENCE_INCLUDE: float = 0.3
    
    # Whether to include validation metadata in responses
    INCLUDE_VALIDATION_METADATA: bool = True
    
    # Whether to auto-correct minor issues
    ENABLE_AUTO_CORRECTION: bool = True


# ============================================================================
# Validated FAA Analysis
# ============================================================================

async def analyze_session_for_faa_validated(
    session_id: str,
    storage: BaseStore,
    llm_service: BaseLLM,
    config: Optional[ValidationConfig] = None
) -> Dict:
    """
    Analyze a session and classify activities as actions or findings.
    This version includes hallucination guard validation.
    
    Args:
        session_id: Session ID to analyze
        storage: Storage instance to load session data
        llm_service: LLM service instance
        config: Optional validation configuration
        
    Returns:
        Dictionary with:
        - items: List of validated FAAItem objects
        - validation_summary: Summary of validation results
        - dropped_items: Items that failed validation
        - warnings: List of warnings
    """
    config = config or ValidationConfig()
    guard = HallucinationGuard(
        strict_mitre_validation=config.STRICT_MITRE_VALIDATION,
        enable_auto_correction=config.ENABLE_AUTO_CORRECTION
    )
    
    logger.info(f"Analyzing session {session_id} for FAA classification (validated)")
    
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
        
        # Use v2 prompt if configured
        if config.USE_V2_PROMPTS:
            prompt_template = FAA_ANALYSIS_PROMPT_V2
        else:
            from app.modules.red_team.prompts import FAA_ANALYSIS_PROMPT
            prompt_template = FAA_ANALYSIS_PROMPT
        
        # Prepare prompt with session data
        # Use string replacement instead of .format() to avoid issues with JSON braces in prompt
        prompt = prompt_template.replace(
            "{terminal_content}", session.terminal_content[:50000]
        ).replace(
            "{screenshot_text}", screenshot_text[:50000] if screenshot_text else "No screenshot text available"
        )
        
        # Build source context for validation
        source_context = session.terminal_content + "\n" + screenshot_text
        
        # Call LLM
        logger.info("Calling LLM for FAA analysis...")
        start_time = datetime.utcnow()
        
        response_text = await llm_service.query(
            question=prompt,
            context="",
            scope="single",
            operation_name=None
        )
        
        elapsed = (datetime.utcnow() - start_time).total_seconds()
        logger.info(f"LLM response received in {elapsed:.2f} seconds")
        
        # Parse JSON response using robust sanitizer
        from app.utils.json_sanitizer import JsonSanitizer
        
        logger.info(f"Parsing LLM response ({len(response_text)} chars)")
        analysis_data = JsonSanitizer.parse_llm_json(response_text)
        logger.info(f"Parsed result keys: {list(analysis_data.keys())}")
        
        # Check if parsing failed (fallback structure returned)
        if analysis_data.get("_fallback"):
            logger.error("JSON parsing failed, using fallback structure")
            parsing_notes = analysis_data.get("parsing_notes", "Unknown parsing error")
            return {
                "items": [],
                "validation_summary": {
                    "total_items_from_llm": 0,
                    "validated_items": 0,
                    "dropped_items": 0,
                    "average_confidence": 0,
                    "items_needing_review": 0,
                    "error": "JSON parse error"
                },
                "dropped_items": [],
                "warnings": [f"LLM returned malformed JSON. {parsing_notes}"]
            }
        
        # Ensure we have an items array
        if "items" not in analysis_data:
            logger.warning("No 'items' key in parsed response, using empty list")
            analysis_data["items"] = []
            if "parsing_notes" not in analysis_data:
                analysis_data["parsing_notes"] = "No items found in LLM response"
        
        # Process and validate each item
        validated_items = []
        dropped_items = []
        all_warnings = []
        validation_results = []
        
        # Check for parsing notes from LLM
        if "parsing_notes" in analysis_data:
            all_warnings.append(f"LLM parsing notes: {analysis_data['parsing_notes']}")
        
        if "unclassified_content" in analysis_data:
            for content in analysis_data.get("unclassified_content", []):
                all_warnings.append(f"Unclassified content: {content}")
        
        now = datetime.utcnow()
        
        for item_data in analysis_data.get("items", []):
            try:
                # Get original confidence
                original_confidence = float(item_data.get("confidence_score", 0.7))
                
                # Validate with hallucination guard
                validation_result = guard.validate_faa_item(
                    item_data,
                    source_context,
                    original_confidence
                )
                
                validation_results.append(validation_result)
                
                # Check if we should include this item
                if validation_result.overall_confidence < config.MIN_CONFIDENCE_INCLUDE:
                    dropped_items.append({
                        "item": item_data,
                        "reason": "Confidence below threshold",
                        "validation": validation_result.to_dict()
                    })
                    continue
                
                # Apply corrections if available
                mitre_technique = item_data.get("mitre_technique")
                if validation_result.corrections.get("suggested_technique"):
                    if config.ENABLE_AUTO_CORRECTION:
                        mitre_technique = validation_result.corrections["suggested_technique"]
                        all_warnings.append(
                            f"Auto-corrected MITRE technique: {item_data.get('mitre_technique')} -> {mitre_technique}"
                        )
                
                # Validate and normalize MITRE technique
                if mitre_technique:
                    is_valid, normalized, error = validate_mitre_technique(mitre_technique)
                    if not is_valid:
                        if config.STRICT_MITRE_VALIDATION:
                            all_warnings.append(f"Removed invalid MITRE technique: {mitre_technique} ({error})")
                            mitre_technique = None
                        else:
                            all_warnings.append(f"Kept potentially invalid MITRE technique: {mitre_technique}")
                    else:
                        mitre_technique = f"{normalized} - {mitre_technique.split(' - ', 1)[1] if ' - ' in mitre_technique else normalized}"
                
                # Determine timestamp
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
                
                # Get detection strategies for the technique
                detection_strategy_ids = []
                if mitre_technique:
                    try:
                        from app.modules.red_team.detection_strategies import get_detection_strategy_service
                        strategy_service = get_detection_strategy_service()
                        technique_id = strategy_service.extract_technique_id(mitre_technique)
                        if technique_id:
                            strategies = strategy_service.get_strategies_for_technique(technique_id)
                            detection_strategy_ids = [s.id for s in strategies]
                    except Exception as e:
                        logger.warning(f"Failed to link detection strategies: {e}")
                
                # Create validated FAA item
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
                    confidence_score=validation_result.overall_confidence,  # Use validated confidence
                    manually_corrected=False,
                    notes=item_data.get("notes"),
                    created_at=now,
                    updated_at=now
                )
                
                # Add validation warnings to notes
                if validation_result.warnings and config.INCLUDE_VALIDATION_METADATA:
                    existing_notes = faa_item.notes or ""
                    validation_notes = " | ".join(validation_result.warnings[:2])  # Limit to 2
                    faa_item.notes = f"{existing_notes} [Validation: {validation_notes}]".strip()
                
                # Mark if needs review
                if validation_result.recommended_action == "review":
                    faa_item.notes = (faa_item.notes or "") + " [NEEDS REVIEW]"
                
                validated_items.append(faa_item)
                all_warnings.extend(validation_result.warnings)
                
            except Exception as e:
                logger.warning(f"Failed to process FAA item: {e}")
                dropped_items.append({
                    "item": item_data,
                    "reason": f"Processing error: {e}",
                    "validation": None
                })
                continue
        
        # Build validation summary
        validation_summary = {
            "total_items_from_llm": len(analysis_data.get("items", [])),
            "validated_items": len(validated_items),
            "dropped_items": len(dropped_items),
            "average_confidence": sum(v.overall_confidence for v in validation_results) / len(validation_results) if validation_results else 0,
            "items_needing_review": sum(1 for v in validation_results if v.recommended_action == "review"),
            "mitre_corrections_made": sum(1 for v in validation_results if v.corrections.get("suggested_technique")),
            "grounding_issues": sum(1 for v in validation_results if v.grounding_validation and not v.grounding_validation.is_grounded)
        }
        
        logger.info(
            f"FAA analysis complete: {validation_summary['validated_items']} validated, "
            f"{validation_summary['dropped_items']} dropped, "
            f"{validation_summary['items_needing_review']} need review"
        )
        
        return {
            "items": validated_items,
            "validation_summary": validation_summary,
            "dropped_items": dropped_items,
            "warnings": list(set(all_warnings))  # Deduplicate
        }
        
    except Exception as e:
        logger.error(f"Failed to analyze session for FAA: {e}")
        raise RuntimeError(f"FAA analysis failed: {e}") from e


# ============================================================================
# Validated Expert Analysis
# ============================================================================

async def generate_expert_analysis_validated(
    sessions: List[Session],
    llm_service: BaseLLM,
    operation_names: Optional[List[str]] = None,
    config: Optional[ValidationConfig] = None
) -> Dict:
    """
    Generate expert analysis using LLM with hallucination guard validation.
    
    Args:
        sessions: List of session objects to analyze
        llm_service: LLM service instance
        operation_names: Optional list of operation names for context
        config: Optional validation configuration
        
    Returns:
        Dictionary with:
        - analysis: ExpertAnalysis object
        - validation_result: HallucinationGuardResult
        - warnings: List of warnings
    """
    from app.modules.red_team.services import (
        summarize_sessions_for_llm,
        create_empty_analysis,
        KILL_CHAIN_PHASES
    )
    
    config = config or ValidationConfig()
    guard = HallucinationGuard(
        strict_mitre_validation=config.STRICT_MITRE_VALIDATION,
        enable_auto_correction=config.ENABLE_AUTO_CORRECTION
    )
    
    logger.info(f"Generating validated expert analysis from {len(sessions)} sessions")
    
    if not sessions:
        return {
            "analysis": create_empty_analysis("No sessions available for analysis."),
            "validation_result": None,
            "warnings": ["No sessions provided"]
        }
    
    try:
        # Build context from sessions
        context = summarize_sessions_for_llm(sessions)
        
        # Add operation context
        if operation_names and len(operation_names) > 1:
            context = f"=== ANALYZING MULTIPLE OPERATIONS ===\nOperations: {', '.join(operation_names)}\n\n{context}"
        elif operation_names and len(operation_names) == 1:
            context = f"=== OPERATION: {operation_names[0]} ===\n\n{context}"
        
        # Use v2 prompt if configured
        if config.USE_V2_PROMPTS:
            prompt = EXPERT_ANALYSIS_PROMPT_V2
        else:
            from app.modules.red_team.prompts import EXPERT_ANALYSIS_PROMPT
            prompt = EXPERT_ANALYSIS_PROMPT
        
        question = f"""{prompt}

Please analyze the session data provided in the context and return your analysis as JSON following the format specified above."""
        
        # Call LLM
        logger.info("Calling LLM for expert analysis...")
        start_time = datetime.utcnow()
        
        response_text = await llm_service.query(
            question=question,
            context=context,
            scope="all" if operation_names and len(operation_names) > 1 else "single",
            operation_name=operation_names[0] if operation_names and len(operation_names) == 1 else None
        )
        
        elapsed = (datetime.utcnow() - start_time).total_seconds()
        logger.info(f"LLM response received in {elapsed:.2f} seconds")
        
        # Parse JSON response using robust sanitizer
        from app.utils.json_sanitizer import JsonSanitizer
        
        analysis_data = JsonSanitizer.parse_llm_json(response_text)
        
        # Check if parsing failed (fallback structure returned)
        if analysis_data.get("_fallback"):
            logger.error("JSON parsing failed for expert analysis, using fallback")
            return {
                "analysis": create_empty_analysis("Failed to parse LLM response - malformed JSON"),
                "validation_result": None,
                "warnings": ["JSON parse error - the model returned malformed JSON"]
            }
        
        # Validate with hallucination guard
        session_ids = {s.id for s in sessions}
        validation_result = guard.validate_expert_analysis(
            analysis_data,
            context,
            session_ids
        )
        
        warnings = list(validation_result.warnings)
        
        # Check data quality notes from LLM
        if "data_quality_notes" in analysis_data:
            warnings.append(f"LLM data quality notes: {analysis_data['data_quality_notes']}")
        
        # Validate kill chain progress
        kill_chain_progress = {}
        for phase in KILL_CHAIN_PHASES:
            status = analysis_data.get("kill_chain_progress", {}).get(phase, "next")
            if status not in ["completed", "current", "next", "unknown"]:
                status = "next"
            kill_chain_progress[phase] = status
        
        # Validate phase confidence
        phase_confidence = analysis_data.get("phase_confidence", "Medium")
        if phase_confidence not in ["High", "Medium", "Low"]:
            phase_confidence = "Medium"
        
        # Validate current phase
        current_phase = analysis_data.get("current_phase", "Reconnaissance")
        if current_phase not in KILL_CHAIN_PHASES:
            current_phase_lower = current_phase.lower()
            for phase in KILL_CHAIN_PHASES:
                if phase.lower() in current_phase_lower or current_phase_lower in phase.lower():
                    current_phase = phase
                    break
            else:
                current_phase = "Reconnaissance"
                warnings.append(f"Invalid phase '{analysis_data.get('current_phase')}' corrected to 'Reconnaissance'")
        
        # Parse next steps
        next_steps = []
        for step_data in analysis_data.get("next_steps", []):
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
            valid_evidence = [sid for sid in evidence_sessions if sid in session_ids]
            invalid_evidence = [sid for sid in evidence_sessions if sid not in session_ids]
            if invalid_evidence:
                warnings.append(f"Removed {len(invalid_evidence)} invalid session references")
            evidence_sessions = valid_evidence
        else:
            evidence_sessions = []
        
        # Build ExpertAnalysis
        expert_analysis = ExpertAnalysis(
            current_phase=current_phase,
            phase_confidence=phase_confidence,
            kill_chain_progress=kill_chain_progress,
            progress_summary=analysis_data.get("progress_summary", "Analysis in progress."),
            gaps_identified=analysis_data.get("gaps_identified", []),
            recommendations=analysis_data.get("recommendations", []),
            next_steps=next_steps,
            risk_assessment=analysis_data.get("risk_assessment", "Risk assessment pending."),
            detection_risk_assessment=None,
            recommended_detection_strategies=[],
            detection_coverage_gaps=[],
            evidence_sessions=evidence_sessions,
            generated_at=datetime.utcnow()
        )
        
        # Add validation confidence to the response
        if config.INCLUDE_VALIDATION_METADATA:
            # We can't modify ExpertAnalysis, but we return it in the dict
            pass
        
        logger.info(
            f"Expert analysis generated: phase={expert_analysis.current_phase}, "
            f"confidence={expert_analysis.phase_confidence}, "
            f"validation_confidence={validation_result.overall_confidence:.2f}"
        )
        
        return {
            "analysis": expert_analysis,
            "validation_result": validation_result.to_dict(),
            "warnings": warnings,
            "overall_confidence": validation_result.overall_confidence,
            "recommended_action": validation_result.recommended_action
        }
        
    except Exception as e:
        logger.error(f"Failed to generate expert analysis: {e}", exc_info=True)
        return {
            "analysis": create_empty_analysis(f"LLM analysis failed: {str(e)}"),
            "validation_result": None,
            "warnings": [f"Analysis failed: {e}"]
        }


# ============================================================================
# Validated Query Response
# ============================================================================

async def query_with_validation(
    question: str,
    context: str,
    llm_service: BaseLLM,
    scope: str = "all",
    operation_name: Optional[str] = None,
    config: Optional[ValidationConfig] = None
) -> Dict:
    """
    Query the LLM with validation of the response.
    
    Args:
        question: User's question
        context: Context to provide to the LLM
        llm_service: LLM service instance
        scope: Query scope
        operation_name: Operation name for single scope
        config: Optional validation configuration
        
    Returns:
        Dictionary with:
        - answer: The LLM's response
        - validation_result: HallucinationGuardResult
        - confidence: Overall confidence score
        - warnings: List of warnings
    """
    config = config or ValidationConfig()
    guard = HallucinationGuard()
    
    try:
        # Call LLM
        response = await llm_service.query(
            question=question,
            context=context,
            scope=scope,
            operation_name=operation_name
        )
        
        # Validate response
        validation_result = guard.validate_query_response(
            response,
            context,
            question
        )
        
        # Build warnings
        warnings = list(validation_result.warnings)
        
        if validation_result.hallucination_analysis:
            if validation_result.hallucination_analysis.hallucination_risk_score > 0.5:
                warnings.append(validation_result.hallucination_analysis.recommendation)
        
        if validation_result.grounding_validation:
            if not validation_result.grounding_validation.is_grounded:
                for fab in validation_result.grounding_validation.fabrications:
                    warnings.append(fab.message)
        
        return {
            "answer": response,
            "validation_result": validation_result.to_dict(),
            "confidence": validation_result.overall_confidence,
            "warnings": warnings,
            "recommended_action": validation_result.recommended_action
        }
        
    except Exception as e:
        logger.error(f"Query with validation failed: {e}")
        return {
            "answer": f"Error processing query: {e}",
            "validation_result": None,
            "confidence": 0.0,
            "warnings": [f"Query failed: {e}"],
            "recommended_action": "reject"
        }


# ============================================================================
# Utility Functions
# ============================================================================

def get_validation_summary(results: List[HallucinationGuardResult]) -> Dict:
    """
    Generate a summary of multiple validation results.
    
    Args:
        results: List of validation results
        
    Returns:
        Summary dictionary
    """
    if not results:
        return {
            "total_items": 0,
            "valid_items": 0,
            "average_confidence": 0.0,
            "needs_review_count": 0,
            "rejection_count": 0
        }
    
    return {
        "total_items": len(results),
        "valid_items": sum(1 for r in results if r.is_valid),
        "average_confidence": sum(r.overall_confidence for r in results) / len(results),
        "needs_review_count": sum(1 for r in results if r.recommended_action == "review"),
        "rejection_count": sum(1 for r in results if r.recommended_action == "reject"),
        "critical_issues_total": sum(len(r.critical_issues) for r in results),
        "warnings_total": sum(len(r.warnings) for r in results)
    }


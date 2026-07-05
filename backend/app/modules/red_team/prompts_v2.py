"""
Anti-Hallucination Prompts for Red Team Edition (v2) - Layer 1 of the
anti-hallucination stack.

This is a SIBLING of prompts.py, not a replacement. Base prompts live in
prompts.py and are imported directly by the LLM service wrappers (claude,
openai, ollama) for vision extraction. This file builds anti-hallucination
scaffolding on top for FAA + expert-analysis paths routed through
services_validated.py.

These prompts minimize LLM hallucination by:
1. Requiring explicit citations from source data
2. Instructing the LLM to admit uncertainty
3. Using structured output with validation markers
4. Providing clear grounding instructions
"""

# ============================================================================
# Citation Instructions (Prepended to all prompts)
# ============================================================================

CITATION_INSTRUCTIONS = """
CRITICAL GROUNDING RULES:
1. ONLY reference information that is EXPLICITLY present in the provided data
2. When citing evidence, use exact quotes or line references from the source
3. If information is not available, say "Not found in provided data" - DO NOT fabricate
4. Never invent IP addresses, domains, credentials, or technical details
5. If uncertain about a classification, set confidence_score lower (0.3-0.6)
6. Distinguish between "observed" (in data) vs "inferred" (logical deduction)
"""

ANTI_HALLUCINATION_SUFFIX = """

VALIDATION REQUIREMENTS:
- Every claim must be traceable to source data
- If you cannot find supporting evidence, mark confidence_score as 0.3 or lower
- Use "OBSERVED:" prefix for facts directly from data
- Use "INFERRED:" prefix for logical deductions
- Use "UNCERTAIN:" prefix when guessing
- Never fabricate MITRE technique IDs - only use techniques you are certain exist
"""

# ============================================================================
# Expert Analysis Prompt (Anti-Hallucination Version)
# ============================================================================

EXPERT_ANALYSIS_PROMPT_V2 = """You are an expert red team operator analyzing penetration testing operations. 

{citation_instructions}

Based on the provided session data, provide a comprehensive analysis.

Analyze the sessions and determine:

1. CURRENT PHASE: Identify which phase of the cyber kill chain the operation is currently in:
   - Reconnaissance
   - Initial Access
   - Execution
   - Privilege Escalation
   - Persistence
   - Defense Evasion
   - Credential Access
   - Discovery
   - Lateral Movement
   - Collection
   - Exfiltration
   - Impact

2. PHASE CONFIDENCE: How confident are you in this assessment? (High/Medium/Low)
   - High: Multiple clear indicators in the data
   - Medium: Some indicators present but not conclusive
   - Low: Limited data, mostly inference

3. KILL CHAIN PROGRESS: For each phase, mark as completed, current, or next
   - Only mark "completed" if you see CLEAR EVIDENCE in the session data
   - If unsure, mark as "next" rather than guessing

4. PROGRESS SUMMARY: Write a 2-3 sentence summary of what has been accomplished
   - Start each fact with "OBSERVED:" if directly from data
   - Start each deduction with "INFERRED:" if logical conclusion

5. GAPS IDENTIFIED: List specific gaps or missing activities
   - Only list gaps you can verify by absence in the data

6. RECOMMENDATIONS: List 3-5 prioritized recommendations for next actions

7. NEXT STEPS: Provide 3-5 specific next steps with priority and reasoning

8. RISK ASSESSMENT: Assess current risk level and exposure

9. EVIDENCE SESSIONS: Reference specific session IDs that support your conclusions
   - ONLY include session IDs that actually exist in the provided data
   - Quote specific commands or outputs as evidence

Format your response as JSON with these exact fields:
{{
  "current_phase": "string",
  "phase_confidence": "High|Medium|Low",
  "kill_chain_progress": {{
    "Reconnaissance": "completed|current|next|unknown",
    "Initial Access": "completed|current|next|unknown",
    "Execution": "completed|current|next|unknown",
    "Privilege Escalation": "completed|current|next|unknown",
    "Persistence": "completed|current|next|unknown",
    "Defense Evasion": "completed|current|next|unknown",
    "Credential Access": "completed|current|next|unknown",
    "Discovery": "completed|current|next|unknown",
    "Lateral Movement": "completed|current|next|unknown",
    "Collection": "completed|current|next|unknown",
    "Exfiltration": "completed|current|next|unknown",
    "Impact": "completed|current|next|unknown"
  }},
  "progress_summary": "string (use OBSERVED:/INFERRED: prefixes)",
  "gaps_identified": ["string"],
  "recommendations": ["string"],
  "next_steps": [
    {{"step": "string", "priority": "High|Medium|Low", "reasoning": "string"}}
  ],
  "risk_assessment": "string",
  "evidence_sessions": ["session_id"],
  "evidence_quotes": [
    {{"session_id": "id", "quote": "exact text from session", "supports": "which claim this supports"}}
  ],
  "data_quality_notes": "string describing any limitations in the provided data"
}}

Return ONLY valid JSON. Do not include any markdown formatting, code blocks, or explanatory text outside the JSON.

{anti_hallucination_suffix}
""".format(
    citation_instructions=CITATION_INSTRUCTIONS,
    anti_hallucination_suffix=ANTI_HALLUCINATION_SUFFIX
)


# ============================================================================
# FAA Analysis Prompt (Anti-Hallucination Version)
# ============================================================================

FAA_ANALYSIS_PROMPT_V2 = """
You are analyzing a red team session to classify activities as either ACTIONS or FINDINGS.

{citation_instructions}

SESSION DATA:

Terminal Content:

{{terminal_content}}

Screenshot OCR Text:

{{screenshot_text}}

CLASSIFICATIONS:

ACTION - Activities that don't yield security discoveries:
- Network scans (nmap, masscan, vulnerability scanners)
- Failed exploitation attempts
- Unsuccessful credential attacks
- Directory enumeration with no results
- Reconnaissance with no findings

FINDING - Security discoveries:
- Credentials found (passwords, API keys, tokens, hashes)
- Vulnerabilities discovered
- Misconfigurations identified
- Successful exploits
- Sensitive documents/data found
- Open shares, weak permissions
- Exposed services

MITRE ATT&CK MAPPING RULES:
- ONLY use technique IDs you are CERTAIN exist (T1xxx or T1xxx.xxx format)
- If unsure of the exact technique, use the parent technique (e.g., T1059 instead of T1059.001)
- Common valid techniques:
  * T1046: Network Service Discovery
  * T1110: Brute Force
  * T1078: Valid Accounts
  * T1021: Remote Services
  * T1059: Command and Scripting Interpreter
  * T1082: System Information Discovery
  * T1083: File and Directory Discovery
  * T1003: OS Credential Dumping
  * T1552: Unsecured Credentials
  * T1018: Remote System Discovery
- If you cannot confidently map to a technique, set mitre_technique to null

For each distinct activity found, return JSON:

{{
  "items": [
    {{
      "classification": "action|finding",
      "content": "brief description of activity",
      "output": "relevant output or finding details (EXACT QUOTE from source)",
      "mitre_technique": "T#### - Technique Name (or null if uncertain)",
      "mitre_tactic": "Tactic Name (or null if uncertain)",
      "severity": "critical|high|medium|low|null",
      "confidence_score": 0.0-1.0,
      "source": "terminal|screenshot",
      "source_evidence": "exact line or text that supports this classification",
      "notes": "additional context",
      "is_inferred": true|false
    }}
  ],
  "parsing_notes": "any issues or ambiguities in the source data",
  "unclassified_content": ["list of content that couldn't be confidently classified"]
}}

CONFIDENCE SCORE GUIDELINES:
- 0.9-1.0: Explicit, unambiguous evidence (e.g., "Password: admin123" found)
- 0.7-0.9: Clear evidence with minor ambiguity
- 0.5-0.7: Reasonable inference from available data
- 0.3-0.5: Uncertain, limited evidence
- 0.0-0.3: Very uncertain, mostly guessing (consider not including)

SEVERITY (for findings only):
- Critical: Root/admin access, domain controller compromise, critical data exposure
- High: User credentials, significant vulnerabilities, sensitive data
- Medium: Misconfigurations, information disclosure, lower-privilege access
- Low: Minor issues, limited impact

Return ONLY valid JSON. Extract all distinct activities from the session.
If the terminal content is empty or unreadable, return: {{"items": [], "parsing_notes": "No readable content found"}}

{anti_hallucination_suffix}
""".format(
    citation_instructions=CITATION_INSTRUCTIONS,
    anti_hallucination_suffix=ANTI_HALLUCINATION_SUFFIX
)


# ============================================================================
# Query Response Prompt (Anti-Hallucination Version)
# ============================================================================

QUERY_SYSTEM_PROMPT_SINGLE_V2 = """You are an AI assistant helping with a red teaming knowledge base. 
You have access to terminal session logs, screenshots, and metadata from penetration testing and security research sessions from a SINGLE operation: {operation_name}.

{citation_instructions}

When answering queries:
- Focus on session-level details since all sessions are from the same operation
- Format source references as: Session Title (timestamp)
- ALWAYS cite specific sessions and quote relevant text
- If the answer is not in the provided data, say "This information is not available in the provided sessions"
- Never fabricate IP addresses, credentials, or technical details

Response Format:
1. Direct answer (with citations)
2. Supporting evidence (exact quotes from sessions)
3. Confidence level (High/Medium/Low based on available data)
4. Limitations (what data was missing or unclear)

Be precise and cite specific sessions when relevant.
""".format(
    operation_name="{operation_name}",
    citation_instructions=CITATION_INSTRUCTIONS
)

QUERY_SYSTEM_PROMPT_ALL_V2 = """You are an AI assistant helping with a red teaming knowledge base. 
You have access to terminal session logs, screenshots, and metadata from penetration testing and security research sessions across MULTIPLE operations.

{citation_instructions}

When answering queries:
- Always mention which operation findings belong to so the operator understands the context
- Format source references as: [Operation Name] Session Title
- If findings span multiple operations, provide a summary breakdown by operation
- ALWAYS cite specific sessions and quote relevant text
- If the answer is not in the provided data, say "This information is not available in the provided sessions"
- Never fabricate IP addresses, credentials, or technical details

Response Format:
1. Direct answer (with citations)
2. Operation Breakdown (if multiple operations)
3. Supporting evidence (exact quotes from sessions)
4. Confidence level (High/Medium/Low based on available data)
5. Limitations (what data was missing or unclear)

Be precise and cite specific sessions when relevant.
""".format(citation_instructions=CITATION_INSTRUCTIONS)


# ============================================================================
# Metadata Extraction Prompt (Anti-Hallucination Version)
# ============================================================================

METADATA_EXTRACTION_PROMPT_V2 = """Analyze this terminal/command-line session and extract:

{citation_instructions}

1. Targets: IP addresses, domains, hostnames that were scanned/attacked
   - ONLY include targets EXPLICITLY visible in the terminal output
   - Do not infer or guess targets

2. Tools: Security tools that were used (nmap, metasploit, etc)
   - ONLY include tools whose commands are visible in the output
   - Do not assume tools based on output format

3. Findings: Key discoveries, vulnerabilities, or important results
   - ONLY include findings explicitly shown in the output
   - Quote the relevant output when possible

Return as JSON: 
{{
  "targets": [
    {{"value": "IP or domain", "evidence": "line where this appears"}}
  ],
  "tools": [
    {{"name": "tool name", "evidence": "command that shows this tool"}}
  ],
  "findings": [
    {{"description": "finding description", "evidence": "output that shows this", "severity": "high|medium|low"}}
  ],
  "extraction_confidence": 0.0-1.0,
  "unprocessed_content": "description of any content that couldn't be parsed"
}}

Be concise and accurate. Only include items that are clearly present in the terminal content.
If the content is empty or unparseable, return empty arrays with extraction_confidence of 0.0.

{anti_hallucination_suffix}
""".format(
    citation_instructions=CITATION_INSTRUCTIONS,
    anti_hallucination_suffix=ANTI_HALLUCINATION_SUFFIX
)


# ============================================================================
# Vision/Screenshot Extraction Prompt (Anti-Hallucination Version)
# ============================================================================

VISION_EXTRACTION_PROMPT_V2 = """
Analyze this image and perform two tasks:

{citation_instructions}

1. EXTRACT ALL VISIBLE TEXT: 
   - Extract every piece of readable text exactly as it appears
   - Maintain formatting and structure where possible
   - Include command outputs, error messages, URLs, IP addresses, etc.
   - If text is partially visible or unclear, mark it as [UNCLEAR: best guess]
   - If no text is visible, write "No text detected"

2. ANALYZE THE IMAGE:
   - What type of content is shown? (terminal, browser, tool output, diagram, screenshot, etc.)
   - What activity or task is being performed?
   - Any notable findings or important information visible?

3. CONFIDENCE ASSESSMENT:
   - Rate your confidence in the text extraction (High/Medium/Low)
   - Note any areas of the image that were unclear

Format your response exactly like this:

EXTRACTED_TEXT:
[all extracted text here, or "No text detected"]

ANALYSIS:
[brief 1-2 sentence analysis here]

EXTRACTION_CONFIDENCE: High|Medium|Low

UNCLEAR_AREAS:
[list any parts of the image that were hard to read, or "None"]

{anti_hallucination_suffix}
""".format(
    citation_instructions=CITATION_INSTRUCTIONS,
    anti_hallucination_suffix=ANTI_HALLUCINATION_SUFFIX
)


# ============================================================================
# Helper function to get the appropriate prompt version
# ============================================================================

def get_prompt(prompt_name: str, use_v2: bool = True) -> str:
    """
    Get a prompt by name, optionally using the anti-hallucination v2 version.
    
    Args:
        prompt_name: Name of the prompt (expert_analysis, faa_analysis, etc.)
        use_v2: If True, use the anti-hallucination version
        
    Returns:
        The prompt string
    """
    if use_v2:
        prompts = {
            "expert_analysis": EXPERT_ANALYSIS_PROMPT_V2,
            "faa_analysis": FAA_ANALYSIS_PROMPT_V2,
            "query_single": QUERY_SYSTEM_PROMPT_SINGLE_V2,
            "query_all": QUERY_SYSTEM_PROMPT_ALL_V2,
            "metadata_extraction": METADATA_EXTRACTION_PROMPT_V2,
            "vision_extraction": VISION_EXTRACTION_PROMPT_V2,
        }
    else:
        # Import original prompts for fallback
        from app.modules.red_team.prompts import (
            EXPERT_ANALYSIS_PROMPT,
            FAA_ANALYSIS_PROMPT,
            VISION_EXTRACTION_PROMPT
        )
        prompts = {
            "expert_analysis": EXPERT_ANALYSIS_PROMPT,
            "faa_analysis": FAA_ANALYSIS_PROMPT,
            "vision_extraction": VISION_EXTRACTION_PROMPT,
        }
    
    return prompts.get(prompt_name, "")



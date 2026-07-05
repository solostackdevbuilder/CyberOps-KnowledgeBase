"""
Prompts for red team edition.
Combines insights and vision prompts.
"""

# ============================================================================
# Insights Prompts
# ============================================================================

EXPERT_ANALYSIS_PROMPT = """You are an expert red team operator analyzing penetration testing operations. Based on the provided session data, provide a comprehensive analysis.

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

3. KILL CHAIN PROGRESS: For each phase, mark as completed, current, or next

4. PROGRESS SUMMARY: Write a 2-3 sentence summary of what has been accomplished so far

5. GAPS IDENTIFIED: List specific gaps or missing activities (e.g., "No persistence established", "Limited lateral movement")

6. RECOMMENDATIONS: List 3-5 prioritized recommendations for next actions

7. NEXT STEPS: Provide 3-5 specific next steps with priority (High/Medium/Low) and reasoning

8. RISK ASSESSMENT: Assess current risk level and exposure

9. EVIDENCE SESSIONS: Reference specific session IDs that support your conclusions

Format your response as JSON with these exact fields:
{{
  "current_phase": "string",
  "phase_confidence": "High|Medium|Low",
  "kill_chain_progress": {{
    "Reconnaissance": "completed|current|next",
    "Initial Access": "completed|current|next",
    "Execution": "completed|current|next",
    "Privilege Escalation": "completed|current|next",
    "Persistence": "completed|current|next",
    "Defense Evasion": "completed|current|next",
    "Credential Access": "completed|current|next",
    "Discovery": "completed|current|next",
    "Lateral Movement": "completed|current|next",
    "Collection": "completed|current|next",
    "Exfiltration": "completed|current|next",
    "Impact": "completed|current|next"
  }},
  "progress_summary": "string",
  "gaps_identified": ["string"],
  "recommendations": ["string"],
  "next_steps": [
    {{"step": "string", "priority": "High|Medium|Low", "reasoning": "string"}}
  ],
  "risk_assessment": "string",
  "evidence_sessions": ["session_id"]
}}

Return ONLY valid JSON. Do not include any markdown formatting, code blocks, or explanatory text outside the JSON."""


# ============================================================================
# Vision Prompts
# ============================================================================

VISION_EXTRACTION_PROMPT = """
Analyze this image and perform two tasks:

1. EXTRACT ALL VISIBLE TEXT: 
   - Extract every piece of readable text exactly as it appears
   - Maintain formatting and structure where possible
   - Include command outputs, error messages, URLs, IP addresses, etc.
   - If no text is visible, write "No text detected"

2. ANALYZE THE IMAGE:
   - What type of content is shown? (terminal, browser, tool output, diagram, screenshot, etc.)
   - What activity or task is being performed?
   - Any notable findings or important information visible?

Format your response exactly like this:

EXTRACTED_TEXT:
[all extracted text here, or "No text detected"]

ANALYSIS:
[brief 1-2 sentence analysis here]
"""


# ============================================================================
# FAA (Findings and Actions) Prompts
# ============================================================================

FAA_ANALYSIS_PROMPT = """
You are analyzing a red team session to classify activities as either ACTIONS or FINDINGS.

SESSION DATA:

Terminal Content:

{terminal_content}

Screenshot OCR Text:

{screenshot_text}

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

MITRE ATT&CK TECHNIQUES (examples):
- T1046: Network Service Discovery (Reconnaissance)
- T1110: Brute Force (Credential Access)
- T1078: Valid Accounts (Defense Evasion)
- T1021: Remote Services (Lateral Movement)
- T1059: Command and Scripting Interpreter (Execution)

For each distinct activity found, return JSON:

{{
  "items": [
    {{
      "classification": "action|finding",
      "content": "brief description of activity",
      "output": "relevant output or finding details",
      "mitre_technique": "T#### - Technique Name",
      "mitre_tactic": "Tactic Name",
      "severity": "critical|high|medium|low|null",
      "confidence_score": 0.0-1.0,
      "source": "terminal|screenshot",
      "notes": "additional context"
    }}
  ]
}}

SEVERITY (for findings only):
- Critical: Root/admin access, domain controller compromise, critical data exposure
- High: User credentials, significant vulnerabilities, sensitive data
- Medium: Misconfigurations, information disclosure, lower-privilege access
- Low: Minor issues, limited impact

Return ONLY valid JSON. Extract all distinct activities from the session.
"""

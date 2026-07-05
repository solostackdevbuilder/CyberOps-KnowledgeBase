"""
Bulletproof JSON sanitizer for fixing malformed LLM output.

Handles control characters, truncated JSON, markdown blocks, and syntax errors.
Guarantees a dict output (never raises JSONDecodeError).
"""
import json
import logging
import re
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)


class JsonSanitizer:
    """
    A bulletproof JSON sanitizer that fixes malformed LLM output.
    
    Handles control characters, truncated JSON, markdown blocks, and syntax errors.
    """

    @staticmethod
    def parse_llm_json(raw_response: str) -> Dict[str, Any]:
        """
        Main entry point. Takes any LLM response string and returns valid JSON.
        Guarantees a dict output (never raises JSONDecodeError).

        Args:
            raw_response: Raw response string from LLM (may contain markdown, control chars, etc.)

        Returns:
            Parsed JSON dictionary (never None, always returns a valid dict)
        """
        if not raw_response or not isinstance(raw_response, str):
            logger.warning("Empty or invalid response received")
            return JsonSanitizer._emergency_fallback()

        # Strategy 1: Direct parse attempt (fast path for well-formed JSON)
        try:
            return json.loads(raw_response)
        except json.JSONDecodeError:
            logger.debug("Direct parse failed, entering sanitization pipeline")

        # Strategy 2: Extract JSON from markdown/code fences
        json_block = JsonSanitizer._extract_json_block(raw_response)

        # Strategy 3: Fix control characters using state machine
        sanitized = JsonSanitizer._fix_control_characters(json_block)

        # Strategy 4: Fix common syntax errors
        sanitized = JsonSanitizer._fix_syntax_errors(sanitized)

        # Strategy 5: Try parsing with multiple increasing leniency levels
        result = JsonSanitizer._attempt_parsing(sanitized)

        if result is None:
            # Strategy 6: Extract partial JSON structure
            result = JsonSanitizer._extract_partial_json(sanitized)

        # Strategy 7: Absolute last resort
        if result is None:
            logger.critical("All parsing strategies failed")
            # Log a sample of what we're trying to parse for debugging
            logger.error(f"Failed to parse JSON. First 500 chars: {sanitized[:500]}")
            logger.error(f"Last 500 chars: {sanitized[-500:]}")
            result = JsonSanitizer._emergency_fallback()

        return result

    @staticmethod
    def _extract_json_block(text: str) -> str:
        """Extract JSON from markdown code fences or find the first JSON object."""
        text = text.strip()

        # Pattern 1: ```json ... ```
        match = re.search(r'```json\s*(.+?)\s*```', text, re.DOTALL)
        if match:
            logger.info("Extracted JSON from markdown code fence")
            return match.group(1)

        # Pattern 2: ``` ... ```
        match = re.search(r'```\s*(.+?)\s*```', text, re.DOTALL)
        if match:
            logger.info("Extracted JSON from generic code fence")
            return match.group(1)

        # Pattern 3: Find first { and last }
        start = text.find('{')
        end = text.rfind('}')

        if start >= 0 and end > start:
            logger.info("Extracted JSON by boundary detection")
            return text[start:end + 1]

        logger.warning("No clear JSON boundaries found, returning original text")
        return text

    @staticmethod
    def _fix_control_characters(text: str) -> str:
        """
        Core function: Fixes unescaped control characters in JSON strings.
        Uses a state machine to only modify characters within string values.

        Args:
            text: JSON text with potential control character issues

        Returns:
            Sanitized JSON text with control characters properly escaped
        """
        result = []
        in_string = False
        escape_next = False

        for i, char in enumerate(text):
            # Handle escaped sequences
            if escape_next:
                result.append(char)
                escape_next = False
                continue

            if char == '\\':
                escape_next = True
                result.append(char)
                continue

            # Track string boundaries
            if char == '"' and not escape_next:
                in_string = not in_string
                result.append(char)
                continue

            # Inside strings: escape control characters
            if in_string and ord(char) < 32:
                if char == '\n':
                    result.append('\\n')
                elif char == '\t':
                    result.append('\\t')
                elif char == '\r':
                    result.append('\\r')
                elif char == '\b':
                    result.append('\\b')
                elif char == '\f':
                    result.append('\\f')
                else:
                    # Remove other control characters silently
                    continue
            else:
                # Outside strings: keep as-is
                result.append(char)

        cleaned = ''.join(result)

        # Double-check: remove any remaining null bytes
        cleaned = cleaned.replace('\x00', '')

        logger.debug(f"Control character sanitization complete: {len(text)} -> {len(cleaned)} chars")
        return cleaned

    @staticmethod
    def _fix_syntax_errors(text: str) -> str:
        """Fix common JSON syntax errors without over-engineering."""
        # Fix trailing commas before closing braces/brackets
        text = re.sub(r',\s*}', '}', text)
        text = re.sub(r',\s*]', ']', text)

        # Fix missing commas between elements (basic patterns)
        text = re.sub(r'}\s*{', '}, {', text)
        text = re.sub(r']\s*\[', '], [', text)
        text = re.sub(r'}\s*\[', '}, [', text)

        # Strip C-style comments, but only outside string values -
        # otherwise a URL like "http://..." in a legitimate payload gets
        # truncated at the second slash, wiping the rest of the line.
        text = JsonSanitizer._strip_comments_outside_strings(text)

        # Remove duplicate commas
        text = re.sub(r',\s*,', ',', text)

        logger.debug("Syntax error fixes applied")
        return text

    @staticmethod
    def _strip_comments_outside_strings(text: str) -> str:
        """Remove // line comments and /* */ block comments, respecting string boundaries."""
        result: list[str] = []
        i = 0
        n = len(text)
        in_string = False
        escape_next = False

        while i < n:
            char = text[i]

            if escape_next:
                result.append(char)
                escape_next = False
                i += 1
                continue

            if char == '\\':
                escape_next = True
                result.append(char)
                i += 1
                continue

            if char == '"':
                in_string = not in_string
                result.append(char)
                i += 1
                continue

            if not in_string and char == '/' and i + 1 < n:
                next_char = text[i + 1]
                if next_char == '/':
                    # Line comment: skip to next newline (which _fix_control_characters
                    # already escaped to the two-char sequence "\\n", so we look for
                    # a real newline - if the whole text is one line, consume to end).
                    i += 2
                    while i < n and text[i] != '\n':
                        i += 1
                    continue
                if next_char == '*':
                    # Block comment: skip to */
                    i += 2
                    while i + 1 < n and not (text[i] == '*' and text[i + 1] == '/'):
                        i += 1
                    i += 2
                    continue

            result.append(char)
            i += 1

        return ''.join(result)

    @staticmethod
    def _attempt_parsing(text: str) -> Optional[Dict[str, Any]]:
        """Try parsing with increasing leniency."""
        last_error = None
        
        # Attempt 1: Standard parsing
        try:
            return json.loads(text)
        except json.JSONDecodeError as e:
            last_error = e
            logger.debug(f"Standard parsing failed: {e}")

        # Attempt 2: Lenient parsing - remove control chars
        try:
            # Remove control chars except newline, tab, carriage return
            control_char_map = {i: None for i in range(32) if i not in [10, 13, 9]}
            cleaned = text.translate(control_char_map)
            return json.loads(cleaned)
        except json.JSONDecodeError as e:
            last_error = e
            logger.debug(f"Lenient parsing failed: {e}")

        # Attempt 3: Remove all whitespace outside strings and retry
        try:
            compacted = JsonSanitizer._minify_json(text)
            return json.loads(compacted)
        except json.JSONDecodeError as e:
            last_error = e
            logger.debug(f"Minified parsing failed: {e}")
        
        # Attempt 4: Try to fix specific JSON errors based on error message
        if last_error:
            try:
                fixed = JsonSanitizer._fix_specific_error(text, last_error)
                if fixed != text:
                    return json.loads(fixed)
            except json.JSONDecodeError as e:
                logger.debug(f"Specific error fix failed: {e}")

        return None
    
    @staticmethod
    def _fix_specific_error(text: str, error: json.JSONDecodeError) -> str:
        """Try to fix specific JSON errors based on the error message."""
        error_msg = str(error)
        pos = error.pos if hasattr(error, 'pos') else 0
        
        # Get context around error position
        start = max(0, pos - 50)
        end = min(len(text), pos + 50)
        context = text[start:end]
        logger.debug(f"Error context around pos {pos}: ...{context}...")
        
        # Fix: Missing comma between elements
        if "Expecting ',' delimiter" in error_msg or "Expecting property name" in error_msg:
            # Try inserting a comma before the error position
            # Look backwards for a closing quote, brace, or bracket
            for i in range(pos - 1, max(0, pos - 20), -1):
                if text[i] in '"}]' and i + 1 < len(text) and text[i + 1] not in ',}]':
                    # Check if next non-whitespace is a quote or brace
                    rest = text[i + 1:].lstrip()
                    if rest and rest[0] in '"{[':
                        # Insert comma
                        fixed = text[:i + 1] + ',' + text[i + 1:]
                        logger.debug(f"Inserted comma at position {i + 1}")
                        return fixed
        
        # Fix: Unexpected character (often a control char or bad escape)
        if "Unexpected" in error_msg or "Invalid" in error_msg:
            # Remove the problematic character
            if 0 <= pos < len(text):
                fixed = text[:pos] + text[pos + 1:]
                logger.debug(f"Removed character at position {pos}")
                return fixed
        
        return text

    @staticmethod
    def _minify_json(text: str) -> str:
        """Remove unnecessary whitespace outside string values."""
        result = []
        in_string = False
        escape_next = False

        for char in text:
            if escape_next:
                result.append(char)
                escape_next = False
                continue

            if char == '\\':
                escape_next = True
                result.append(char)
                continue

            if char == '"' and not escape_next:
                in_string = not in_string
                result.append(char)
                continue

            # Outside strings: skip whitespace (space, newline, tab)
            if not in_string and char in ' \n\t\r':
                continue

            result.append(char)

        return ''.join(result)

    @staticmethod
    def _try_merge_top_level_objects(text: str) -> Optional[Dict[str, Any]]:
        """Walk `text` tracking brace depth, parse each top-level `{...}`
        span as JSON, and return the merged dict (last-write-wins on key
        conflicts). Returns None if no complete object was found.

        Factored out of _extract_partial_json so the dispatcher below is
        easier to read. Behavior is byte-for-byte identical: same brace-
        depth logic, same escape check, same silent `except:` on parse
        failure, same merge order, same log line on success.
        """
        objects = []
        depth = 0
        start = -1

        for i, char in enumerate(text):
            if char == '{' and (i == 0 or text[i-1] != '\\'):
                if depth == 0:
                    start = i
                depth += 1
            elif char == '}' and (i == 0 or text[i-1] != '\\'):
                depth -= 1
                if depth == 0 and start >= 0:
                    try:
                        obj = json.loads(text[start:i+1])
                        objects.append(obj)
                    except:
                        pass

        if not objects:
            return None

        # Merge objects (last one wins on key conflicts)
        merged = {}
        for obj in objects:
            merged.update(obj)
        logger.info(f"Partial extraction succeeded: {len(objects)} objects merged")
        return merged

    @staticmethod
    def _extract_partial_json(text: str) -> Optional[Dict[str, Any]]:
        """
        Extract whatever valid JSON fragments we can find.
        Enhanced version that handles complex nested structures better.
        """
        logger.info("Attempting partial JSON extraction")

        # First, try to find and parse top-level objects via brace-depth walk.
        merged = JsonSanitizer._try_merge_top_level_objects(text)
        if merged is not None:
            return merged

        # If that didn't work, try regex-based extraction (more robust)
        # Try to detect what type of JSON we're dealing with
        is_simulation = '"execution_steps"' in text or '"prerequisites"' in text
        is_extraction = '"iocs"' in text or '"ttps"' in text or '"attack_chain"' in text
        is_faa = '"items"' in text and ('"classification"' in text or '"mitre_technique"' in text)
        
        if is_faa:
            # FAA (Findings and Actions) format
            result = {
                "items": [],
                "parsing_notes": "Extracted via partial parsing"
            }
            
            # Try to extract items array
            items_start = text.find('"items"')
            if items_start > 0:
                bracket_start = text.find('[', items_start)
                if bracket_start > 0:
                    # Extract item objects
                    remaining = text[bracket_start + 1:]
                    item_objects = []
                    depth = 0
                    current_item = ""
                    in_string = False
                    escape_next = False
                    
                    for char in remaining:
                        if escape_next:
                            escape_next = False
                            current_item += char
                            continue
                        
                        if char == '\\':
                            escape_next = True
                            current_item += char
                            continue
                        
                        if char == '"' and not escape_next:
                            in_string = not in_string
                            current_item += char
                            continue
                        
                        if not in_string:
                            if char == '{':
                                if depth == 0:
                                    current_item = "{"
                                else:
                                    current_item += char
                                depth += 1
                            elif char == '}':
                                current_item += char
                                depth -= 1
                                if depth == 0:
                                    item_objects.append(current_item)
                                    current_item = ""
                            elif char == ']' and depth == 0:
                                break
                            else:
                                if depth > 0:
                                    current_item += char
                        else:
                            current_item += char
                        
                        if len(current_item) > 5000:
                            break
                    
                    # Parse each item
                    for item_obj in item_objects:
                        try:
                            # Try direct parse first
                            item = json.loads(item_obj)
                            result["items"].append(item)
                        except json.JSONDecodeError:
                            # Extract fields manually
                            item = {}
                            
                            # Classification
                            class_match = re.search(r'"classification"\s*:\s*"([^"]+)"', item_obj)
                            if class_match:
                                item["classification"] = class_match.group(1)
                            
                            # Content
                            content_match = re.search(r'"content"\s*:\s*"([^"]+)"', item_obj)
                            if content_match:
                                item["content"] = content_match.group(1)
                            
                            # MITRE technique
                            mitre_match = re.search(r'"mitre_technique"\s*:\s*"([^"]+)"', item_obj)
                            if mitre_match:
                                item["mitre_technique"] = mitre_match.group(1)
                            elif '"mitre_technique"' in item_obj and 'null' in item_obj:
                                item["mitre_technique"] = None
                            
                            # MITRE tactic
                            tactic_match = re.search(r'"mitre_tactic"\s*:\s*"([^"]+)"', item_obj)
                            if tactic_match:
                                item["mitre_tactic"] = tactic_match.group(1)
                            
                            # Severity
                            sev_match = re.search(r'"severity"\s*:\s*"([^"]+)"', item_obj)
                            if sev_match:
                                item["severity"] = sev_match.group(1)
                            
                            # Confidence score
                            conf_match = re.search(r'"confidence_score"\s*:\s*([\d.]+)', item_obj)
                            if conf_match:
                                item["confidence_score"] = float(conf_match.group(1))
                            
                            # Source
                            source_match = re.search(r'"source"\s*:\s*"([^"]+)"', item_obj)
                            if source_match:
                                item["source"] = source_match.group(1)
                            
                            # Output (may contain special chars)
                            output_match = re.search(r'"output"\s*:\s*"((?:[^"\\]|\\.)*)"', item_obj)
                            if output_match:
                                item["output"] = output_match.group(1)
                            
                            # Notes
                            notes_match = re.search(r'"notes"\s*:\s*"([^"]*)"', item_obj)
                            if notes_match:
                                item["notes"] = notes_match.group(1)
                            
                            if item.get("classification") or item.get("content"):
                                result["items"].append(item)
            
            if result["items"]:
                logger.info(f"Extracted {len(result['items'])} FAA items via partial parsing")
                return result
        
        elif is_extraction:
            # Threat intelligence extraction format
            result = {
                "iocs": {},
                "ttps": [],
                "attack_chain": [],
                "tools": [],
                "timeline": [],
                "threat_actors": [],
                "infrastructure": {}
            }
            
            # Try to extract IOCs
            iocs_match = re.search(r'"iocs"\s*:\s*\{', text)
            if iocs_match:
                # Try to extract IOC types
                for ioc_type in ["ips", "domains", "urls", "hashes", "emails", "file_paths"]:
                    pattern = f'"{ioc_type}"\\s*:\\s*\\[(.*?)\\]'
                    type_match = re.search(pattern, text, re.DOTALL)
                    if type_match:
                        ioc_list = []
                        # Extract IOC objects
                        ioc_objects = re.findall(r'\{[^}]*"value"[^}]*\}', type_match.group(1), re.DOTALL)
                        for ioc_obj in ioc_objects:
                            value_match = re.search(r'"value"\s*:\s*"([^"]+)"', ioc_obj)
                            context_match = re.search(r'"context"\s*:\s*"([^"]+)"', ioc_obj)
                            if value_match:
                                ioc_list.append({
                                    "value": value_match.group(1),
                                    "context": context_match.group(1) if context_match else ""
                                })
                        if ioc_list:
                            result["iocs"][ioc_type] = ioc_list
            
            # Try to extract TTPs
            ttps_match = re.search(r'"ttps"\s*:\s*\[(.*?)\]', text, re.DOTALL)
            if ttps_match:
                ttps = re.findall(r'"([^"]+)"', ttps_match.group(1))
                result["ttps"] = list(set(ttps))  # Deduplicate
            
            # Try to extract tools
            tools_match = re.search(r'"tools"\s*:\s*\[(.*?)\]', text, re.DOTALL)
            if tools_match:
                tools = re.findall(r'"([^"]+)"', tools_match.group(1))
                result["tools"] = list(set(tools))  # Deduplicate
            
            # Try to extract threat actors
            actors_match = re.search(r'"threat_actors"\s*:\s*\[(.*?)\]', text, re.DOTALL)
            if actors_match:
                actors = re.findall(r'"([^"]+)"', actors_match.group(1))
                result["threat_actors"] = list(set(actors))  # Deduplicate
            
            # Check if we extracted anything meaningful
            has_data = (
                result.get("iocs") and any(result["iocs"].values()) or
                result.get("ttps") or
                result.get("tools") or
                result.get("threat_actors")
            )
            
            if has_data:
                logger.info(f"Extracted partial extraction data: {len(result.get('ttps', []))} TTPs, {len(result.get('tools', []))} tools")
                return result
        else:
            # Simulation report format (default)
            result = {
                "prerequisites": [],
                "setup_instructions": "",
                "execution_steps": [],
                "difficulty_level": "intermediate",
                "estimated_duration": "Unknown",
                "risk_level": "medium"
            }

        # Try to extract prerequisites
        prereq_match = re.search(r'"prerequisites"\s*:\s*\[(.*?)\]', text, re.DOTALL)
        if prereq_match:
            prereq_text = prereq_match.group(1)
            # Extract quoted strings
            prereqs = re.findall(r'"([^"]+)"', prereq_text)
            result["prerequisites"] = prereqs

        # Try to extract setup_instructions - handle multiline and escaped content
        setup_start = text.find('"setup_instructions"')
        if setup_start > 0:
            # Find the colon after setup_instructions
            colon_pos = text.find(':', setup_start)
            if colon_pos > 0:
                # Find the opening quote
                quote_start = text.find('"', colon_pos)
                if quote_start > 0:
                    # Extract the string content (handling escaped quotes and newlines)
                    setup_content = ""
                    i = quote_start + 1
                    escaped = False
                    while i < len(text):
                        char = text[i]
                        if escaped:
                            if char == 'n':
                                setup_content += '\n'
                            elif char == 't':
                                setup_content += '\t'
                            elif char == 'r':
                                setup_content += '\r'
                            elif char == '\\':
                                setup_content += '\\'
                            elif char == '"':
                                setup_content += '"'
                            else:
                                setup_content += char
                            escaped = False
                        elif char == '\\':
                            escaped = True
                        elif char == '"':
                            # Check if this is the closing quote (not inside a string)
                            # Look ahead to see if there's a comma or closing brace
                            next_chars = text[i+1:i+10].strip()
                            if next_chars.startswith(',') or next_chars.startswith('}') or next_chars.startswith(']'):
                                break
                            setup_content += char
                        else:
                            setup_content += char
                        i += 1

                    if setup_content:
                        result["setup_instructions"] = setup_content

        # Try to extract execution_steps (partial) - more robust pattern
        steps_start = text.find('"execution_steps"')
        if steps_start > 0:
            # Find the opening bracket
            bracket_start = text.find('[', steps_start)
            if bracket_start > 0:
                # Extract everything from bracket to end (or find closing bracket)
                remaining = text[bracket_start + 1:]

                # Try to find complete step objects
                step_objects = []
                depth = 0
                current_step = ""
                in_string = False
                escape_next = False

                for i, char in enumerate(remaining):
                    if escape_next:
                        escape_next = False
                        current_step += char
                        continue

                    if char == '\\':
                        escape_next = True
                        current_step += char
                        continue

                    if char == '"' and not escape_next:
                        in_string = not in_string
                        current_step += char
                        continue

                    if not in_string:
                        if char == '{':
                            if depth == 0:
                                current_step = "{"
                            else:
                                current_step += char
                            depth += 1
                        elif char == '}':
                            current_step += char
                            depth -= 1
                            if depth == 0:
                                # Complete step object found
                                step_objects.append(current_step)
                                current_step = ""
                        else:
                            if depth > 0:
                                current_step += char
                    else:
                        current_step += char

                    # Safety limit
                    if len(current_step) > 10000:
                        break

                # Parse each step object
                for step_obj in step_objects:
                    try:
                        # Extract step_number
                        step_num_match = re.search(r'"step_number"\s*:\s*(\d+)', step_obj)
                        step_num = int(step_num_match.group(1)) if step_num_match else len(result["execution_steps"]) + 1

                        # Extract title
                        title_match = re.search(r'"title"\s*:\s*"([^"]+)"', step_obj)
                        title = title_match.group(1) if title_match else f"Step {step_num}"

                        # Extract description
                        desc_match = re.search(r'"description"\s*:\s*"([^"]+)"', step_obj)
                        desc = desc_match.group(1) if desc_match else ""

                        # Extract commands
                        commands = []
                        cmd_match = re.search(r'"commands"\s*:\s*\[(.*?)\]', step_obj, re.DOTALL)
                        if cmd_match:
                            commands = re.findall(r'"([^"]+)"', cmd_match.group(1))

                        # Extract expected_result
                        expected_match = re.search(r'"expected_result"\s*:\s*"([^"]+)"', step_obj)
                        expected = expected_match.group(1) if expected_match else ""

                        # Extract troubleshooting
                        trouble_match = re.search(r'"troubleshooting"\s*:\s*"([^"]+)"', step_obj)
                        troubleshooting = trouble_match.group(1) if trouble_match else ""

                        # Extract warnings
                        warnings = []
                        warnings_match = re.search(r'"warnings"\s*:\s*\[(.*?)\]', step_obj, re.DOTALL)
                        if warnings_match:
                            warnings = re.findall(r'"([^"]+)"', warnings_match.group(1))

                        result["execution_steps"].append({
                            "step_number": step_num,
                            "title": title,
                            "description": desc,
                            "commands": commands,
                            "expected_result": expected,
                            "troubleshooting": troubleshooting,
                            "warnings": warnings
                        })
                    except Exception as e:
                        logger.debug(f"Failed to parse step object: {e}")
                        continue

        # Extract difficulty and risk
        diff_match = re.search(r'"difficulty_level"\s*:\s*"([^"]+)"', text)
        if diff_match:
            result["difficulty_level"] = diff_match.group(1)

        risk_match = re.search(r'"risk_level"\s*:\s*"([^"]+)"', text)
        if risk_match:
            result["risk_level"] = risk_match.group(1)

        duration_match = re.search(r'"estimated_duration"\s*:\s*"([^"]+)"', text)
        if duration_match:
            result["estimated_duration"] = duration_match.group(1)

        # Only return if we extracted something meaningful
        if result.get("execution_steps") or result.get("setup_instructions"):
            logger.info(f"Extracted partial JSON: {len(result['execution_steps'])} steps, {len(result['prerequisites'])} prerequisites")
            return result

        return None

    @staticmethod
    def _emergency_fallback() -> Dict[str, Any]:
        """Return a minimal valid structure when everything fails."""
        logger.critical("EMERGENCY FALLBACK: Returning empty structure")
        return {
            # FAA-compatible fields
            "items": [],
            "parsing_notes": "Emergency fallback - JSON parsing completely failed",
            # Simulation-compatible fields  
            "title": "Parsing Error - Emergency Fallback",
            "description": "The LLM response could not be parsed. Manual review required.",
            "execution_steps": [],
            "prerequisites": [],
            "setup_instructions": "ERROR: See logs for details",
            "difficulty_level": "intermediate",
            "estimated_duration": "Unknown",
            "risk_level": "medium",
            "_fallback": True
        }


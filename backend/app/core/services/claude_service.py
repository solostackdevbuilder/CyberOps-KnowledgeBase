"""
Claude API service for querying session data with context.
Implements BaseLLM interface.
Uses AsyncAnthropic for proper async support in uvicorn/FastAPI.
"""
import base64
import json
import logging
from pathlib import Path
from typing import Dict, List, Optional

import httpx
import time
from anthropic import AsyncAnthropic, APIError, APIConnectionError, APITimeoutError, APIStatusError, AuthenticationError, RateLimitError, BadRequestError, NotFoundError, PermissionDeniedError

from app.config import settings
from app.core.models import Session
from app.modules.red_team.prompts import VISION_EXTRACTION_PROMPT
from app.core.services.base_llm import BaseLLM, ImageExtractionResult
from app.core.services.privacy_transform import PrivacyTransformService
from app.core.storage.base_store import BaseStore

logger = logging.getLogger(__name__)


class ClaudeService(BaseLLM):
    """Service for interacting with Claude API to query session data."""
    
    def __init__(self, api_key: str, model_name: str = "claude-sonnet-4-5-20250929", storage: Optional[BaseStore] = None):
        """
        Initialize Claude service.
        
        Args:
            api_key: Anthropic API key
            model_name: Claude model name to use
            storage: Optional storage instance for loading sessions (for backward compatibility)
            
        Raises:
            ValueError: If API key is not configured
        """
        if not api_key or api_key == "your-key-here":
            raise ValueError(
                "ANTHROPIC_API_KEY is not configured. Please set it in your .env file."
            )
        # Configure with retries and generous timeouts
        # max_retries handles transient "Server disconnected" errors
        self.client = AsyncAnthropic(
            api_key=api_key,
            max_retries=3,
            timeout=httpx.Timeout(300.0, connect=30.0),
        )
        self.model_name = model_name
        self.storage = storage
        self.max_context_sessions = getattr(settings, "max_context_sessions", 20)
        self.privacy_transform = PrivacyTransformService()
    
    async def query(
        self,
        question: str,
        context: str,
        scope: str = "all",
        operation_name: Optional[str] = None,
        max_tokens: int = 4096,
        system_prompt: Optional[str] = None
    ) -> str:
        """
        Query Claude with a question and context.
        
        Args:
            question: User's question/query
            context: Context string to provide to Claude
            scope: Query scope - "all" for all operations, "single" for one operation
            operation_name: Name of the operation when scope is "single"
            system_prompt: Optional custom system prompt override
            
        Returns:
            Claude's response as a string
            
        Raises:
            RuntimeError: If Claude API call fails
        """
        try:
            # Use custom system prompt if provided, otherwise build scope-aware default
            if system_prompt is not None:
                effective_system_prompt = system_prompt
            elif scope == "all":
                effective_system_prompt = """You are an AI assistant helping with a red teaming knowledge base. 
You have access to terminal session logs, screenshots, and metadata from penetration testing and security research sessions across MULTIPLE operations.

When answering queries:
- Always mention which operation findings belong to so the operator understands the context
- Format source references as: [Operation Name] Session Title
- If findings span multiple operations, provide a summary breakdown by operation
- Structure your response with operation-level summaries when relevant

Example response structure:
[Direct answer to question]

Operation Breakdown:
- Operation ACME: [summary]
- Operation Beta: [summary]

Sources:
[list sources with operation names]

Be precise and cite specific sessions when relevant."""
            else:
                # Single operation scope
                effective_system_prompt = f"""You are an AI assistant helping with a red teaming knowledge base. 
You have access to terminal session logs, screenshots, and metadata from penetration testing and security research sessions from a SINGLE operation: {operation_name or 'the selected operation'}.

When answering queries:
- Focus on session-level details since all sessions are from the same operation
- Format source references as: Session Title (timestamp)
- You don't need to repeat the operation name in your answers (the operator already knows they're querying this specific operation)
- Provide detailed session-by-session analysis when relevant

Be precise and cite specific sessions when relevant."""
            
            sanitized_context = (await self.privacy_transform.sanitize_for_llm(context, target="context")).text
            sanitized_question = (await self.privacy_transform.sanitize_for_llm(question, target="question")).text
            sanitized_system_prompt = (
                (await self.privacy_transform.sanitize_for_llm(effective_system_prompt, target="context")).text
                if effective_system_prompt
                else effective_system_prompt
            )

            user_message = f"""Context from knowledge base sessions:

{sanitized_context}

---

User Question: {sanitized_question}

Please provide a helpful answer based on the context above."""
            
            # Call Claude API with retry logic for RemoteProtocolError
            prompt_len = len(user_message)
            max_attempts = 3
            last_error = None
            
            for attempt in range(1, max_attempts + 1):
                try:
                    print(f"[Claude] Attempt {attempt}/{max_attempts}: Connecting to API... (model={self.model_name}, prompt_length={prompt_len} chars)")
                    start_time = time.time()
                    
                    message = await self.client.messages.create(
                        model=self.model_name,
                        max_tokens=max_tokens,
                        system=sanitized_system_prompt,
                        messages=[
                            {
                                "role": "user",
                                "content": user_message
                            }
                        ]
                    )
                    
                    elapsed = time.time() - start_time
                    print(f"[Claude] Response received in {elapsed:.1f}s (stop_reason={message.stop_reason}, usage: input={message.usage.input_tokens}, output={message.usage.output_tokens})")
                    break  # Success
                    
                except APIConnectionError as e:
                    last_error = e
                    cause_chain = []
                    cause = e.__cause__
                    while cause:
                        cause_chain.append(f"{type(cause).__name__}: {cause}")
                        cause = cause.__cause__
                    cause_detail = " -> ".join(cause_chain) if cause_chain else "No detail"
                    
                    if attempt < max_attempts:
                        wait_time = attempt * 2  # 2s, 4s
                        print(f"[Claude] Attempt {attempt} failed: {cause_detail}")
                        print(f"[Claude] Retrying in {wait_time}s... (creating fresh client)")
                        import asyncio
                        await asyncio.sleep(wait_time)
                        # Create a fresh client to get a clean connection pool
                        self.client = AsyncAnthropic(
                            api_key=self.client.api_key,
                            max_retries=2,
                            timeout=httpx.Timeout(300.0, connect=30.0),
                        )
                    else:
                        print(f"[Claude] All {max_attempts} attempts failed: {cause_detail}")
                        raise
            else:
                # All attempts failed
                raise last_error  # type: ignore
            
            # Extract response text
            response_text = ""
            for content_block in message.content:
                if content_block.type == "text":
                    response_text += content_block.text
            
            if await self.privacy_transform.should_restore_output():
                response_text = (await self.privacy_transform.restore_for_ui(response_text)).text

            print(f"[Claude] Response extracted ({len(response_text)} chars)")
            return response_text
            
        except AuthenticationError as e:
            raise RuntimeError(
                f"Claude authentication failed (HTTP 401): Invalid or expired API key. "
                f"Please check your Anthropic API key in Settings. Detail: {e.message}"
            ) from e
        except PermissionDeniedError as e:
            raise RuntimeError(
                f"Claude permission denied (HTTP 403): Your API key may not have access to model '{self.model_name}'. "
                f"Detail: {e.message}"
            ) from e
        except NotFoundError as e:
            raise RuntimeError(
                f"Claude model not found (HTTP 404): Model '{self.model_name}' does not exist or is not available. "
                f"Try selecting a different model in Settings. Detail: {e.message}"
            ) from e
        except RateLimitError as e:
            raise RuntimeError(
                f"Claude rate limit exceeded (HTTP 429): Too many requests. "
                f"Please wait a moment and try again. Detail: {e.message}"
            ) from e
        except BadRequestError as e:
            raise RuntimeError(
                f"Claude bad request (HTTP 400): The request was malformed. "
                f"This may be caused by an overly long input. Detail: {e.message}"
            ) from e
        except APITimeoutError as e:
            raise RuntimeError(
                f"Claude API request timed out: The request took too long to complete. "
                f"This could be a network issue or the API may be under heavy load. "
                f"Check your internet connection and try again."
            ) from e
        except APIConnectionError as e:
            # Dig into the root cause for actionable detail
            cause_chain = []
            cause = e.__cause__
            while cause:
                cause_chain.append(f"{type(cause).__name__}: {cause}")
                cause = cause.__cause__
            cause_detail = " -> ".join(cause_chain) if cause_chain else "No additional detail"
            print(f"[Claude] CONNECTION ERROR. Root cause chain: {cause_detail}")
            raise RuntimeError(
                f"Claude API connection error: Could not connect to Anthropic API (api.anthropic.com). "
                f"Root cause: {cause_detail}"
            ) from e
        except APIStatusError as e:
            raise RuntimeError(
                f"Claude API error (HTTP {e.status_code}): {e.message}"
            ) from e
        except APIError as e:
            raise RuntimeError(f"Claude API error: {e.message}") from e
        except Exception as e:
            raise RuntimeError(f"Failed to query Claude (unexpected error): {type(e).__name__}: {e}") from e
    
    async def extract_metadata(self, terminal_content: str) -> Dict[str, List[str]]:
        """
        Extract metadata from terminal content using Claude API.
        
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
            
            sanitized_terminal_content = (
                await self.privacy_transform.sanitize_for_llm(terminal_content, target="context")
            ).text

            user_message = f"""Terminal session content:

{sanitized_terminal_content}

---

Extract the targets, tools, and findings from this session. Return only valid JSON with the structure:
{{"targets": [], "tools": [], "findings": []}}"""
            
            # Call Claude API using native async client
            message = await self.client.messages.create(
                model=self.model_name,
                max_tokens=2048,
                system=system_prompt,
                messages=[
                    {
                        "role": "user",
                        "content": user_message
                    }
                ]
            )
            
            # Extract response text
            response_text = ""
            for content_block in message.content:
                if content_block.type == "text":
                    response_text += content_block.text
            
            # Parse JSON response
            if await self.privacy_transform.should_restore_output():
                response_text = (await self.privacy_transform.restore_for_ui(response_text)).text

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
            
        except AuthenticationError as e:
            raise RuntimeError(f"Claude authentication failed: {e.message}") from e
        except APIConnectionError as e:
            raise RuntimeError(
                f"Claude API connection error during metadata extraction: Could not reach api.anthropic.com. "
                f"Detail: {e.message}"
            ) from e
        except APIStatusError as e:
            raise RuntimeError(f"Claude API error (HTTP {e.status_code}): {e.message}") from e
        except APIError as e:
            raise RuntimeError(f"Claude API error: {e.message}") from e
        except Exception as e:
            raise RuntimeError(f"Failed to extract metadata ({type(e).__name__}): {e}") from e
    
    async def test_connection(self) -> bool:
        """
        Test connection to Claude API.
        
        Returns:
            True if connection is successful, False otherwise
            
        Raises:
            RuntimeError: With detailed error info if connection fails
        """
        try:
            # Make a simple API call to test connection
            await self.client.messages.create(
                model=self.model_name,
                max_tokens=10,
                messages=[
                    {
                        "role": "user",
                        "content": "test"
                    }
                ]
            )
            return True
        except AuthenticationError as e:
            logger.error(f"Claude connection test failed - authentication error: {e.message}")
            return False
        except APIConnectionError as e:
            logger.error(f"Claude connection test failed - cannot reach API: {e.message}")
            return False
        except NotFoundError as e:
            logger.error(f"Claude connection test failed - model '{self.model_name}' not found: {e.message}")
            return False
        except Exception as e:
            logger.error(f"Claude connection test failed ({type(e).__name__}): {e}")
            return False
    
    def supports_vision(self) -> bool:
        """
        Check if Claude service supports vision.
        Claude Sonnet and Opus models support vision.
        
        Returns:
            True (Claude models support vision)
        """
        return True
    
    async def extract_from_image(self, image_path: str) -> ImageExtractionResult:
        """
        Extract text and analyze an image using Claude vision API.
        
        Args:
            image_path: Path to the image file
            
        Returns:
            ImageExtractionResult with extracted text and analysis
            
        Raises:
            RuntimeError: If extraction fails
        """
        try:
            # Read and encode image
            image_file = Path(image_path)
            if not image_file.exists():
                raise FileNotFoundError(f"Image file not found: {image_path}")
            
            # Read image file
            with open(image_file, "rb") as f:
                image_data = f.read()
            
            # Detect image type
            image_ext = image_file.suffix.lower()
            mime_type_map = {
                ".jpg": "image/jpeg",
                ".jpeg": "image/jpeg",
                ".png": "image/png",
                ".gif": "image/gif",
                ".webp": "image/webp"
            }
            media_type = mime_type_map.get(image_ext, "image/png")
            
            # Encode to base64
            base64_image = base64.b64encode(image_data).decode("utf-8")
            
            # Build message content with image
            message_content = [
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": media_type,
                        "data": base64_image
                    }
                },
                {
                    "type": "text",
                    "text": VISION_EXTRACTION_PROMPT
                }
            ]
            
            # Call Claude API using native async client
            message = await self.client.messages.create(
                model=self.model_name,
                max_tokens=4096,
                messages=[
                    {
                        "role": "user",
                        "content": message_content
                    }
                ]
            )
            
            # Extract response text
            response_text = ""
            for content_block in message.content:
                if content_block.type == "text":
                    response_text += content_block.text
            
            # Parse response
            extracted_text, analysis = self._parse_vision_response(response_text)
            
            return ImageExtractionResult(
                extracted_text=extracted_text,
                analysis=analysis,
                confidence=None
            )
            
        except FileNotFoundError as e:
            raise RuntimeError(f"Image file not found: {e}") from e
        except AuthenticationError as e:
            raise RuntimeError(f"Claude authentication failed: {e.message}") from e
        except APIConnectionError as e:
            raise RuntimeError(
                f"Claude API connection error during image extraction: Could not reach api.anthropic.com. "
                f"Detail: {e.message}"
            ) from e
        except APIStatusError as e:
            raise RuntimeError(f"Claude API error (HTTP {e.status_code}): {e.message}") from e
        except APIError as e:
            raise RuntimeError(f"Claude API error: {e.message}") from e
        except Exception as e:
            raise RuntimeError(f"Failed to extract from image ({type(e).__name__}): {e}") from e
    
    def _parse_vision_response(self, response_text: str) -> tuple[str, str]:
        """
        Parse vision extraction response into extracted_text and analysis.
        
        Args:
            response_text: Raw response from Claude
            
        Returns:
            Tuple of (extracted_text, analysis)
        """
        response_text = response_text.strip()
        
        # Try to find EXTRACTED_TEXT and ANALYSIS markers
        extracted_text = ""
        analysis = ""
        
        if "EXTRACTED_TEXT:" in response_text and "ANALYSIS:" in response_text:
            # Split by markers
            parts = response_text.split("EXTRACTED_TEXT:", 1)
            if len(parts) > 1:
                text_part = parts[1].split("ANALYSIS:", 1)
                extracted_text = text_part[0].strip()
                if len(text_part) > 1:
                    analysis = text_part[1].strip()
        else:
            # If markers not found, try to intelligently split
            # Look for common patterns
            lines = response_text.split("\n")
            in_extracted = False
            in_analysis = False
            extracted_lines = []
            analysis_lines = []
            
            for line in lines:
                line_lower = line.lower()
                if "extracted" in line_lower and "text" in line_lower:
                    in_extracted = True
                    in_analysis = False
                    continue
                elif "analysis" in line_lower:
                    in_extracted = False
                    in_analysis = True
                    continue
                
                if in_extracted:
                    extracted_lines.append(line)
                elif in_analysis:
                    analysis_lines.append(line)
            
            if extracted_lines:
                extracted_text = "\n".join(extracted_lines).strip()
            if analysis_lines:
                analysis = "\n".join(analysis_lines).strip()
            
            # If still no clear split, put everything in extracted_text
            if not extracted_text and not analysis:
                extracted_text = response_text
                analysis = "Image analyzed but no structured response format detected."
        
        return extracted_text, analysis
    
    # Backward compatibility method
    async def query_with_context(self, query: str, session_ids: Optional[List[str]] = None) -> str:
        """
        Query Claude with context from recent or specified sessions.
        This is a convenience method for backward compatibility.
        
        Args:
            query: User's query/question
            session_ids: Optional list of specific session IDs to include in context.
                        If None, uses most recent sessions.
        
        Returns:
            Claude's response as a string
            
        Raises:
            RuntimeError: If storage is not available or Claude API call fails
        """
        if not self.storage:
            raise RuntimeError("Storage is required for query_with_context method")
        
        try:
            # Load sessions for context
            if session_ids:
                # Load specific sessions
                sessions = []
                for session_id in session_ids[:self.max_context_sessions]:
                    session = await self.storage.get_session(session_id)
                    if session:
                        sessions.append(session)
            else:
                # Load most recent sessions
                all_sessions = await self.storage.list_sessions()
                sessions = all_sessions[:self.max_context_sessions]
                # Load full terminal content for these sessions
                full_sessions = []
                for session in sessions:
                    full_session = await self.storage.get_session(session.id)
                    if full_session:
                        full_sessions.append(full_session)
                sessions = full_sessions
            
            # Build context from sessions
            context = self._build_context(sessions)
            
            # Use the base query method
            return await self.query(query, context)
            
        except Exception as e:
            raise RuntimeError(f"Failed to query with context: {e}") from e
    
    def _build_context(self, sessions: List[Session]) -> str:
        """
        Build a formatted context string from session data.
        
        Args:
            sessions: List of sessions to include in context
            
        Returns:
            Formatted context string
        """
        if not sessions:
            return "No sessions available in the knowledge base."
        
        context_parts = []
        
        for i, session in enumerate(sessions, 1):
            session_context = f"=== Session {i}: {session.title} ===\n"
            session_context += f"ID: {session.id}\n"
            session_context += f"Created: {session.created_at.isoformat()}\n"
            session_context += f"Updated: {session.updated_at.isoformat()}\n"
            
            if session.description:
                session_context += f"Description: {session.description}\n"
            
            if session.tags:
                session_context += f"Tags: {', '.join(session.tags)}\n"
            
            session_context += f"\nTerminal Content:\n{session.terminal_content}\n"
            
            if session.screenshots:
                session_context += f"\nScreenshots ({len(session.screenshots)}):\n"
                for screenshot in session.screenshots:
                    session_context += f"  - {screenshot.filename}"
                    if screenshot.description:
                        session_context += f": {screenshot.description}"
                    session_context += f" ({screenshot.timestamp.isoformat()})\n"
            
            # Add screenshot extractions if available
            if hasattr(session, 'screenshot_extractions') and session.screenshot_extractions:
                session_context += f"\nScreenshot Extractions:\n"
                for extraction in session.screenshot_extractions:
                    if extraction.extracted_text:
                        session_context += f"  - [{extraction.filename}]: {extraction.extracted_text}\n"
                        if extraction.analysis:
                            session_context += f"    Analysis: {extraction.analysis}\n"
            
            session_context += "\n"
            context_parts.append(session_context)
        
        return "\n".join(context_parts)


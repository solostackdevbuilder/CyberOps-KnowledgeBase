"""
OpenAI API service implementation.
Implements BaseLLM interface.
"""
import asyncio
import base64
import json
from pathlib import Path
from typing import Dict, List, Optional

from openai import AsyncOpenAI, APIError

from app.core.models import Session
from app.modules.red_team.prompts import VISION_EXTRACTION_PROMPT
from app.core.services.base_llm import BaseLLM, ImageExtractionResult
from app.core.services.privacy_transform import PrivacyTransformService


class OpenAIService(BaseLLM):
    """Service for interacting with OpenAI API."""
    
    def __init__(self, api_key: str, model_name: str = "gpt-4-turbo-preview", endpoint: str = None):
        """
        Initialize OpenAI service.
        
        Args:
            api_key: OpenAI API key
            model_name: Model name to use (e.g., 'gpt-4-turbo-preview', 'gpt-3.5-turbo')
            endpoint: Optional custom endpoint URL (for OpenAI-compatible APIs)
            
        Raises:
            ValueError: If API key is not configured
        """
        if not api_key:
            raise ValueError("OpenAI API key is required")
        
        self.api_key = api_key
        self.model_name = model_name
        
        # Initialize client
        if endpoint:
            self.client = AsyncOpenAI(api_key=api_key, base_url=endpoint)
        else:
            self.client = AsyncOpenAI(api_key=api_key)
        self.privacy_transform = PrivacyTransformService()
    
    async def extract_metadata(self, terminal_content: str) -> Dict[str, List[str]]:
        """
        Extract metadata from terminal content using OpenAI API.
        
        Args:
            terminal_content: Terminal/command-line session content
            
        Returns:
            Dictionary with keys: targets, tools, findings (each is a list of strings)
            
        Raises:
            RuntimeError: If OpenAI API call fails
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
            
            # Call OpenAI API
            response = await self.client.chat.completions.create(
                model=self.model_name,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_message}
                ],
                max_tokens=2048,
                temperature=0.3
            )
            
            # Extract response text
            response_text = response.choices[0].message.content
            
            if await self.privacy_transform.should_restore_output():
                response_text = (await self.privacy_transform.restore_for_ui(response_text)).text

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
                raise RuntimeError(f"Failed to parse OpenAI response as JSON: {e}. Response: {response_text[:200]}")
            
        except APIError as e:
            raise RuntimeError(f"OpenAI API error: {e.message}") from e
        except Exception as e:
            raise RuntimeError(f"Failed to extract metadata: {e}") from e
    
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
        Query OpenAI with a question and context.
        Note: This method accepts context string. For session-based queries with screenshot extractions,
        use query_with_context or build context with screenshot extractions included.
        
        Args:
            question: User's question/query
            context: Context string to provide to OpenAI (should include screenshot extractions if available)
            scope: Query scope - "all" for all operations, "single" for one operation
            operation_name: Name of the operation when scope is "single"
            
        Returns:
            OpenAI's response as a string
            
        Raises:
            RuntimeError: If OpenAI API call fails
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
            
            # Call OpenAI API
            response = await self.client.chat.completions.create(
                model=self.model_name,
                messages=[
                    {"role": "system", "content": sanitized_system_prompt},
                    {"role": "user", "content": user_message}
                ],
                max_tokens=max_tokens,
                temperature=0.7
            )
            
            # Extract response text
            response_text = response.choices[0].message.content
            if response_text is None:
                response_text = ""

            if await self.privacy_transform.should_restore_output():
                response_text = (await self.privacy_transform.restore_for_ui(response_text)).text
            return response_text
            
        except APIError as e:
            raise RuntimeError(f"OpenAI API error: {e.message}") from e
        except Exception as e:
            raise RuntimeError(f"Failed to query OpenAI: {e}") from e
    
    async def test_connection(self) -> bool:
        """
        Test connection to OpenAI API.
        
        Returns:
            True if connection is successful, False otherwise
        """
        try:
            # Make a simple API call to test connection
            await self.client.chat.completions.create(
                model=self.model_name,
                messages=[
                    {"role": "user", "content": "test"}
                ],
                max_tokens=10
            )
            return True
        except Exception:
            return False
    
    def supports_vision(self) -> bool:
        """
        Check if OpenAI service supports vision.
        GPT-4 Vision models support vision.
        
        Returns:
            True if model supports vision, False otherwise
        """
        model_lower = self.model_name.lower()
        return "vision" in model_lower or "gpt-4" in model_lower
    
    async def extract_from_image(self, image_path: str) -> ImageExtractionResult:
        """
        Extract text and analyze an image using OpenAI vision API.
        
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
            
            # Build message with image
            # Use gpt-4-vision-preview or gpt-4-turbo if available
            vision_model = self.model_name
            if "vision" not in vision_model.lower() and "gpt-4" in vision_model.lower():
                # Try to use vision-capable model
                if "turbo" in vision_model.lower():
                    vision_model = "gpt-4-turbo"
                else:
                    vision_model = "gpt-4-vision-preview"
            
            response = await self.client.chat.completions.create(
                model=vision_model,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": VISION_EXTRACTION_PROMPT
                            },
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:{media_type};base64,{base64_image}"
                                }
                            }
                        ]
                    }
                ],
                max_tokens=4096
            )
            
            # Extract response text
            response_text = response.choices[0].message.content or ""
            
            # Parse response
            extracted_text, analysis = self._parse_vision_response(response_text)
            
            return ImageExtractionResult(
                extracted_text=extracted_text,
                analysis=analysis,
                confidence=None
            )
            
        except FileNotFoundError as e:
            raise RuntimeError(f"Image file not found: {e}") from e
        except APIError as e:
            raise RuntimeError(f"OpenAI API error: {e.message}") from e
        except Exception as e:
            raise RuntimeError(f"Failed to extract from image: {e}") from e
    
    def _parse_vision_response(self, response_text: str) -> tuple[str, str]:
        """
        Parse vision extraction response into extracted_text and analysis.
        
        Args:
            response_text: Raw response from OpenAI
            
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


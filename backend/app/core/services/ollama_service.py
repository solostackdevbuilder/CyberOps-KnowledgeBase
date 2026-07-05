"""
Ollama API service implementation.
Implements BaseLLM interface.
"""
import base64
import json
from pathlib import Path
from typing import Dict, List, Optional

import httpx

from app.core.models import Session
from app.modules.red_team.prompts import VISION_EXTRACTION_PROMPT
from app.core.services.base_llm import BaseLLM, ImageExtractionResult
from app.core.services.privacy_transform import PrivacyTransformService


class OllamaService(BaseLLM):
    """Service for interacting with Ollama API."""
    
    def __init__(self, endpoint: str, model_name: str = "llama2"):
        """
        Initialize Ollama service.
        
        Args:
            endpoint: Ollama server endpoint (e.g., 'http://localhost:11434')
            model_name: Model name to use (e.g., 'llama2', 'mistral', 'codellama')
            
        Raises:
            ValueError: If endpoint is not configured
        """
        if not endpoint:
            raise ValueError("Ollama endpoint is required")
        
        # Normalize endpoint (remove trailing slash)
        self.endpoint = endpoint.rstrip("/")
        self.model_name = model_name
        self.client = httpx.AsyncClient(timeout=120.0)  # Longer timeout for local models
        self.privacy_transform = PrivacyTransformService()
    
    async def list_available_models(self) -> List[str]:
        """
        List available models from Ollama server.
        
        Returns:
            List of model names
        """
        try:
            response = await self.client.get(f"{self.endpoint}/api/tags")
            response.raise_for_status()
            data = response.json()
            models = [model["name"] for model in data.get("models", [])]
            return models
        except Exception as e:
            raise RuntimeError(f"Failed to list Ollama models: {e}")
    
    async def extract_metadata(self, terminal_content: str) -> Dict[str, List[str]]:
        """
        Extract metadata from terminal content using Ollama API.
        
        Args:
            terminal_content: Terminal/command-line session content
            
        Returns:
            Dictionary with keys: targets, tools, findings (each is a list of strings)
            
        Raises:
            RuntimeError: If Ollama API call fails
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
            
            # Call Ollama API
            payload = {
                "model": self.model_name,
                "prompt": f"{system_prompt}\n\n{user_message}",
                "stream": False,
                "options": {
                    "temperature": 0.3,
                    "num_predict": 2048
                }
            }
            
            response = await self.client.post(
                f"{self.endpoint}/api/generate",
                json=payload
            )
            response.raise_for_status()
            
            data = response.json()
            response_text = data.get("response", "")
            
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
                raise RuntimeError(f"Failed to parse Ollama response as JSON: {e}. Response: {response_text[:200]}")
            
        except httpx.HTTPError as e:
            raise RuntimeError(f"Ollama API error: {e}") from e
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
        Query Ollama with a question and context.
        Note: This method accepts context string. For session-based queries with screenshot extractions,
        build context with screenshot extractions included.
        
        Args:
            question: User's question/query
            context: Context string to provide to Ollama (should include screenshot extractions if available)
            scope: Query scope - "all" for all operations, "single" for one operation
            operation_name: Name of the operation when scope is "single"
            
        Returns:
            Ollama's response as a string
            
        Raises:
            RuntimeError: If Ollama API call fails
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

            prompt = f"""{sanitized_system_prompt}

Context from knowledge base sessions:

{sanitized_context}

---

User Question: {sanitized_question}

Please provide a helpful answer based on the context above."""
            
            # Call Ollama API
            payload = {
                "model": self.model_name,
                "prompt": prompt,
                "stream": False,
                "options": {
                    "temperature": 0.7,
                    "num_predict": 4096
                }
            }
            
            response = await self.client.post(
                f"{self.endpoint}/api/generate",
                json=payload
            )
            response.raise_for_status()
            
            data = response.json()
            response_text = data.get("response", "")
            if await self.privacy_transform.should_restore_output():
                response_text = (await self.privacy_transform.restore_for_ui(response_text)).text
            return response_text
            
        except httpx.HTTPError as e:
            raise RuntimeError(f"Ollama API error: {e}") from e
        except Exception as e:
            raise RuntimeError(f"Failed to query Ollama: {e}") from e
    
    async def test_connection(self) -> bool:
        """
        Test connection to Ollama API.
        
        Returns:
            True if connection is successful, False otherwise
        """
        try:
            # Try to list models as a connection test
            response = await self.client.get(f"{self.endpoint}/api/tags", timeout=5.0)
            response.raise_for_status()
            return True
        except Exception:
            return False
    
    def supports_vision(self) -> bool:
        """
        Check if Ollama service supports vision.
        Checks if current model name contains vision-related keywords.
        
        Returns:
            True if model supports vision, False otherwise
        """
        model_lower = self.model_name.lower()
        return "llava" in model_lower or "vision" in model_lower or "bakllava" in model_lower
    
    async def extract_from_image(self, image_path: str) -> ImageExtractionResult:
        """
        Extract text and analyze an image using Ollama vision API.
        
        Args:
            image_path: Path to the image file
            
        Returns:
            ImageExtractionResult with extracted text and analysis
            
        Raises:
            RuntimeError: If extraction fails or model doesn't support vision
        """
        if not self.supports_vision():
            raise RuntimeError(f"Model {self.model_name} does not support vision. Use a vision model like llava or bakllava.")
        
        try:
            # Read and encode image
            image_file = Path(image_path)
            if not image_file.exists():
                raise FileNotFoundError(f"Image file not found: {image_path}")
            
            # Read image file
            with open(image_file, "rb") as f:
                image_data = f.read()
            
            # Encode to base64
            base64_image = base64.b64encode(image_data).decode("utf-8")
            
            # Build prompt with image
            prompt = VISION_EXTRACTION_PROMPT
            
            # Call Ollama API with image
            payload = {
                "model": self.model_name,
                "prompt": prompt,
                "images": [base64_image],
                "stream": False,
                "options": {
                    "temperature": 0.3,
                    "num_predict": 4096
                }
            }
            
            response = await self.client.post(
                f"{self.endpoint}/api/generate",
                json=payload
            )
            response.raise_for_status()
            
            data = response.json()
            response_text = data.get("response", "")
            
            # Parse response
            extracted_text, analysis = self._parse_vision_response(response_text)
            
            return ImageExtractionResult(
                extracted_text=extracted_text,
                analysis=analysis,
                confidence=None
            )
            
        except FileNotFoundError as e:
            raise RuntimeError(f"Image file not found: {e}") from e
        except httpx.HTTPError as e:
            raise RuntimeError(f"Ollama API error: {e}") from e
        except Exception as e:
            raise RuntimeError(f"Failed to extract from image: {e}") from e
    
    def _parse_vision_response(self, response_text: str) -> tuple[str, str]:
        """
        Parse vision extraction response into extracted_text and analysis.
        
        Args:
            response_text: Raw response from Ollama
            
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
    
    async def close(self) -> None:
        """Close HTTP client."""
        await self.client.aclose()


"""
Abstract base class for LLM services.
All LLM providers must implement this interface.
"""
from abc import ABC, abstractmethod
from typing import Dict, List, Optional

from pydantic import BaseModel


class ImageExtractionResult(BaseModel):
    """Result model for image text extraction."""
    extracted_text: str = ""
    analysis: str = ""
    confidence: Optional[str] = None


class BaseLLM(ABC):
    """Abstract base class for LLM services."""
    
    @abstractmethod
    async def extract_metadata(self, terminal_content: str) -> Dict[str, List[str]]:
        """
        Extract metadata from terminal content.
        
        Extracts:
        - targets: IP addresses, domains, hostnames
        - tools: Security tools used
        - findings: Key discoveries or vulnerabilities
        
        Args:
            terminal_content: Terminal/command-line session content
            
        Returns:
            Dictionary with keys: targets, tools, findings (each is a list of strings)
            
        Raises:
            RuntimeError: If LLM API call fails
        """
        pass
    
    @abstractmethod
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
        Query the LLM with a question and context.
        
        Args:
            question: User's question/query
            context: Context string to provide to the LLM
            scope: Query scope - "all" for all operations, "single" for one operation
            operation_name: Name of the operation when scope is "single"
            max_tokens: Maximum tokens in the response (default 4096, use higher for complex outputs)
            system_prompt: Optional custom system prompt. When provided, overrides the
                          default scope-based system prompt. Useful for non-red-team tasks
                          like simulation generation.
            
        Returns:
            LLM's response as a string
            
        Raises:
            RuntimeError: If LLM API call fails
        """
        pass
    
    @abstractmethod
    async def test_connection(self) -> bool:
        """
        Test connection to the LLM provider.
        
        Returns:
            True if connection is successful, False otherwise
        """
        pass
    
    def supports_vision(self) -> bool:
        """
        Check if this LLM service supports vision/image processing.
        
        Returns:
            True if vision is supported, False otherwise
        """
        return False
    
    async def extract_from_image(self, image_path: str) -> ImageExtractionResult:
        """
        Extract text and analyze an image using vision capabilities.
        
        Args:
            image_path: Path to the image file
            
        Returns:
            ImageExtractionResult with extracted text and analysis
            
        Raises:
            NotImplementedError: If vision is not supported
            RuntimeError: If extraction fails
        """
        raise NotImplementedError("Vision extraction not supported by this LLM provider")


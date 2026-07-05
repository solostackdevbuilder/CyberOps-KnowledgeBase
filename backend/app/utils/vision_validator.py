"""
Utility functions for validating vision support for LLM providers.
"""
from app.models_settings import LLMProvider


def check_vision_support(provider: LLMProvider, model_name: str) -> bool:
    """
    Check if a given LLM provider and model support vision capabilities.
    
    Args:
        provider: LLM provider (CLAUDE, OPENAI, OLLAMA)
        model_name: Model name to check
        
    Returns:
        True if vision is supported, False otherwise
    """
    model_lower = model_name.lower()
    
    if provider == LLMProvider.CLAUDE:
        # Claude Sonnet and Opus models support vision
        return "sonnet" in model_lower or "opus" in model_lower
    
    elif provider == LLMProvider.OPENAI:
        # GPT-4 Vision models support vision
        return "vision" in model_lower or "gpt-4" in model_lower
    
    elif provider == LLMProvider.OLLAMA:
        # Ollama vision models (llava, bakllava, etc.)
        return "llava" in model_lower or "vision" in model_lower or "bakllava" in model_lower
    
    # Default: no vision support
    return False






"""
Factory for creating LLM service instances with fallback logic.
"""
import logging
from typing import Optional

from typing import TYPE_CHECKING

from app.models_settings import LLMProvider, Settings
from app.core.services.base_llm import BaseLLM

if TYPE_CHECKING:
    from app.core.storage.base_store import BaseStore

logger = logging.getLogger(__name__)

# Cache for LLM instances (singleton pattern)
_llm_cache: Optional[BaseLLM] = None
_cached_settings: Optional[Settings] = None


def get_llm_service(settings: Settings, storage: Optional["BaseStore"] = None) -> BaseLLM:
    """
    Get LLM service instance based on settings.
    Implements fallback logic: if primary LLM fails, try Claude -> OpenAI -> Ollama in order.
    Uses lazy initialization with caching.
    
    Args:
        settings: Application settings
        storage: Optional storage instance (for backward compatibility with query_with_context)
        
    Returns:
        LLM service instance implementing BaseLLM
        
    Raises:
        ValueError: If LLM provider is not supported or configuration is invalid
        RuntimeError: If all LLM providers fail
    """
    global _llm_cache, _cached_settings
    
    # Check if we can reuse cached instance
    if _llm_cache is not None and _cached_settings is not None:
        # Check if settings changed
        if (
            _cached_settings.llm_provider == settings.llm_provider
            and _cached_settings.llm_config == settings.llm_config
        ):
            return _llm_cache
    
    # Try to create LLM service with fallback
    llm_service = None
    error_messages = []
    
    # Primary provider
    primary_provider = settings.llm_provider
    llm_config = settings.llm_config
    
    # Fallback order: primary -> Claude -> OpenAI -> Ollama
    fallback_providers = [primary_provider]
    if primary_provider != LLMProvider.CLAUDE:
        fallback_providers.append(LLMProvider.CLAUDE)
    if primary_provider != LLMProvider.OPENAI:
        fallback_providers.append(LLMProvider.OPENAI)
    if primary_provider != LLMProvider.OLLAMA:
        fallback_providers.append(LLMProvider.OLLAMA)
    
    for provider in fallback_providers:
        try:
            if provider == LLMProvider.CLAUDE:
                # Try Claude
                try:
                    from app.core.services.claude_service import ClaudeService
                except ImportError as e:
                    raise RuntimeError(
                        "Claude service requires 'anthropic' package. Install it with: pip install anthropic"
                    ) from e
                
                api_key = None
                model_name = "claude-sonnet-4-5-20250929"
                
                if llm_config and llm_config.provider == LLMProvider.CLAUDE:
                    api_key = llm_config.api_key
                    if llm_config.model_name:
                        model_name = llm_config.model_name
                else:
                    # Try to get from environment
                    from app.config import settings as app_settings
                    api_key = getattr(app_settings, "anthropic_api_key", None)
                
                if not api_key:
                    raise ValueError("Claude API key is required")
                
                llm_service = ClaudeService(api_key=api_key, model_name=model_name, storage=storage)
                logger.info(f"Using LLM provider: Claude ({model_name})")
                break
                
            elif provider == LLMProvider.OPENAI:
                # Try OpenAI
                try:
                    from app.core.services.openai_service import OpenAIService
                except ImportError as e:
                    raise RuntimeError(
                        "OpenAI service requires 'openai' package. Install it with: pip install openai"
                    ) from e
                
                if not llm_config or llm_config.provider != LLMProvider.OPENAI:
                    raise ValueError("OpenAI config is required")
                
                api_key = llm_config.api_key
                if not api_key:
                    raise ValueError("OpenAI API key is required")
                
                model_name = llm_config.model_name or "gpt-4-turbo-preview"
                endpoint = llm_config.endpoint
                
                llm_service = OpenAIService(api_key=api_key, model_name=model_name, endpoint=endpoint)
                logger.info(f"Using LLM provider: OpenAI ({model_name})")
                break
                
            elif provider == LLMProvider.OLLAMA:
                # Try Ollama
                try:
                    from app.core.services.ollama_service import OllamaService
                except ImportError as e:
                    raise RuntimeError(
                        "Ollama service requires 'httpx' package. Install it with: pip install httpx"
                    ) from e
                
                if not llm_config or llm_config.provider != LLMProvider.OLLAMA:
                    raise ValueError("Ollama config is required")
                
                endpoint = llm_config.endpoint
                if not endpoint:
                    raise ValueError("Ollama endpoint is required")
                
                model_name = llm_config.model_name or "llama2"
                
                llm_service = OllamaService(endpoint=endpoint, model_name=model_name)
                logger.info(f"Using LLM provider: Ollama ({model_name} at {endpoint})")
                break
                
        except Exception as e:
            error_messages.append(f"{provider.value}: {str(e)}")
            logger.warning(f"Failed to initialize {provider.value}: {e}")
            continue
    
    if llm_service is None:
        error_summary = "; ".join(error_messages)
        raise RuntimeError(f"Failed to initialize any LLM provider. Errors: {error_summary}")
    
    # Cache the instance
    _llm_cache = llm_service
    _cached_settings = settings
    
    return llm_service


def clear_llm_cache() -> None:
    """Clear the LLM cache (useful for testing or reconfiguration)."""
    global _llm_cache, _cached_settings
    if _llm_cache and hasattr(_llm_cache, "close"):
        # Close connections if needed (e.g., Ollama HTTP client)
        try:
            import asyncio
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # If loop is running, schedule close
                asyncio.create_task(_llm_cache.close())
            else:
                loop.run_until_complete(_llm_cache.close())
        except Exception:
            pass
    _llm_cache = None
    _cached_settings = None


"""
FastAPI dependency injection for common resources.
Provides cached, injectable dependencies for storage, settings, and LLM services.
"""
import logging
from functools import lru_cache
from typing import Optional

from fastapi import Depends, Request

from app.models_settings import Settings
from app.core.storage.base_store import BaseStore
from app.core.storage.settings_store import SettingsStore
from app.core.storage.storage_factory import get_storage
from app.core.services.llm_factory import get_llm_service
from app.core.services.base_llm import BaseLLM

logger = logging.getLogger(__name__)

# Cached settings store instance
_settings_store: Optional[SettingsStore] = None
_cached_settings: Optional[Settings] = None
_cached_storage: Optional[BaseStore] = None


def get_settings_store() -> SettingsStore:
    """
    Get or create a singleton SettingsStore instance.
    
    Returns:
        SettingsStore instance
    """
    global _settings_store
    if _settings_store is None:
        _settings_store = SettingsStore()
    return _settings_store


async def get_settings(
    settings_store: SettingsStore = Depends(get_settings_store)
) -> Settings:
    """
    Load application settings with caching.
    
    Settings are cached after first load and only reloaded when explicitly
    invalidated (e.g., after settings update).
    
    Args:
        settings_store: Injected settings store
        
    Returns:
        Application settings
    """
    global _cached_settings
    if _cached_settings is None:
        _cached_settings = await settings_store.load_settings()
        logger.debug("Settings loaded and cached")
    return _cached_settings


async def get_storage_service(
    settings: Settings = Depends(get_settings)
) -> BaseStore:
    """
    Get storage service based on current settings.
    
    Storage is cached and reused across requests.
    
    Args:
        settings: Injected application settings
        
    Returns:
        Storage service instance
    """
    global _cached_storage
    if _cached_storage is None:
        _cached_storage = get_storage(settings)
        logger.debug(f"Storage initialized: {settings.storage_backend.value}")
    return _cached_storage


async def get_llm(
    settings: Settings = Depends(get_settings),
    storage: BaseStore = Depends(get_storage_service)
) -> BaseLLM:
    """
    Get LLM service based on current settings.
    
    LLM service is cached in llm_factory.
    
    Args:
        settings: Injected application settings
        storage: Injected storage service (for context queries)
        
    Returns:
        LLM service instance
        
    Raises:
        LLMNotConfiguredError: If LLM is not configured
    """
    from app.core.exceptions import LLMNotConfiguredError
    
    if not settings.llm_config:
        raise LLMNotConfiguredError(
            "LLM service not configured. Please configure LLM settings."
        )
    
    return get_llm_service(settings, storage=storage)


async def get_optional_llm(
    settings: Settings = Depends(get_settings),
    storage: BaseStore = Depends(get_storage_service)
) -> Optional[BaseLLM]:
    """
    Get LLM service if configured, otherwise return None.
    
    Use this for endpoints where LLM is optional.
    
    Args:
        settings: Injected application settings
        storage: Injected storage service
        
    Returns:
        LLM service instance or None if not configured
    """
    if not settings.llm_config:
        return None
    
    try:
        return get_llm_service(settings, storage=storage)
    except Exception as e:
        logger.warning(f"Failed to initialize LLM service: {e}")
        return None


def invalidate_settings_cache() -> None:
    """
    Invalidate the cached settings.
    
    Call this after settings are updated to force reload on next request.
    """
    global _cached_settings, _cached_storage
    _cached_settings = None
    _cached_storage = None
    logger.info("Settings cache invalidated")


def invalidate_storage_cache() -> None:
    """
    Invalidate the cached storage instance.
    
    Call this when storage backend changes.
    """
    global _cached_storage
    _cached_storage = None
    logger.info("Storage cache invalidated")


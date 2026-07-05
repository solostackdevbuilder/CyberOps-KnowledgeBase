"""
Factory for creating storage backend instances.
"""
from typing import Optional

from app.models_settings import Settings, StorageBackend
from app.core.storage.base_store import BaseStore
from app.core.storage.json_store import JSONStore

# Cache for storage instances (singleton pattern)
_storage_cache: Optional[BaseStore] = None
_cached_settings: Optional[Settings] = None


def get_storage(settings: Settings) -> BaseStore:
    """
    Get storage instance based on settings.
    Uses lazy initialization with caching.
    
    Args:
        settings: Application settings
        
    Returns:
        Storage instance implementing BaseStore
        
    Raises:
        ValueError: If storage backend is not supported
        RuntimeError: If storage initialization fails
    """
    global _storage_cache, _cached_settings
    
    # Check if we can reuse cached instance
    if _storage_cache is not None and _cached_settings is not None:
        # Check if settings changed
        if (
            _cached_settings.storage_backend == settings.storage_backend
            and _cached_settings.database_config == settings.database_config
        ):
            return _storage_cache
    
    # Create new instance based on backend
    if settings.storage_backend == StorageBackend.JSON:
        storage = JSONStore()
    elif settings.storage_backend == StorageBackend.MONGODB:
        if not settings.database_config:
            raise ValueError("database_config is required for MongoDB storage")
        # Lazy import to avoid requiring motor if not using MongoDB
        try:
            from app.core.storage.mongodb_store import MongoDBStore
        except ImportError as e:
            raise RuntimeError(
                "MongoDB storage requires 'motor' package. Install it with: pip install motor"
            ) from e
        storage = MongoDBStore(settings.database_config)
    elif settings.storage_backend == StorageBackend.POSTGRESQL:
        if not settings.database_config:
            raise ValueError("database_config is required for PostgreSQL storage")
        # Lazy import to avoid requiring asyncpg if not using PostgreSQL
        try:
            from app.core.storage.postgresql_store import PostgreSQLStore
        except ImportError as e:
            raise RuntimeError(
                "PostgreSQL storage requires 'asyncpg' package. Install it with: pip install asyncpg"
            ) from e
        storage = PostgreSQLStore(settings.database_config)
    else:
        raise ValueError(f"Unsupported storage backend: {settings.storage_backend}")
    
    # Cache the instance
    _storage_cache = storage
    _cached_settings = settings
    
    return storage


def clear_storage_cache() -> None:
    """Clear the storage cache (useful for testing or reconfiguration)."""
    global _storage_cache, _cached_settings
    _storage_cache = None
    _cached_settings = None


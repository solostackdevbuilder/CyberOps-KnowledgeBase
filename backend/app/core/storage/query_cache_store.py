"""
File-based storage for query cache.
Handles saving and loading cached query results.
"""
import json
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Dict, Any
from uuid import uuid4

import aiofiles
from aiofiles import os as aios

from app.config import settings


class QueryCacheStore:
    """File-based storage implementation for query cache."""
    
    def __init__(self):
        """Initialize the query cache store with directory path."""
        self.cache_dir = settings.query_cache_dir
    
    async def _ensure_directories(self) -> None:
        """Ensure the cache directory exists."""
        try:
            await aios.makedirs(self.cache_dir, exist_ok=True)
        except Exception as e:
            raise RuntimeError(f"Failed to create directory {self.cache_dir}: {e}")
    
    async def save_query(
        self,
        question: str,
        operation_id: Optional[str],
        response: Dict[str, Any]
    ) -> str:
        """
        Save a query and its response to cache.
        
        Args:
            question: The query question
            operation_id: Optional operation ID filter
            response: The query response data
            
        Returns:
            The cache entry ID
        """
        await self._ensure_directories()
        
        # Generate unique cache entry ID
        cache_id = str(uuid4())
        now = datetime.utcnow()
        
        # Create cache entry
        cache_entry = {
            "id": cache_id,
            "question": question,
            "operation_id": operation_id,
            "response": response,
            "created_at": now.isoformat(),
        }
        
        # Save cache entry as JSON
        cache_file = self.cache_dir / f"{cache_id}.json"
        async with aiofiles.open(cache_file, "w", encoding="utf-8") as f:
            await f.write(json.dumps(cache_entry, indent=2, ensure_ascii=False))
        
        return cache_id
    
    async def get_query(self, cache_id: str) -> Optional[Dict[str, Any]]:
        """
        Retrieve a cached query by ID.
        
        Args:
            cache_id: Unique cache entry identifier
            
        Returns:
            Cache entry if found, None otherwise
        """
        cache_file = self.cache_dir / f"{cache_id}.json"
        
        if not await aios.path.exists(cache_file):
            return None
        
        try:
            async with aiofiles.open(cache_file, "r", encoding="utf-8") as f:
                content = await f.read()
                return json.loads(content)
        except Exception as e:
            # Log error but don't fail - return None if file is corrupted
            print(f"Error reading cache file {cache_file}: {e}")
            return None
    
    async def list_queries(self, limit: int = 10) -> List[Dict[str, Any]]:
        """
        List the most recent cached queries.
        
        Args:
            limit: Maximum number of queries to return (default: 10)
            
        Returns:
            List of cache entries sorted by creation time (newest first)
        """
        await self._ensure_directories()
        
        if not await aios.path.exists(self.cache_dir):
            return []
        
        # Get all cache files
        cache_files = []
        try:
            entries = await aios.listdir(self.cache_dir)
            for entry in entries:
                file_path = self.cache_dir / entry
                if await aios.path.isfile(file_path) and file_path.suffix == ".json":
                    cache_files.append(file_path)
        except Exception as e:
            print(f"Error scanning cache directory: {e}")
            return []
        
        # Load and parse all cache entries
        entries = []
        for cache_file in cache_files:
            try:
                async with aiofiles.open(cache_file, "r", encoding="utf-8") as f:
                    content = await f.read()
                    entry = json.loads(content)
                    entries.append(entry)
            except Exception as e:
                # Skip corrupted files
                print(f"Error reading cache file {cache_file}: {e}")
                continue
        
        # Sort by created_at (newest first)
        entries.sort(
            key=lambda x: x.get("created_at", ""),
            reverse=True
        )
        
        # Return limited results
        return entries[:limit]
    
    async def delete_query(self, cache_id: str) -> bool:
        """
        Delete a cached query.
        
        Args:
            cache_id: Unique cache entry identifier
            
        Returns:
            True if deleted, False if not found
        """
        cache_file = self.cache_dir / f"{cache_id}.json"
        
        if not await aios.path.exists(cache_file):
            return False
        
        try:
            await aios.remove(cache_file)
            return True
        except Exception as e:
            print(f"Error deleting cache file {cache_file}: {e}")
            return False




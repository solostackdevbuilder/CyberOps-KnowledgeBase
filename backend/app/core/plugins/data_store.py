"""
Plugin data store with isolation.
Each plugin gets its own data directory and cannot access other plugins' data.
"""
import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

import aiofiles

from app.core.plugins.base import PluginManifest
from app.core.plugins.capabilities import STORAGE_READ_WRITE, require

logger = logging.getLogger(__name__)


class PluginDataStore:
    """Scoped data access for a single plugin.

    Each plugin gets its own directory under data/plugins/<plugin_id>/.
    Data is organized into collections (subdirectories) with JSON documents.

    Construction requires the owning plugin to declare STORAGE_READ_WRITE.
    The manifest argument is the enforcement hook; plugin_id comes from
    manifest.id so we can't drift out of sync.

    Usage:
        store = PluginDataStore(plugin.manifest, Path("backend/data"))
        await store.save("jobs", "job-123", {...})
    """

    def __init__(self, manifest: PluginManifest, base_data_dir: Path):
        require(manifest, STORAGE_READ_WRITE)
        self._manifest = manifest
        self.plugin_id = manifest.id
        self.data_dir = base_data_dir / "plugins" / manifest.id
        self.data_dir.mkdir(parents=True, exist_ok=True)

    def _collection_dir(self, collection: str) -> Path:
        """Get or create collection directory."""
        d = self.data_dir / collection
        d.mkdir(parents=True, exist_ok=True)
        return d

    def _doc_path(self, collection: str, key: str) -> Path:
        """Get path for a document. Sanitizes key to prevent path traversal."""
        safe_key = "".join(c for c in key if c.isalnum() or c in ("-", "_"))
        if not safe_key:
            raise ValueError(f"Invalid document key: {key}")
        return self._collection_dir(collection) / f"{safe_key}.json"

    async def save(self, collection: str, key: str, data: Dict[str, Any]) -> None:
        """Save a document to a collection."""
        path = self._doc_path(collection, key)
        async with aiofiles.open(path, "w", encoding="utf-8") as f:
            await f.write(json.dumps(data, indent=2, default=str))

    async def load(self, collection: str, key: str) -> Optional[Dict[str, Any]]:
        """Load a document from a collection. Returns None if not found."""
        path = self._doc_path(collection, key)
        if not path.exists():
            return None
        try:
            async with aiofiles.open(path, "r", encoding="utf-8") as f:
                content = await f.read()
                return json.loads(content)
        except (json.JSONDecodeError, Exception) as e:
            logger.warning(f"Failed to load {path}: {e}")
            return None

    async def list_keys(self, collection: str) -> List[str]:
        """List all document keys in a collection."""
        col_dir = self._collection_dir(collection)
        return [
            f.stem for f in col_dir.glob("*.json")
        ]

    async def delete(self, collection: str, key: str) -> bool:
        """Delete a document. Returns True if deleted, False if not found."""
        path = self._doc_path(collection, key)
        if path.exists():
            path.unlink()
            return True
        return False

    async def list_collections(self) -> List[str]:
        """List all collections for this plugin."""
        return [
            d.name for d in self.data_dir.iterdir()
            if d.is_dir()
        ]

    async def clear_collection(self, collection: str) -> int:
        """Delete all documents in a collection. Returns count deleted."""
        col_dir = self._collection_dir(collection)
        count = 0
        for f in col_dir.glob("*.json"):
            f.unlink()
            count += 1
        return count

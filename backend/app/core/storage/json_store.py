"""
JSON file-based storage implementation that wraps FileStore and OperationStore.
Implements BaseStore interface for consistency with other storage backends.
"""
from typing import List, Optional

from app.core.models import Operation, OperationCreate, OperationUpdate
from app.core.models import Session, SessionCreate, SessionUpdate
from app.core.models import FAAItem, FAAItemCreate, FAAItemUpdate
from app.core.storage.base_store import BaseStore
from app.core.storage.file_store import FileStore
from app.modules.red_team.storage import OperationStore


class JSONStore(BaseStore):
    """JSON file-based storage implementation."""
    
    def __init__(self):
        """Initialize JSON store with file-based stores."""
        self.file_store = FileStore()
        self.operation_store = OperationStore()
    
    async def _ensure_directories(self) -> None:
        """Ensure all required directories exist."""
        await self.file_store._ensure_directories()
        await self.operation_store._ensure_directories()
    
    # Operation methods
    async def create_operation(self, operation_data: OperationCreate) -> Operation:
        """Create a new operation."""
        return await self.operation_store.create_operation(operation_data)
    
    async def get_operation(self, operation_id: str) -> Optional[Operation]:
        """Retrieve an operation by ID."""
        return await self.operation_store.get_operation(operation_id)
    
    async def list_operations(self) -> List[Operation]:
        """List all operations."""
        return await self.operation_store.list_operations()
    
    async def update_operation(self, operation_id: str, update_data: OperationUpdate) -> Optional[Operation]:
        """Update an existing operation."""
        return await self.operation_store.update_operation(operation_id, update_data)
    
    async def delete_operation(self, operation_id: str) -> bool:
        """Delete an operation."""
        return await self.operation_store.delete_operation(operation_id)
    
    async def add_session_to_operation(self, operation_id: str, session_id: str) -> bool:
        """Add a session ID to an operation's session_ids list."""
        return await self.operation_store.add_session_to_operation(operation_id, session_id)
    
    async def remove_session_from_operation(self, operation_id: str, session_id: str) -> bool:
        """Remove a session ID from an operation's session_ids list."""
        return await self.operation_store.remove_session_from_operation(operation_id, session_id)
    
    # Session methods
    async def create_session(self, session_data: SessionCreate) -> Session:
        """Create a new session."""
        return await self.file_store.create_session(session_data)
    
    async def get_session(self, session_id: str) -> Optional[Session]:
        """Retrieve a session by ID."""
        return await self.file_store.get_session(session_id)
    
    async def list_sessions(self) -> List[Session]:
        """List all sessions."""
        return await self.file_store.list_sessions()
    
    async def update_session(self, session_id: str, update_data: SessionUpdate) -> Optional[Session]:
        """Update an existing session."""
        return await self.file_store.update_session(session_id, update_data)
    
    async def delete_session(self, session_id: str) -> bool:
        """Delete a session."""
        return await self.file_store.delete_session(session_id)
    
    # FAA (Findings and Actions) methods
    async def create_faa_item(self, faa_data: FAAItemCreate) -> FAAItem:
        """Create a new FAA item."""
        return await self.file_store.create_faa_item(faa_data)
    
    async def get_faa_item(self, faa_id: str, session_id: str) -> Optional[FAAItem]:
        """Retrieve an FAA item by ID."""
        return await self.file_store.get_faa_item(faa_id, session_id)
    
    async def list_faa_items(
        self,
        session_id: str,
        classification: Optional[str] = None,
        mitre_technique: Optional[str] = None,
        severity: Optional[str] = None
    ) -> List[FAAItem]:
        """List all FAA items for a session with optional filters."""
        return await self.file_store.list_faa_items(
            session_id=session_id,
            classification=classification,
            mitre_technique=mitre_technique,
            severity=severity
        )
    
    async def update_faa_item(
        self,
        faa_id: str,
        session_id: str,
        update_data: FAAItemUpdate
    ) -> Optional[FAAItem]:
        """Update an existing FAA item."""
        return await self.file_store.update_faa_item(faa_id, session_id, update_data)
    
    async def delete_faa_item(self, faa_id: str, session_id: str) -> bool:
        """Delete an FAA item."""
        return await self.file_store.delete_faa_item(faa_id, session_id)
    
    async def save_faa_items(self, session_id: str, faa_items: List[FAAItem]) -> None:
        """Save multiple FAA items for a session."""
        return await self.file_store.save_faa_items(session_id, faa_items)


"""
File-based storage for operations.
Handles all file I/O operations for operations.
"""
import json
from datetime import datetime
from pathlib import Path
from typing import List, Optional
from uuid import uuid4

import aiofiles
from aiofiles import os as aios

from app.config import settings
from app.modules.red_team.models import Operation, OperationCreate, OperationUpdate


class OperationStore:
    """File-based storage implementation for operations."""
    
    def __init__(self):
        """Initialize the operation store with directory path."""
        self.operations_dir = settings.operations_dir
    
    async def _ensure_directories(self) -> None:
        """Ensure the operations directory exists."""
        try:
            await aios.makedirs(self.operations_dir, exist_ok=True)
        except Exception as e:
            raise RuntimeError(f"Failed to create directory {self.operations_dir}: {e}")
    
    async def create_operation(self, operation_data: OperationCreate) -> Operation:
        """
        Create a new operation and save as JSON.
        
        Args:
            operation_data: Operation creation data
            
        Returns:
            Created operation with generated ID and timestamps
        """
        await self._ensure_directories()
        
        # Generate unique operation ID
        operation_id = str(uuid4())
        now = datetime.utcnow()
        
        # Create operation object
        operation = Operation(
            id=operation_id,
            name=operation_data.name,
            description=operation_data.description,
            created_at=now,
            status="active",
            session_ids=[]
        )
        
        # Save operation as JSON
        operation_file = self.operations_dir / f"{operation_id}.json"
        operation_dict = operation.model_dump(mode="json")
        # Convert datetime objects to ISO format strings
        operation_dict["created_at"] = operation.created_at.isoformat()
        
        async with aiofiles.open(operation_file, "w", encoding="utf-8") as f:
            await f.write(json.dumps(operation_dict, indent=2, ensure_ascii=False))
        
        return operation
    
    async def get_operation(self, operation_id: str) -> Optional[Operation]:
        """
        Retrieve an operation by ID.
        
        Args:
            operation_id: Unique operation identifier
            
        Returns:
            Operation object if found, None otherwise
        """
        operation_file = self.operations_dir / f"{operation_id}.json"
        
        # Check if operation exists
        try:
            if not await aios.path.exists(operation_file):
                return None
        except Exception:
            return None
        
        try:
            # Load operation metadata
            async with aiofiles.open(operation_file, "r", encoding="utf-8") as f:
                content = await f.read()
                operation_dict = json.loads(content)
            
            # Parse datetime strings back to datetime objects
            operation_dict["created_at"] = datetime.fromisoformat(operation_dict["created_at"])
            
            return Operation(**operation_dict)
        except Exception as e:
            raise RuntimeError(f"Failed to load operation {operation_id}: {e}")
    
    async def list_operations(self) -> List[Operation]:
        """
        List all operations.
        
        Returns:
            List of operation objects
        """
        await self._ensure_directories()
        
        operations = []
        
        try:
            # Get all JSON files in operations directory
            if not await aios.path.exists(self.operations_dir):
                return operations
            
            files = []
            async for file_path in self._list_files(self.operations_dir):
                if file_path.suffix == ".json":
                    files.append(file_path)
            
            # Load each operation
            for operation_file in files:
                try:
                    async with aiofiles.open(operation_file, "r", encoding="utf-8") as f:
                        content = await f.read()
                        operation_dict = json.loads(content)
                    
                    # Parse datetime strings
                    operation_dict["created_at"] = datetime.fromisoformat(operation_dict["created_at"])
                    
                    operations.append(Operation(**operation_dict))
                except Exception as e:
                    # Skip corrupted files but log the error
                    print(f"Warning: Failed to load operation from {operation_file}: {e}")
                    continue
            
            # Sort by created_at descending (most recent first)
            operations.sort(key=lambda o: o.created_at, reverse=True)
            
        except Exception as e:
            raise RuntimeError(f"Failed to list operations: {e}")
        
        return operations
    
    async def _list_files(self, directory: Path):
        """Async generator to list files in a directory."""
        try:
            entries = await aios.listdir(directory)
            for entry in entries:
                file_path = directory / entry
                if await aios.path.isfile(file_path):
                    yield file_path
        except Exception as e:
            raise RuntimeError(f"Failed to list files in {directory}: {e}")
    
    async def update_operation(self, operation_id: str, update_data: OperationUpdate) -> Optional[Operation]:
        """
        Update an existing operation.
        
        Args:
            operation_id: Unique operation identifier
            update_data: Fields to update
            
        Returns:
            Updated operation if found, None otherwise
        """
        operation = await self.get_operation(operation_id)
        if not operation:
            return None
        
        # Update fields if provided
        if update_data.name is not None:
            operation.name = update_data.name
        if update_data.description is not None:
            operation.description = update_data.description
        if update_data.status is not None:
            operation.status = update_data.status
        
        # Save updated operation
        operation_file = self.operations_dir / f"{operation_id}.json"
        operation_dict = operation.model_dump(mode="json")
        operation_dict["created_at"] = operation.created_at.isoformat()
        
        async with aiofiles.open(operation_file, "w", encoding="utf-8") as f:
            await f.write(json.dumps(operation_dict, indent=2, ensure_ascii=False))
        
        return operation
    
    async def delete_operation(self, operation_id: str) -> bool:
        """
        Delete an operation.
        
        Args:
            operation_id: Unique operation identifier
            
        Returns:
            True if operation was deleted, False if not found
        """
        operation_file = self.operations_dir / f"{operation_id}.json"
        
        deleted = False
        
        # Delete operation file
        try:
            if await aios.path.exists(operation_file):
                await aios.remove(operation_file)
                deleted = True
        except Exception as e:
            raise RuntimeError(f"Failed to delete operation file {operation_file}: {e}")
        
        return deleted
    
    async def add_session_to_operation(self, operation_id: str, session_id: str) -> bool:
        """
        Add a session ID to an operation's session_ids list.
        
        Args:
            operation_id: Operation identifier
            session_id: Session identifier to add
            
        Returns:
            True if successful, False if operation not found
        """
        operation = await self.get_operation(operation_id)
        if not operation:
            return False
        
        # Add session_id if not already present
        if session_id not in operation.session_ids:
            operation.session_ids.append(session_id)
            
            # Save updated operation
            operation_file = self.operations_dir / f"{operation_id}.json"
            operation_dict = operation.model_dump(mode="json")
            operation_dict["created_at"] = operation.created_at.isoformat()
            
            async with aiofiles.open(operation_file, "w", encoding="utf-8") as f:
                await f.write(json.dumps(operation_dict, indent=2, ensure_ascii=False))
        
        return True
    
    async def remove_session_from_operation(self, operation_id: str, session_id: str) -> bool:
        """
        Remove a session ID from an operation's session_ids list.
        
        Args:
            operation_id: Operation identifier
            session_id: Session identifier to remove
            
        Returns:
            True if successful, False if operation not found
        """
        operation = await self.get_operation(operation_id)
        if not operation:
            return False
        
        # Remove session_id if present
        if session_id in operation.session_ids:
            operation.session_ids.remove(session_id)
            
            # Save updated operation
            operation_file = self.operations_dir / f"{operation_id}.json"
            operation_dict = operation.model_dump(mode="json")
            operation_dict["created_at"] = operation.created_at.isoformat()
            
            async with aiofiles.open(operation_file, "w", encoding="utf-8") as f:
                await f.write(json.dumps(operation_dict, indent=2, ensure_ascii=False))
        
        return True



# ============================================================================
# Content from query_helpers.py
# ============================================================================

from typing import List, Optional

from app.modules.red_team.models import Session
from app.core.storage.base_store import BaseStore


async def build_query_context(
    sessions: List[Session],
    include_operation_names: bool,
    storage: BaseStore
) -> str:
    """
    Build formatted context string from session data.
    
    Args:
        sessions: List of sessions to include in context
        include_operation_names: True if querying all operations, False if single operation
        storage: Storage instance to load operation details
        
    Returns:
        Formatted context string
    """
    if not sessions:
        return "No sessions available in the knowledge base."
    
    # Load operation names for all unique operation IDs
    operation_names: dict[str, str] = {}
    if include_operation_names:
        unique_operation_ids = {s.operation_id for s in sessions if s.operation_id}
        for operation_id in unique_operation_ids:
            try:
                operation = await storage.get_operation(operation_id)
                if operation:
                    operation_names[operation_id] = operation.name
                else:
                    operation_names[operation_id] = f"Unknown Operation ({operation_id})"
            except Exception:
                operation_names[operation_id] = f"Unknown Operation ({operation_id})"
    
    context_parts = []
    
    for i, session in enumerate(sessions, 1):
        session_context = f"=== Session {i}: {session.title} ===\n"
        session_context += f"ID: {session.id}\n"
        
        # Include operation name if querying all operations
        if include_operation_names and session.operation_id:
            operation_name = operation_names.get(session.operation_id, "Unknown Operation")
            session_context += f"Operation: {operation_name}\n"
        
        # Include operator name if available
        if session.operator_name:
            session_context += f"Operator: {session.operator_name}\n"
        
        session_context += f"Timestamp: {session.created_at.isoformat()}\n"
        session_context += f"Updated: {session.updated_at.isoformat()}\n"
        
        if session.description:
            session_context += f"Description: {session.description}\n"
        
        if session.tags:
            session_context += f"Tags: {', '.join(session.tags)}\n"
        
        session_context += f"\nTerminal Content:\n{session.terminal_content}\n"
        
        if session.screenshots:
            session_context += f"\nScreenshots ({len(session.screenshots)}):\n"
            for screenshot in session.screenshots:
                session_context += f"  - {screenshot.filename}"
                if screenshot.description:
                    session_context += f": {screenshot.description}"
                session_context += f" ({screenshot.timestamp.isoformat()})\n"
        
        # Add screenshot extractions if available
        if hasattr(session, 'screenshot_extractions') and session.screenshot_extractions:
            session_context += f"\nScreenshot Extractions:\n"
            for extraction in session.screenshot_extractions:
                if extraction.extracted_text:
                    session_context += f"  - [{extraction.filename}]: {extraction.extracted_text}\n"
                    if extraction.analysis:
                        session_context += f"    Analysis: {extraction.analysis}\n"
        
        session_context += "\n"
        context_parts.append(session_context)
    
    return "\n".join(context_parts)


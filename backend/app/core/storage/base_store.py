"""
Abstract base class for storage operations.
All storage backends must implement this interface.
"""
from abc import ABC, abstractmethod
from typing import List, Optional

from app.core.models import Operation, OperationCreate, OperationUpdate
from app.core.models import Session, SessionCreate, SessionUpdate


class BaseStore(ABC):
    """Abstract base class for storage backends."""
    
    # Operation methods
    @abstractmethod
    async def create_operation(self, operation_data: OperationCreate) -> Operation:
        """
        Create a new operation.
        
        Args:
            operation_data: Operation creation data
            
        Returns:
            Created operation with generated ID and timestamps
        """
        pass
    
    @abstractmethod
    async def get_operation(self, operation_id: str) -> Optional[Operation]:
        """
        Retrieve an operation by ID.
        
        Args:
            operation_id: Unique operation identifier
            
        Returns:
            Operation object if found, None otherwise
        """
        pass
    
    @abstractmethod
    async def list_operations(self) -> List[Operation]:
        """
        List all operations.
        
        Returns:
            List of operation objects
        """
        pass
    
    @abstractmethod
    async def update_operation(self, operation_id: str, update_data: OperationUpdate) -> Optional[Operation]:
        """
        Update an existing operation.
        
        Args:
            operation_id: Unique operation identifier
            update_data: Fields to update
            
        Returns:
            Updated operation if found, None otherwise
        """
        pass
    
    @abstractmethod
    async def delete_operation(self, operation_id: str) -> bool:
        """
        Delete an operation.
        
        Args:
            operation_id: Unique operation identifier
            
        Returns:
            True if operation was deleted, False if not found
        """
        pass
    
    @abstractmethod
    async def add_session_to_operation(self, operation_id: str, session_id: str) -> bool:
        """
        Add a session ID to an operation's session_ids list.
        
        Args:
            operation_id: Operation identifier
            session_id: Session identifier to add
            
        Returns:
            True if successful, False if operation not found
        """
        pass
    
    @abstractmethod
    async def remove_session_from_operation(self, operation_id: str, session_id: str) -> bool:
        """
        Remove a session ID from an operation's session_ids list.
        
        Args:
            operation_id: Operation identifier
            session_id: Session identifier to remove
            
        Returns:
            True if successful, False if operation not found
        """
        pass
    
    # Session methods
    @abstractmethod
    async def create_session(self, session_data: SessionCreate) -> Session:
        """
        Create a new session.
        
        Args:
            session_data: Session creation data
            
        Returns:
            Created session with generated ID and timestamps
        """
        pass
    
    @abstractmethod
    async def get_session(self, session_id: str) -> Optional[Session]:
        """
        Retrieve a session by ID.
        
        Args:
            session_id: Unique session identifier
            
        Returns:
            Session object if found, None otherwise
        """
        pass
    
    @abstractmethod
    async def list_sessions(self) -> List[Session]:
        """
        List all sessions.
        
        Returns:
            List of session objects
        """
        pass
    
    @abstractmethod
    async def update_session(self, session_id: str, update_data: SessionUpdate) -> Optional[Session]:
        """
        Update an existing session.
        
        Args:
            session_id: Unique session identifier
            update_data: Fields to update
            
        Returns:
            Updated session if found, None otherwise
        """
        pass
    
    @abstractmethod
    async def delete_session(self, session_id: str) -> bool:
        """
        Delete a session.
        
        Args:
            session_id: Unique session identifier
            
        Returns:
            True if session was deleted, False if not found
        """
        pass


"""
MongoDB storage implementation using Motor (async MongoDB driver).
"""
import base64
from datetime import datetime
from typing import List, Optional
from uuid import uuid4

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from pymongo.errors import ConnectionFailure, OperationFailure

from app.core.models import Operation, OperationCreate, OperationUpdate
from app.core.models import Session, SessionCreate, SessionUpdate
from app.models_settings import DatabaseConfig
from app.core.storage.base_store import BaseStore


class MongoDBStore(BaseStore):
    """MongoDB storage implementation."""
    
    def __init__(self, config: DatabaseConfig):
        """
        Initialize MongoDB store.
        
        Args:
            config: Database configuration
            
        Raises:
            ValueError: If configuration is invalid
        """
        self.config = config
        
        # Build connection string
        if config.connection_string:
            self.connection_string = config.connection_string
        else:
            # Build from individual fields
            if not config.host or not config.database_name:
                raise ValueError("Either connection_string or (host and database_name) must be provided")
            
            # Build MongoDB URI
            auth_part = ""
            if config.username and config.password:
                auth_part = f"{config.username}:{config.password}@"
            
            port = config.port or 27017
            self.connection_string = f"mongodb://{auth_part}{config.host}:{port}/{config.database_name}"
        
        self.database_name = config.database_name or "redteam_kb"
        self.client: Optional[AsyncIOMotorClient] = None
        self.db: Optional[AsyncIOMotorDatabase] = None
    
    async def _ensure_connected(self) -> None:
        """Ensure MongoDB connection is established."""
        if self.client is None:
            try:
                self.client = AsyncIOMotorClient(self.connection_string)
                self.db = self.client[self.database_name]
                # Test connection
                await self.client.admin.command("ping")
            except Exception as e:
                raise RuntimeError(f"Failed to connect to MongoDB: {e}")
    
    async def test_connection(self) -> bool:
        """
        Test MongoDB connection.
        
        Returns:
            True if connection is successful, False otherwise
        """
        try:
            await self._ensure_connected()
            await self.client.admin.command("ping")
            return True
        except Exception:
            return False
    
    # Operation methods
    async def create_operation(self, operation_data: OperationCreate) -> Operation:
        """Create a new operation."""
        await self._ensure_connected()
        
        operation_id = str(uuid4())
        now = datetime.utcnow()
        
        operation = Operation(
            id=operation_id,
            name=operation_data.name,
            description=operation_data.description,
            created_at=now,
            status="active",
            session_ids=[]
        )
        
        # Convert to dict for MongoDB
        operation_dict = operation.model_dump(mode="json")
        operation_dict["created_at"] = operation.created_at.isoformat()
        
        try:
            await self.db.operations.insert_one(operation_dict)
        except Exception as e:
            raise RuntimeError(f"Failed to create operation: {e}")
        
        return operation
    
    async def get_operation(self, operation_id: str) -> Optional[Operation]:
        """Retrieve an operation by ID."""
        await self._ensure_connected()
        
        try:
            operation_dict = await self.db.operations.find_one({"id": operation_id})
            if not operation_dict:
                return None
            
            # Remove MongoDB _id field
            operation_dict.pop("_id", None)
            
            # Parse datetime
            operation_dict["created_at"] = datetime.fromisoformat(operation_dict["created_at"])
            
            return Operation(**operation_dict)
        except Exception as e:
            raise RuntimeError(f"Failed to get operation: {e}")
    
    async def list_operations(self) -> List[Operation]:
        """List all operations."""
        await self._ensure_connected()
        
        operations = []
        
        try:
            cursor = self.db.operations.find().sort("created_at", -1)
            async for operation_dict in cursor:
                # Remove MongoDB _id field
                operation_dict.pop("_id", None)
                
                # Parse datetime
                operation_dict["created_at"] = datetime.fromisoformat(operation_dict["created_at"])
                
                operations.append(Operation(**operation_dict))
        except Exception as e:
            raise RuntimeError(f"Failed to list operations: {e}")
        
        return operations
    
    async def update_operation(self, operation_id: str, update_data: OperationUpdate) -> Optional[Operation]:
        """Update an existing operation."""
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
        
        # Convert to dict for MongoDB
        operation_dict = operation.model_dump(mode="json")
        operation_dict["created_at"] = operation.created_at.isoformat()
        
        try:
            await self.db.operations.update_one(
                {"id": operation_id},
                {"$set": operation_dict}
            )
        except Exception as e:
            raise RuntimeError(f"Failed to update operation: {e}")
        
        return operation
    
    async def delete_operation(self, operation_id: str) -> bool:
        """Delete an operation."""
        await self._ensure_connected()
        
        try:
            result = await self.db.operations.delete_one({"id": operation_id})
            return result.deleted_count > 0
        except Exception as e:
            raise RuntimeError(f"Failed to delete operation: {e}")
    
    async def add_session_to_operation(self, operation_id: str, session_id: str) -> bool:
        """Add a session ID to an operation's session_ids list."""
        operation = await self.get_operation(operation_id)
        if not operation:
            return False
        
        # Add session_id if not already present
        if session_id not in operation.session_ids:
            operation.session_ids.append(session_id)
            
            try:
                await self.db.operations.update_one(
                    {"id": operation_id},
                    {"$set": {"session_ids": operation.session_ids}}
                )
            except Exception as e:
                raise RuntimeError(f"Failed to add session to operation: {e}")
        
        return True
    
    async def remove_session_from_operation(self, operation_id: str, session_id: str) -> bool:
        """Remove a session ID from an operation's session_ids list."""
        operation = await self.get_operation(operation_id)
        if not operation:
            return False
        
        # Remove session_id if present
        if session_id in operation.session_ids:
            operation.session_ids.remove(session_id)
            
            try:
                await self.db.operations.update_one(
                    {"id": operation_id},
                    {"$set": {"session_ids": operation.session_ids}}
                )
            except Exception as e:
                raise RuntimeError(f"Failed to remove session from operation: {e}")
        
        return True
    
    # Session methods
    async def create_session(self, session_data: SessionCreate) -> Session:
        """Create a new session."""
        await self._ensure_connected()
        
        session_id = str(uuid4())
        now = datetime.utcnow()
        
        session = Session(
            id=session_id,
            title=session_data.title,
            description=session_data.description,
            tags=session_data.tags,
            operation_id=session_data.operation_id,
            operator_name=session_data.operator_name,
            targets=session_data.targets,
            tools=session_data.tools,
            findings=session_data.findings,
            primary_tool=session_data.primary_tool,
            documentation_time_minutes=session_data.documentation_time_minutes,
            created_at=now,
            updated_at=now,
            terminal_content=session_data.terminal_content,
            screenshots=session_data.screenshots
        )
        
        # Convert to dict for MongoDB
        session_dict = session.model_dump(mode="json")
        session_dict["created_at"] = session.created_at.isoformat()
        session_dict["updated_at"] = session.updated_at.isoformat()
        for screenshot in session_dict.get("screenshots", []):
            if "timestamp" in screenshot:
                screenshot["timestamp"] = screenshot["timestamp"].isoformat() if isinstance(screenshot["timestamp"], datetime) else screenshot["timestamp"]
        
        try:
            await self.db.sessions.insert_one(session_dict)
        except Exception as e:
            raise RuntimeError(f"Failed to create session: {e}")
        
        return session
    
    async def get_session(self, session_id: str) -> Optional[Session]:
        """Retrieve a session by ID."""
        await self._ensure_connected()
        
        try:
            session_dict = await self.db.sessions.find_one({"id": session_id})
            if not session_dict:
                return None
            
            # Remove MongoDB _id field
            session_dict.pop("_id", None)
            
            # Parse datetimes
            session_dict["created_at"] = datetime.fromisoformat(session_dict["created_at"])
            session_dict["updated_at"] = datetime.fromisoformat(session_dict["updated_at"])
            for screenshot in session_dict.get("screenshots", []):
                if "timestamp" in screenshot:
                    screenshot["timestamp"] = datetime.fromisoformat(screenshot["timestamp"])
            
            return Session(**session_dict)
        except Exception as e:
            raise RuntimeError(f"Failed to get session: {e}")
    
    async def list_sessions(self) -> List[Session]:
        """List all sessions."""
        await self._ensure_connected()
        
        sessions = []
        
        try:
            cursor = self.db.sessions.find().sort("updated_at", -1)
            async for session_dict in cursor:
                # Remove MongoDB _id field
                session_dict.pop("_id", None)
                
                # Parse datetimes
                session_dict["created_at"] = datetime.fromisoformat(session_dict["created_at"])
                session_dict["updated_at"] = datetime.fromisoformat(session_dict["updated_at"])
                for screenshot in session_dict.get("screenshots", []):
                    if "timestamp" in screenshot:
                        screenshot["timestamp"] = datetime.fromisoformat(screenshot["timestamp"])
                
                sessions.append(Session(**session_dict))
        except Exception as e:
            raise RuntimeError(f"Failed to list sessions: {e}")
        
        return sessions
    
    async def update_session(self, session_id: str, update_data: SessionUpdate) -> Optional[Session]:
        """Update an existing session."""
        session = await self.get_session(session_id)
        if not session:
            return None
        
        # Update fields if provided
        if update_data.title is not None:
            session.title = update_data.title
        if update_data.description is not None:
            session.description = update_data.description
        if update_data.tags is not None:
            session.tags = update_data.tags
        if update_data.terminal_content is not None:
            session.terminal_content = update_data.terminal_content
        if update_data.targets is not None:
            session.targets = update_data.targets
        if update_data.tools is not None:
            session.tools = update_data.tools
        if update_data.findings is not None:
            session.findings = update_data.findings
        if update_data.primary_tool is not None:
            session.primary_tool = update_data.primary_tool
        if update_data.documentation_time_minutes is not None:
            session.documentation_time_minutes = update_data.documentation_time_minutes

        # Update timestamp
        session.updated_at = datetime.utcnow()

        # Convert to dict for MongoDB
        session_dict = session.model_dump(mode="json")
        session_dict["created_at"] = session.created_at.isoformat()
        session_dict["updated_at"] = session.updated_at.isoformat()
        for screenshot in session_dict.get("screenshots", []):
            if "timestamp" in screenshot:
                screenshot["timestamp"] = screenshot["timestamp"].isoformat() if isinstance(screenshot["timestamp"], datetime) else screenshot["timestamp"]
        
        try:
            await self.db.sessions.update_one(
                {"id": session_id},
                {"$set": session_dict}
            )
        except Exception as e:
            raise RuntimeError(f"Failed to update session: {e}")
        
        return session
    
    async def delete_session(self, session_id: str) -> bool:
        """Delete a session."""
        await self._ensure_connected()
        
        try:
            result = await self.db.sessions.delete_one({"id": session_id})
            return result.deleted_count > 0
        except Exception as e:
            raise RuntimeError(f"Failed to delete session: {e}")
    
    async def close(self) -> None:
        """Close MongoDB connection."""
        if self.client:
            self.client.close()
            self.client = None
            self.db = None


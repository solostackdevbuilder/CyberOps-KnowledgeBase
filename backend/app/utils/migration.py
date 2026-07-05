"""
Migration utilities for moving data from JSON storage to database storage.
"""
import json
from pathlib import Path
from typing import Dict, List

import aiofiles
from aiofiles import os as aios

from app.config import settings as app_settings
from app.core.models import Operation, Session
from app.models_settings import DatabaseConfig, StorageBackend
from app.core.storage.base_store import BaseStore
from app.core.storage.json_store import JSONStore


async def migrate_json_to_mongodb(mongodb_config: DatabaseConfig) -> Dict[str, any]:
    """
    Migrate all operations and sessions from JSON files to MongoDB.
    
    Args:
        mongodb_config: MongoDB configuration
        
    Returns:
        Migration report dictionary with counts and errors
    """
    report = {
        "operations_migrated": 0,
        "sessions_migrated": 0,
        "errors": []
    }
    
    try:
        # Lazy import to avoid requiring motor if not using MongoDB
        try:
            from app.core.storage.mongodb_store import MongoDBStore
        except ImportError as e:
            report["errors"].append(
                "MongoDB storage requires 'motor' package. Install it with: pip install motor"
            )
            return report
        
        # Initialize stores
        json_store = JSONStore()
        mongodb_store = MongoDBStore(mongodb_config)
        
        # Test MongoDB connection
        if not await mongodb_store.test_connection():
            report["errors"].append("Failed to connect to MongoDB")
            return report
        
        # Migrate operations
        try:
            operations = await json_store.list_operations()
            for operation in operations:
                try:
                    # Check if operation already exists in MongoDB
                    existing = await mongodb_store.get_operation(operation.id)
                    if not existing:
                        # Create operation in MongoDB
                        from app.core.models import OperationCreate
                        operation_create = OperationCreate(
                            name=operation.name,
                            description=operation.description
                        )
                        # We need to manually set the ID and other fields
                        # Since create_operation generates a new ID, we'll update it
                        created = await mongodb_store.create_operation(operation_create)
                        # Update with original ID and session_ids
                        if created.id != operation.id:
                            # Delete the created one and insert with original ID
                            await mongodb_store.delete_operation(created.id)
                            # Insert directly into MongoDB
                            operation_dict = operation.model_dump(mode="json")
                            operation_dict["created_at"] = operation.created_at.isoformat()
                            await mongodb_store.db.operations.insert_one(operation_dict)
                        else:
                            # Update session_ids if needed
                            if operation.session_ids:
                                await mongodb_store.db.operations.update_one(
                                    {"id": operation.id},
                                    {"$set": {"session_ids": operation.session_ids}}
                                )
                        report["operations_migrated"] += 1
                except Exception as e:
                    report["errors"].append(f"Failed to migrate operation {operation.id}: {str(e)}")
        except Exception as e:
            report["errors"].append(f"Failed to list operations: {str(e)}")
        
        # Migrate sessions
        try:
            sessions = await json_store.list_sessions()
            for session in sessions:
                try:
                    # Check if session already exists in MongoDB
                    existing = await mongodb_store.get_session(session.id)
                    if not existing:
                        # Get full session data
                        full_session = await json_store.get_session(session.id)
                        if full_session:
                            # Create session in MongoDB
                            from app.core.models import SessionCreate
                            session_create = SessionCreate(
                                title=full_session.title,
                                description=full_session.description,
                                tags=full_session.tags,
                                operation_id=full_session.operation_id or "",
                                operator_name=full_session.operator_name or "",
                                terminal_content=full_session.terminal_content,
                                screenshots=full_session.screenshots,
                                targets=full_session.targets,
                                tools=full_session.tools,
                                findings=full_session.findings
                            )
                            # Similar to operations, we need to preserve the ID
                            created = await mongodb_store.create_session(session_create)
                            if created.id != full_session.id:
                                # Delete and insert with original ID
                                await mongodb_store.delete_session(created.id)
                                session_dict = full_session.model_dump(mode="json")
                                session_dict["created_at"] = full_session.created_at.isoformat()
                                session_dict["updated_at"] = full_session.updated_at.isoformat()
                                for screenshot in session_dict.get("screenshots", []):
                                    if "timestamp" in screenshot:
                                        if not isinstance(screenshot["timestamp"], str):
                                            screenshot["timestamp"] = screenshot["timestamp"].isoformat()
                                await mongodb_store.db.sessions.insert_one(session_dict)
                            report["sessions_migrated"] += 1
                except Exception as e:
                    report["errors"].append(f"Failed to migrate session {session.id}: {str(e)}")
        except Exception as e:
            report["errors"].append(f"Failed to list sessions: {str(e)}")
        
        # Close MongoDB connection
        await mongodb_store.close()
        
    except Exception as e:
        report["errors"].append(f"Migration failed: {str(e)}")
    
    return report


async def migrate_json_to_postgresql(postgresql_config: DatabaseConfig) -> Dict[str, any]:
    """
    Migrate all operations and sessions from JSON files to PostgreSQL.
    
    Args:
        postgresql_config: PostgreSQL configuration
        
    Returns:
        Migration report dictionary with counts and errors
    """
    return {
        "operations_migrated": 0,
        "sessions_migrated": 0,
        "errors": ["PostgreSQL storage is not yet implemented"]
    }


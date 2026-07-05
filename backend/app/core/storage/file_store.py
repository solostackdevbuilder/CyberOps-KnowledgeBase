"""
File-based storage for sessions, terminal logs, and screenshots.
Handles all file I/O operations for the knowledge base.

Terminal content (the canonical copy in `terminal_logs/<id>.txt`) is
encrypted at rest via `TerminalContentCipher` when
`CYBEROPS_CREDENTIALS_KEY` is set. Session metadata JSONs keep
`terminal_content` zeroed out so the only place the content exists on
disk is the encrypted `.txt` file. See `terminal_encryption.py` for
the threat model.
"""
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import List, Optional
from uuid import uuid4

import aiofiles
from aiofiles import os as aios

from app.config import settings
from app.core.models import Session, SessionCreate, SessionUpdate
from app.core.models import FAAItem, FAAItemCreate, FAAItemUpdate
from app.core.storage.terminal_encryption import TerminalContentCipher

logger = logging.getLogger(__name__)


class FileStore:
    """File-based storage implementation for sessions."""

    def __init__(self, cipher: Optional[TerminalContentCipher] = None):
        """Initialize the file store with directory paths.

        Args:
            cipher: Terminal content cipher. Defaults to a new
                `TerminalContentCipher()` which reads the key from
                the environment. Tests inject a custom one.
        """
        self.sessions_dir = settings.sessions_dir
        self.terminal_logs_dir = settings.terminal_logs_dir
        self.screenshots_dir = settings.screenshots_dir
        self.faa_dir = settings.faa_dir
        self.cipher = cipher if cipher is not None else TerminalContentCipher()
    
    async def _ensure_directories(self) -> None:
        """Ensure all required directories exist."""
        for directory in [self.sessions_dir, self.terminal_logs_dir, self.screenshots_dir, self.faa_dir]:
            try:
                await aios.makedirs(directory, exist_ok=True)
            except Exception as e:
                raise RuntimeError(f"Failed to create directory {directory}: {e}")
    
    async def create_session(self, session_data: SessionCreate) -> Session:
        """
        Create a new session and save both JSON metadata and terminal content.
        
        Args:
            session_data: Session creation data
            
        Returns:
            Created session with generated ID and timestamps
        """
        await self._ensure_directories()
        
        # Generate unique session ID
        session_id = str(uuid4())
        now = datetime.utcnow()
        
        # Create session object
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
        
        # Save session metadata as JSON. terminal_content is stored
        # ONLY in the encrypted .txt file; zero it out in the JSON so a
        # leaked sessions/ directory exposes metadata but not evidence.
        session_file = self.sessions_dir / f"{session_id}.json"
        session_dict = session.model_dump(mode="json")
        session_dict["terminal_content"] = ""
        # Convert datetime objects to ISO format strings
        session_dict["created_at"] = session.created_at.isoformat()
        session_dict["updated_at"] = session.updated_at.isoformat()
        for screenshot in session_dict.get("screenshots", []):
            if "timestamp" in screenshot:
                screenshot["timestamp"] = screenshot["timestamp"].isoformat() if isinstance(screenshot["timestamp"], datetime) else screenshot["timestamp"]

        async with aiofiles.open(session_file, "w", encoding="utf-8") as f:
            await f.write(json.dumps(session_dict, indent=2, ensure_ascii=False))

        # Save terminal content as text file (encrypted if the key is set).
        terminal_file = self.terminal_logs_dir / f"{session_id}.txt"
        encrypted_content = self.cipher.encrypt(session_data.terminal_content)
        async with aiofiles.open(terminal_file, "w", encoding="utf-8") as f:
            await f.write(encrypted_content)

        return session
    
    async def get_session(self, session_id: str) -> Optional[Session]:
        """
        Retrieve a session by ID, loading both metadata and terminal content.
        
        Args:
            session_id: Unique session identifier
            
        Returns:
            Session object if found, None otherwise
        """
        session_file = self.sessions_dir / f"{session_id}.json"
        terminal_file = self.terminal_logs_dir / f"{session_id}.txt"
        
        # Check if session exists
        try:
            if not await aios.path.exists(session_file):
                return None
        except Exception:
            return None
        
        try:
            # Load session metadata
            async with aiofiles.open(session_file, "r", encoding="utf-8") as f:
                content = await f.read()
                session_dict = json.loads(content)
            
            # Load terminal content (may be encrypted on disk).
            terminal_content = ""
            had_plaintext_legacy = False
            if await aios.path.exists(terminal_file):
                async with aiofiles.open(terminal_file, "r", encoding="utf-8") as f:
                    raw = await f.read()
                terminal_content, had_plaintext_legacy = self.cipher.decrypt(raw)

            # Update session dict with terminal content
            session_dict["terminal_content"] = terminal_content

            # Transparent migration: legacy plaintext terminal log gets
            # re-encrypted on first read under a configured key.
            if had_plaintext_legacy and self.cipher.encryption_enabled:
                logger.info(
                    "Migrating plaintext terminal log for session '%s' to "
                    "encrypted form", session_id,
                )
                encrypted = self.cipher.encrypt(terminal_content)
                async with aiofiles.open(terminal_file, "w", encoding="utf-8") as f:
                    await f.write(encrypted)
            
            # Parse datetime strings back to datetime objects
            session_dict["created_at"] = datetime.fromisoformat(session_dict["created_at"])
            session_dict["updated_at"] = datetime.fromisoformat(session_dict["updated_at"])
            for screenshot in session_dict.get("screenshots", []):
                if "timestamp" in screenshot:
                    screenshot["timestamp"] = datetime.fromisoformat(screenshot["timestamp"])
            
            return Session(**session_dict)
        except Exception as e:
            raise RuntimeError(f"Failed to load session {session_id}: {e}")
    
    async def list_sessions(self) -> List[Session]:
        """
        List all sessions by loading JSON metadata files only.
        Terminal content is not loaded for performance.
        
        Returns:
            List of session objects (without terminal content initially)
        """
        await self._ensure_directories()
        
        sessions = []
        
        try:
            # Get all JSON files in sessions directory
            if not await aios.path.exists(self.sessions_dir):
                return sessions
            
            files = []
            async for file_path in self._list_files(self.sessions_dir):
                if file_path.suffix == ".json":
                    files.append(file_path)
            
            # Load each session metadata
            for session_file in files:
                try:
                    async with aiofiles.open(session_file, "r", encoding="utf-8") as f:
                        content = await f.read()
                        session_dict = json.loads(content)
                    
                    # Parse datetime strings
                    session_dict["created_at"] = datetime.fromisoformat(session_dict["created_at"])
                    session_dict["updated_at"] = datetime.fromisoformat(session_dict["updated_at"])
                    for screenshot in session_dict.get("screenshots", []):
                        if "timestamp" in screenshot:
                            screenshot["timestamp"] = datetime.fromisoformat(screenshot["timestamp"])
                    
                    # Load terminal content for search functionality
                    # Performance note: For large datasets, consider a dedicated search endpoint
                    terminal_file = self.terminal_logs_dir / f"{session_dict['id']}.txt"
                    try:
                        if await aios.path.exists(terminal_file):
                            async with aiofiles.open(terminal_file, "r", encoding="utf-8") as tf:
                                raw = await tf.read()
                            decoded, had_plaintext_legacy = self.cipher.decrypt(raw)
                            session_dict["terminal_content"] = decoded
                            if had_plaintext_legacy and self.cipher.encryption_enabled:
                                logger.info(
                                    "Migrating plaintext terminal log for "
                                    "session '%s' to encrypted form",
                                    session_dict["id"],
                                )
                                async with aiofiles.open(terminal_file, "w", encoding="utf-8") as tf:
                                    await tf.write(self.cipher.encrypt(decoded))
                        else:
                            session_dict["terminal_content"] = ""
                    except Exception:
                        session_dict["terminal_content"] = ""
                    
                    sessions.append(Session(**session_dict))
                except Exception as e:
                    # Skip corrupted files but log the error
                    print(f"Warning: Failed to load session from {session_file}: {e}")
                    continue
            
            # Sort by updated_at descending (most recent first)
            sessions.sort(key=lambda s: s.updated_at, reverse=True)
            
        except Exception as e:
            raise RuntimeError(f"Failed to list sessions: {e}")
        
        return sessions
    
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
    
    async def update_session(self, session_id: str, update_data: SessionUpdate) -> Optional[Session]:
        """
        Update an existing session.
        
        Args:
            session_id: Unique session identifier
            update_data: Fields to update
            
        Returns:
            Updated session if found, None otherwise
        """
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
        
        # Save updated session. terminal_content stays ONLY in the
        # encrypted .txt file; zero it out in the metadata JSON.
        session_file = self.sessions_dir / f"{session_id}.json"
        session_dict = session.model_dump(mode="json")
        session_dict["terminal_content"] = ""
        session_dict["created_at"] = session.created_at.isoformat()
        session_dict["updated_at"] = session.updated_at.isoformat()
        for screenshot in session_dict.get("screenshots", []):
            if "timestamp" in screenshot:
                screenshot["timestamp"] = screenshot["timestamp"].isoformat() if isinstance(screenshot["timestamp"], datetime) else screenshot["timestamp"]

        async with aiofiles.open(session_file, "w", encoding="utf-8") as f:
            await f.write(json.dumps(session_dict, indent=2, ensure_ascii=False))

        # Update terminal content file if changed (encrypted on write).
        if update_data.terminal_content is not None:
            terminal_file = self.terminal_logs_dir / f"{session_id}.txt"
            encrypted = self.cipher.encrypt(update_data.terminal_content)
            async with aiofiles.open(terminal_file, "w", encoding="utf-8") as f:
                await f.write(encrypted)

        return session
    
    async def delete_session(self, session_id: str) -> bool:
        """
        Delete a session and all associated files.
        
        Args:
            session_id: Unique session identifier
            
        Returns:
            True if session was deleted, False if not found
        """
        session_file = self.sessions_dir / f"{session_id}.json"
        terminal_file = self.terminal_logs_dir / f"{session_id}.txt"
        
        deleted = False
        
        # Delete session metadata
        try:
            if await aios.path.exists(session_file):
                await aios.remove(session_file)
                deleted = True
        except Exception as e:
            raise RuntimeError(f"Failed to delete session file {session_file}: {e}")
        
        # Delete terminal log
        try:
            if await aios.path.exists(terminal_file):
                await aios.remove(terminal_file)
        except Exception as e:
            print(f"Warning: Failed to delete terminal file {terminal_file}: {e}")
        
        # Delete associated screenshots
        try:
            if await aios.path.exists(self.screenshots_dir):
                async for file_path in self._list_files(self.screenshots_dir):
                    if session_id in file_path.name:
                        try:
                            await aios.remove(file_path)
                        except Exception as e:
                            print(f"Warning: Failed to delete screenshot {file_path}: {e}")
        except Exception as e:
            print(f"Warning: Failed to cleanup screenshots for session {session_id}: {e}")
        
        return deleted
    
    # ============================================================================
    # FAA (Findings and Actions) Methods
    # ============================================================================
    
    def _get_faa_session_dir(self, session_id: str) -> Path:
        """Get the directory path for FAA items of a session."""
        return self.faa_dir / session_id
    
    async def create_faa_item(self, faa_data: FAAItemCreate) -> FAAItem:
        """
        Create a new FAA item and save as JSON.
        
        Args:
            faa_data: FAA item creation data
            
        Returns:
            Created FAA item with generated ID and timestamps
        """
        await self._ensure_directories()
        
        # Generate unique FAA item ID
        faa_id = str(uuid4())
        now = datetime.utcnow()
        
        # Create FAA item object
        faa_item = FAAItem(
            id=faa_id,
            session_id=faa_data.session_id,
            classification=faa_data.classification,
            content=faa_data.content,
            output=faa_data.output,
            mitre_technique=faa_data.mitre_technique,
            mitre_tactic=faa_data.mitre_tactic,
            severity=faa_data.severity,
            timestamp=faa_data.timestamp,
            source=faa_data.source,
            confidence_score=1.0 if faa_data.source == "manual" else 0.5,  # Manual items have high confidence
            manually_corrected=False,
            notes=faa_data.notes,
            created_at=now,
            updated_at=now
        )
        
        # Ensure session directory exists
        session_dir = self._get_faa_session_dir(faa_data.session_id)
        await aios.makedirs(session_dir, exist_ok=True)
        
        # Save FAA item as JSON
        faa_file = session_dir / f"{faa_id}.json"
        faa_dict = faa_item.model_dump(mode="json")
        # Convert datetime objects to ISO format strings
        faa_dict["timestamp"] = faa_item.timestamp.isoformat()
        faa_dict["created_at"] = faa_item.created_at.isoformat()
        faa_dict["updated_at"] = faa_item.updated_at.isoformat()
        
        async with aiofiles.open(faa_file, "w", encoding="utf-8") as f:
            await f.write(json.dumps(faa_dict, indent=2, ensure_ascii=False))
        
        return faa_item
    
    async def get_faa_item(self, faa_id: str, session_id: str) -> Optional[FAAItem]:
        """
        Retrieve an FAA item by ID.
        
        Args:
            faa_id: Unique FAA item identifier
            session_id: Session ID to locate the item
            
        Returns:
            FAA item object if found, None otherwise
        """
        session_dir = self._get_faa_session_dir(session_id)
        faa_file = session_dir / f"{faa_id}.json"
        
        # Check if file exists
        try:
            if not await aios.path.exists(faa_file):
                return None
        except Exception:
            return None
        
        try:
            # Load FAA item
            async with aiofiles.open(faa_file, "r", encoding="utf-8") as f:
                content = await f.read()
                faa_dict = json.loads(content)
            
            # Parse datetime strings back to datetime objects
            faa_dict["timestamp"] = datetime.fromisoformat(faa_dict["timestamp"])
            faa_dict["created_at"] = datetime.fromisoformat(faa_dict["created_at"])
            faa_dict["updated_at"] = datetime.fromisoformat(faa_dict["updated_at"])
            
            return FAAItem(**faa_dict)
        except Exception as e:
            raise RuntimeError(f"Failed to load FAA item {faa_id}: {e}")
    
    async def list_faa_items(
        self,
        session_id: str,
        classification: Optional[str] = None,
        mitre_technique: Optional[str] = None,
        severity: Optional[str] = None
    ) -> List[FAAItem]:
        """
        List all FAA items for a session with optional filters.
        
        Args:
            session_id: Session ID to get items for
            classification: Optional filter by classification (action/finding)
            mitre_technique: Optional filter by MITRE technique
            severity: Optional filter by severity (for findings)
            
        Returns:
            List of FAA item objects
        """
        await self._ensure_directories()
        
        session_dir = self._get_faa_session_dir(session_id)
        faa_items = []
        
        try:
            # Check if session directory exists
            if not await aios.path.exists(session_dir):
                return faa_items
            
            # Get all JSON files in session directory
            files = []
            async for file_path in self._list_files(session_dir):
                if file_path.suffix == ".json":
                    files.append(file_path)
            
            # Load each FAA item
            for faa_file in files:
                try:
                    async with aiofiles.open(faa_file, "r", encoding="utf-8") as f:
                        content = await f.read()
                        faa_dict = json.loads(content)
                    
                    # Apply filters
                    if classification and faa_dict.get("classification") != classification:
                        continue
                    if mitre_technique and faa_dict.get("mitre_technique") != mitre_technique:
                        continue
                    if severity and faa_dict.get("severity") != severity:
                        continue
                    
                    # Parse datetime strings
                    faa_dict["timestamp"] = datetime.fromisoformat(faa_dict["timestamp"])
                    faa_dict["created_at"] = datetime.fromisoformat(faa_dict["created_at"])
                    faa_dict["updated_at"] = datetime.fromisoformat(faa_dict["updated_at"])
                    
                    faa_items.append(FAAItem(**faa_dict))
                except Exception as e:
                    # Skip corrupted files but log the error
                    print(f"Warning: Failed to load FAA item from {faa_file}: {e}")
                    continue
            
            # Sort by timestamp descending (most recent first)
            faa_items.sort(key=lambda item: item.timestamp, reverse=True)
            
        except Exception as e:
            raise RuntimeError(f"Failed to list FAA items for session {session_id}: {e}")
        
        return faa_items
    
    async def update_faa_item(self, faa_id: str, session_id: str, update_data: FAAItemUpdate) -> Optional[FAAItem]:
        """
        Update an existing FAA item.
        
        Args:
            faa_id: Unique FAA item identifier
            session_id: Session ID to locate the item
            update_data: Fields to update
            
        Returns:
            Updated FAA item if found, None otherwise
        """
        faa_item = await self.get_faa_item(faa_id, session_id)
        if not faa_item:
            return None
        
        # Update fields if provided
        if update_data.classification is not None:
            faa_item.classification = update_data.classification
        if update_data.content is not None:
            faa_item.content = update_data.content
        if update_data.output is not None:
            faa_item.output = update_data.output
        if update_data.mitre_technique is not None:
            faa_item.mitre_technique = update_data.mitre_technique
        if update_data.mitre_tactic is not None:
            faa_item.mitre_tactic = update_data.mitre_tactic
        if update_data.severity is not None:
            faa_item.severity = update_data.severity
        if update_data.notes is not None:
            faa_item.notes = update_data.notes
        
        # Mark as manually corrected and update timestamp
        faa_item.manually_corrected = True
        faa_item.updated_at = datetime.utcnow()
        
        # Save updated FAA item
        session_dir = self._get_faa_session_dir(session_id)
        faa_file = session_dir / f"{faa_id}.json"
        faa_dict = faa_item.model_dump(mode="json")
        faa_dict["timestamp"] = faa_item.timestamp.isoformat()
        faa_dict["created_at"] = faa_item.created_at.isoformat()
        faa_dict["updated_at"] = faa_item.updated_at.isoformat()
        
        async with aiofiles.open(faa_file, "w", encoding="utf-8") as f:
            await f.write(json.dumps(faa_dict, indent=2, ensure_ascii=False))
        
        return faa_item
    
    async def delete_faa_item(self, faa_id: str, session_id: str) -> bool:
        """
        Delete an FAA item.
        
        Args:
            faa_id: Unique FAA item identifier
            session_id: Session ID to locate the item
            
        Returns:
            True if item was deleted, False if not found
        """
        session_dir = self._get_faa_session_dir(session_id)
        faa_file = session_dir / f"{faa_id}.json"
        
        deleted = False
        
        # Delete FAA item file
        try:
            if await aios.path.exists(faa_file):
                await aios.remove(faa_file)
                deleted = True
        except Exception as e:
            raise RuntimeError(f"Failed to delete FAA item file {faa_file}: {e}")
        
        return deleted
    
    async def save_faa_items(self, session_id: str, faa_items: List[FAAItem]) -> None:
        """
        Save multiple FAA items for a session (used by analysis).
        
        Args:
            session_id: Session ID
            faa_items: List of FAA items to save
        """
        await self._ensure_directories()
        
        # Ensure session directory exists
        session_dir = self._get_faa_session_dir(session_id)
        await aios.makedirs(session_dir, exist_ok=True)
        
        # Save each FAA item
        for faa_item in faa_items:
            faa_file = session_dir / f"{faa_item.id}.json"
            faa_dict = faa_item.model_dump(mode="json")
            # Convert datetime objects to ISO format strings
            faa_dict["timestamp"] = faa_item.timestamp.isoformat()
            faa_dict["created_at"] = faa_item.created_at.isoformat()
            faa_dict["updated_at"] = faa_item.updated_at.isoformat()
            
            async with aiofiles.open(faa_file, "w", encoding="utf-8") as f:
                await f.write(json.dumps(faa_dict, indent=2, ensure_ascii=False))


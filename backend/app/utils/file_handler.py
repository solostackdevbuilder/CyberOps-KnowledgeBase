"""
Utility functions for handling file uploads, especially screenshots.
"""
import hashlib
import re
from datetime import datetime
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

import aiofiles
import aiofiles.os as aios
from fastapi import UploadFile
from PIL import Image

from app.config import settings
from app.core.models import Screenshot


# Session IDs are UUID-shaped in all current call sites. The filename is built
# directly from this value, so any path separator or traversal marker would
# let a caller write outside screenshots_dir. Callers (red_team.routes,
# browser_extension plugin) also verify session existence upstream, but this
# is the final defense in depth before the disk write.
_SAFE_SESSION_ID = re.compile(r"^[A-Za-z0-9_\-]{1,64}$")


def _validate_session_id(session_id: str) -> None:
    """Reject session IDs that could escape screenshots_dir.

    Raises ValueError for empty, overlong, or path-bearing input.
    """
    if not isinstance(session_id, str) or not _SAFE_SESSION_ID.match(session_id):
        raise ValueError(
            "Invalid session_id: must be 1-64 chars of [A-Za-z0-9_-]"
        )


async def save_screenshot(
    file: UploadFile,
    session_id: str,
    description: Optional[str] = None,
    source_url: Optional[str] = None,
    source_title: Optional[str] = None,
) -> Screenshot:
    """
    Save an uploaded screenshot file and return screenshot metadata.

    Args:
        file: Uploaded file from FastAPI
        session_id: Session ID to associate the screenshot with
        description: Optional description of the screenshot

    Returns:
        Screenshot model with metadata

    Raises:
        ValueError: If file is not a valid image or session_id is malformed
        RuntimeError: If file save fails
    """
    _validate_session_id(session_id)

    # Ensure screenshots directory exists
    screenshots_dir = settings.screenshots_dir
    await _ensure_directory(screenshots_dir)
    
    # Validate file is an image
    try:
        # Read file content
        content = await file.read()
        await file.seek(0)  # Reset file pointer
        
        # Validate with PIL
        image = Image.open(file.file)
        image.verify()
        await file.seek(0)  # Reset again after verify
        
        # Get image format
        image_format = image.format.lower() if image.format else "png"
        
    except Exception as e:
        raise ValueError(f"Invalid image file: {e}")
    
    # Generate unique filename
    timestamp = datetime.utcnow()
    file_hash = hashlib.md5(content).hexdigest()[:8]
    extension = _get_extension_from_content_type(file.content_type) or image_format
    filename = f"{session_id}_{timestamp.strftime('%Y%m%d_%H%M%S')}_{file_hash}.{extension}"
    
    # Save file
    file_path = screenshots_dir / filename
    try:
        async with aiofiles.open(file_path, "wb") as f:
            # Read and write in chunks for large files
            await file.seek(0)
            while chunk := await file.read(8192):
                await f.write(chunk)
    except Exception as e:
        raise RuntimeError(f"Failed to save screenshot: {e}")
    
    source_domain: Optional[str] = None
    if source_url:
        try:
            source_domain = urlparse(source_url).hostname or None
        except Exception:
            source_domain = None

    screenshot = Screenshot(
        filename=filename,
        timestamp=timestamp,
        description=description,
        source_url=source_url,
        source_title=source_title,
        source_domain=source_domain,
    )

    return screenshot


def _get_extension_from_content_type(content_type: Optional[str]) -> Optional[str]:
    """
    Get file extension from MIME content type.
    
    Args:
        content_type: MIME content type string
        
    Returns:
        File extension without dot, or None if unknown
    """
    if not content_type:
        return None
    
    content_type_map = {
        "image/jpeg": "jpg",
        "image/jpg": "jpg",
        "image/png": "png",
        "image/gif": "gif",
        "image/webp": "webp",
        "image/bmp": "bmp",
    }
    
    return content_type_map.get(content_type.lower())


async def _ensure_directory(directory: Path) -> None:
    """
    Ensure a directory exists, creating it if necessary.
    
    Args:
        directory: Path to directory
    """
    try:
        await aios.makedirs(directory, exist_ok=True)
    except Exception as e:
        raise RuntimeError(f"Failed to create directory {directory}: {e}")


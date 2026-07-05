"""
Service for processing screenshots and extracting text using vision capabilities.
"""
import asyncio
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

from PIL import Image

from app.core.models import ScreenshotExtraction
from app.core.services.base_llm import BaseLLM

logger = logging.getLogger(__name__)

# Maximum file size for images (10MB)
MAX_IMAGE_SIZE = 10 * 1024 * 1024

# Allowed image extensions
ALLOWED_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".webp"}

# Timeout for extraction (30 seconds)
EXTRACTION_TIMEOUT = 30.0


async def process_screenshot(
    session_id: str,
    screenshot_path: str,
    filename: str,
    llm_service: BaseLLM
) -> ScreenshotExtraction:
    """
    Process a screenshot and extract text using LLM vision capabilities.
    
    Args:
        session_id: Session ID the screenshot belongs to
        screenshot_path: Full path to the screenshot file
        filename: Name of the screenshot file
        llm_service: LLM service instance to use for extraction
        
    Returns:
        ScreenshotExtraction with extraction results
    """
    logger.info(f"Starting vision extraction for {filename} using {llm_service.__class__.__name__}")
    
    # Check if LLM supports vision
    if not llm_service.supports_vision():
        logger.warning(f"LLM does not support vision, skipping extraction for {filename}")
        return ScreenshotExtraction(
            filename=filename,
            path=screenshot_path,
            uploaded_at=datetime.fromtimestamp(Path(screenshot_path).stat().st_mtime) if Path(screenshot_path).exists() else datetime.utcnow(),
            extracted_text=None,
            analysis=None,
            extraction_status="not_supported",
            error_message="Selected LLM does not support vision"
        )
    
    # Validate image file
    try:
        image_file = Path(screenshot_path)
        
        # Check file exists
        if not image_file.exists():
            logger.error(f"Screenshot file not found: {screenshot_path}")
            return ScreenshotExtraction(
                filename=filename,
                path=screenshot_path,
                uploaded_at=datetime.utcnow(),
                extracted_text=None,
                analysis=None,
                extraction_status="failed",
                error_message="Screenshot file not found"
            )
        
        # Check file extension
        if image_file.suffix.lower() not in ALLOWED_EXTENSIONS:
            logger.error(f"Invalid image format: {image_file.suffix}")
            return ScreenshotExtraction(
                filename=filename,
                path=screenshot_path,
                uploaded_at=datetime.fromtimestamp(image_file.stat().st_mtime),
                extracted_text=None,
                analysis=None,
                extraction_status="failed",
                error_message=f"Invalid image format: {image_file.suffix}. Allowed: {', '.join(ALLOWED_EXTENSIONS)}"
            )
        
        # Check file size
        file_size = image_file.stat().st_size
        if file_size > MAX_IMAGE_SIZE:
            logger.warning(f"Image file is large ({file_size / 1024 / 1024:.2f}MB), may cause issues")
        
        # Validate image with PIL
        try:
            with Image.open(image_file) as img:
                img.verify()
            # Reopen for actual use (verify closes the file)
            with Image.open(image_file) as img:
                img.load()  # Load image data
        except Exception as e:
            logger.error(f"Invalid or corrupted image file: {e}")
            return ScreenshotExtraction(
                filename=filename,
                path=screenshot_path,
                uploaded_at=datetime.fromtimestamp(image_file.stat().st_mtime),
                extracted_text=None,
                analysis=None,
                extraction_status="failed",
                error_message=f"Invalid image file or corrupted data: {str(e)}"
            )
        
        # Get upload timestamp (convert to datetime)
        uploaded_at = datetime.fromtimestamp(image_file.stat().st_mtime)
        
    except Exception as e:
        logger.error(f"Error validating image file: {e}")
        return ScreenshotExtraction(
            filename=filename,
            path=screenshot_path,
            uploaded_at=0,
            extracted_text=None,
            analysis=None,
            extraction_status="failed",
            error_message=f"Error validating image: {str(e)}"
        )
    
    # Perform extraction with timeout
    try:
        logger.info(f"Calling LLM vision API for {filename}")
        start_time = asyncio.get_event_loop().time()
        
        # Call LLM with timeout
        result = await asyncio.wait_for(
            llm_service.extract_from_image(str(screenshot_path)),
            timeout=EXTRACTION_TIMEOUT
        )
        
        elapsed_time = asyncio.get_event_loop().time() - start_time
        logger.info(f"Successfully extracted {len(result.extracted_text)} characters from {filename} in {elapsed_time:.2f} seconds")
        
        # Check if text was extracted
        if not result.extracted_text or result.extracted_text.strip() == "" or result.extracted_text.strip() == "No text detected":
            logger.warning(f"No text found in image {filename}")
            return ScreenshotExtraction(
                filename=filename,
                path=screenshot_path,
                uploaded_at=uploaded_at,
                extracted_text="",
                analysis=result.analysis or "Image contains no readable text",
                extraction_status="no_text",
                error_message=None
            )
        
        # Success
        return ScreenshotExtraction(
            filename=filename,
            path=screenshot_path,
            uploaded_at=uploaded_at,
            extracted_text=result.extracted_text,
            analysis=result.analysis,
            extraction_status="success",
            error_message=None
        )
        
    except asyncio.TimeoutError:
        logger.error(f"Vision extraction timeout for {filename} after {EXTRACTION_TIMEOUT} seconds")
        return ScreenshotExtraction(
            filename=filename,
            path=screenshot_path,
            uploaded_at=uploaded_at,
            extracted_text=None,
            analysis=None,
            extraction_status="failed",
            error_message=f"Extraction timeout after {EXTRACTION_TIMEOUT} seconds"
        )
    
    except Exception as e:
        error_msg = str(e)
        logger.error(f"Vision extraction failed for {filename}: {error_msg}")
        
        # Check for specific error types
        if "API error" in error_msg or "API" in error_msg:
            error_message = f"LLM API error: {error_msg}"
        elif "not found" in error_msg.lower():
            error_message = f"Image file not found: {error_msg}"
        else:
            error_message = f"Extraction failed: {error_msg}"
        
        return ScreenshotExtraction(
            filename=filename,
            path=screenshot_path,
            uploaded_at=uploaded_at,
            extracted_text=None,
            analysis=None,
            extraction_status="failed",
            error_message=error_message
        )


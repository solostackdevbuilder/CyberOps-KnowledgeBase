"""
FastAPI exception handlers for custom exceptions.
Maps application exceptions to appropriate HTTP responses.

Unhandled exceptions go through a catch-all handler that returns a
generic shape with a correlation_id. The full exception and traceback
are logged server-side keyed by that id. Clients get a stable,
non-leaky message they can report back; operators can grep the log
for the id to find the root cause.
"""
import logging
import uuid
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.core.exceptions import (
    RedTeamKBError,
    StorageError,
    StorageConnectionError,
    StorageNotFoundError,
    StorageWriteError,
    StorageReadError,
    LLMError,
    LLMNotConfiguredError,
    LLMConnectionError,
    LLMRateLimitError,
    LLMResponseError,
    LLMContextTooLongError,
    ValidationError,
    ProcessingError,
    ExtractionError,
    CacheError,
    FileError,
    FileUploadError,
    UnsupportedFileTypeError,
)

logger = logging.getLogger(__name__)


def _new_correlation_id() -> str:
    """Short, copy-pasteable id clients can report back to operators."""
    return uuid.uuid4().hex[:12]


def register_exception_handlers(app: FastAPI) -> None:
    """
    Register all custom exception handlers with the FastAPI app.
    
    Args:
        app: FastAPI application instance
    """
    
    @app.exception_handler(StorageNotFoundError)
    async def storage_not_found_handler(request: Request, exc: StorageNotFoundError):
        """Handle resource not found errors - 404."""
        logger.warning(f"Resource not found: {exc.resource_type}/{exc.resource_id}")
        return JSONResponse(
            status_code=404,
            content={
                "error": "not_found",
                "message": exc.message,
                "resource_type": exc.resource_type,
                "resource_id": exc.resource_id
            }
        )
    
    @app.exception_handler(StorageConnectionError)
    async def storage_connection_handler(request: Request, exc: StorageConnectionError):
        """Handle storage connection errors - 503."""
        logger.error(f"Storage connection error: {exc.message}")
        return JSONResponse(
            status_code=503,
            content={
                "error": "storage_unavailable",
                "message": "Storage backend is temporarily unavailable. Please try again.",
                "detail": exc.message
            }
        )
    
    @app.exception_handler(StorageWriteError)
    async def storage_write_handler(request: Request, exc: StorageWriteError):
        """Handle storage write errors - 503."""
        logger.error(f"Storage write error: {exc.message}")
        return JSONResponse(
            status_code=503,
            content={
                "error": "storage_write_failed",
                "message": "Failed to save data. Please try again.",
                "detail": exc.message
            }
        )
    
    @app.exception_handler(StorageReadError)
    async def storage_read_handler(request: Request, exc: StorageReadError):
        """Handle storage read errors - 503."""
        logger.error(f"Storage read error: {exc.message}")
        return JSONResponse(
            status_code=503,
            content={
                "error": "storage_read_failed",
                "message": "Failed to retrieve data. Please try again.",
                "detail": exc.message
            }
        )
    
    @app.exception_handler(StorageError)
    async def storage_error_handler(request: Request, exc: StorageError):
        """Handle general storage errors - 503."""
        logger.error(f"Storage error: {exc.message}")
        return JSONResponse(
            status_code=503,
            content={
                "error": "storage_error",
                "message": "Storage operation failed. Please try again.",
                "detail": exc.message
            }
        )
    
    @app.exception_handler(LLMNotConfiguredError)
    async def llm_not_configured_handler(request: Request, exc: LLMNotConfiguredError):
        """Handle LLM not configured errors - 503."""
        logger.warning(f"LLM not configured: {exc.message}")
        return JSONResponse(
            status_code=503,
            content={
                "error": "llm_not_configured",
                "message": exc.message,
                "action": "Please configure LLM settings in the Settings page."
            }
        )
    
    @app.exception_handler(LLMConnectionError)
    async def llm_connection_handler(request: Request, exc: LLMConnectionError):
        """Handle LLM connection errors - 502."""
        logger.error(f"LLM connection error: {exc.message}")
        return JSONResponse(
            status_code=502,
            content={
                "error": "llm_connection_failed",
                "message": "Failed to connect to LLM service. Please try again.",
                "detail": exc.message
            }
        )
    
    @app.exception_handler(LLMRateLimitError)
    async def llm_rate_limit_handler(request: Request, exc: LLMRateLimitError):
        """Handle LLM rate limit errors - 429."""
        logger.warning(f"LLM rate limit exceeded: {exc.message}")
        return JSONResponse(
            status_code=429,
            content={
                "error": "llm_rate_limited",
                "message": "LLM API rate limit exceeded. Please wait and try again.",
                "detail": exc.message
            }
        )
    
    @app.exception_handler(LLMResponseError)
    async def llm_response_handler(request: Request, exc: LLMResponseError):
        """Handle LLM response parsing errors - 502."""
        logger.error(f"LLM response error: {exc.message}")
        return JSONResponse(
            status_code=502,
            content={
                "error": "llm_response_invalid",
                "message": "LLM returned an invalid response. Please try again.",
                "detail": exc.message
            }
        )
    
    @app.exception_handler(LLMContextTooLongError)
    async def llm_context_handler(request: Request, exc: LLMContextTooLongError):
        """Handle context too long errors - 413."""
        logger.warning(f"LLM context too long: {exc.message}")
        return JSONResponse(
            status_code=413,
            content={
                "error": "context_too_long",
                "message": "The request context is too large. Try selecting fewer sessions.",
                "detail": exc.message
            }
        )
    
    @app.exception_handler(LLMError)
    async def llm_error_handler(request: Request, exc: LLMError):
        """Handle general LLM errors - 502."""
        logger.error(f"LLM error: {exc.message}")
        return JSONResponse(
            status_code=502,
            content={
                "error": "llm_error",
                "message": "LLM service error. Please try again.",
                "detail": exc.message
            }
        )
    
    @app.exception_handler(ValidationError)
    async def validation_error_handler(request: Request, exc: ValidationError):
        """Handle validation errors - 422."""
        logger.warning(f"Validation error: {exc.message}")
        return JSONResponse(
            status_code=422,
            content={
                "error": "validation_error",
                "message": exc.message,
                "field": exc.field
            }
        )
    
    @app.exception_handler(UnsupportedFileTypeError)
    async def unsupported_file_handler(request: Request, exc: UnsupportedFileTypeError):
        """Handle unsupported file type errors - 415."""
        logger.warning(f"Unsupported file type: {exc.file_type}")
        return JSONResponse(
            status_code=415,
            content={
                "error": "unsupported_file_type",
                "message": exc.message,
                "file_type": exc.file_type,
                "supported_types": exc.supported_types
            }
        )
    
    @app.exception_handler(FileUploadError)
    async def file_upload_handler(request: Request, exc: FileUploadError):
        """Handle file upload errors - 400."""
        logger.error(f"File upload error: {exc.message}")
        return JSONResponse(
            status_code=400,
            content={
                "error": "file_upload_failed",
                "message": exc.message
            }
        )
    
    @app.exception_handler(FileError)
    async def file_error_handler(request: Request, exc: FileError):
        """Handle general file errors - 400."""
        logger.error(f"File error: {exc.message}")
        return JSONResponse(
            status_code=400,
            content={
                "error": "file_error",
                "message": exc.message
            }
        )
    
    @app.exception_handler(ExtractionError)
    async def extraction_error_handler(request: Request, exc: ExtractionError):
        """Handle extraction errors - 422."""
        logger.error(f"Extraction error: {exc.message}")
        return JSONResponse(
            status_code=422,
            content={
                "error": "extraction_failed",
                "message": exc.message
            }
        )
    
    @app.exception_handler(ProcessingError)
    async def processing_error_handler(request: Request, exc: ProcessingError):
        """Handle processing errors - 500."""
        logger.error(f"Processing error: {exc.message}")
        return JSONResponse(
            status_code=500,
            content={
                "error": "processing_failed",
                "message": exc.message
            }
        )
    
    @app.exception_handler(CacheError)
    async def cache_error_handler(request: Request, exc: CacheError):
        """Handle cache errors - logged but not exposed to user."""
        logger.warning(f"Cache error (non-critical): {exc.message}")
        # Cache errors are generally non-critical, return 200 with warning
        return JSONResponse(
            status_code=200,
            content={
                "warning": "cache_error",
                "message": "Operation completed but caching failed.",
                "detail": exc.message
            }
        )
    
    @app.exception_handler(RedTeamKBError)
    async def base_error_handler(request: Request, exc: RedTeamKBError):
        """Handle base application errors - 500."""
        correlation_id = _new_correlation_id()
        logger.error(
            "Application error [correlation_id=%s]: %s",
            correlation_id, exc.message, exc_info=exc,
        )
        return JSONResponse(
            status_code=500,
            content={
                "error": "internal_error",
                "message": exc.message,
                "correlation_id": correlation_id,
            }
        )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception):
        """Catch-all for any exception not handled above.

        Until this handler existed, routes that did `raise
        HTTPException(500, detail=str(e))` (or let exceptions bubble
        uncaught) leaked Python tracebacks, file paths, version hints,
        and other recon value into the client response. This handler
        returns a generic shape with a correlation id; the full
        exception (including traceback) is written to the server log
        keyed by that id so operators can still diagnose incidents.
        """
        correlation_id = _new_correlation_id()
        logger.error(
            "Unhandled exception on %s %s [correlation_id=%s]",
            request.method, request.url.path, correlation_id,
            exc_info=exc,
        )
        return JSONResponse(
            status_code=500,
            content={
                "error": "internal_error",
                "message": "An unexpected error occurred. Contact the operator with the correlation id.",
                "correlation_id": correlation_id,
            }
        )


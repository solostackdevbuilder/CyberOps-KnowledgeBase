"""
Custom exceptions for the application.
Provides granular error types for better error handling and debugging.
"""
from typing import Optional


class RedTeamKBError(Exception):
    """Base exception for all application errors."""
    
    def __init__(self, message: str, details: Optional[str] = None):
        self.message = message
        self.details = details
        super().__init__(message)


# ============================================================================
# Storage Exceptions
# ============================================================================

class StorageError(RedTeamKBError):
    """Base exception for storage-related errors."""
    pass


class StorageConnectionError(StorageError):
    """Raised when storage backend connection fails."""
    pass


class StorageNotFoundError(StorageError):
    """Raised when a requested resource is not found in storage."""
    
    def __init__(self, resource_type: str, resource_id: str):
        self.resource_type = resource_type
        self.resource_id = resource_id
        super().__init__(
            message=f"{resource_type} not found: {resource_id}",
            details=f"Resource type: {resource_type}, ID: {resource_id}"
        )


class StorageWriteError(StorageError):
    """Raised when writing to storage fails."""
    pass


class StorageReadError(StorageError):
    """Raised when reading from storage fails."""
    pass


# ============================================================================
# LLM Exceptions
# ============================================================================

class LLMError(RedTeamKBError):
    """Base exception for LLM-related errors."""
    pass


class LLMNotConfiguredError(LLMError):
    """Raised when LLM service is not configured."""
    
    def __init__(self, message: str = "LLM service not configured"):
        super().__init__(message=message)


class LLMConnectionError(LLMError):
    """Raised when LLM API connection fails."""
    pass


class LLMRateLimitError(LLMError):
    """Raised when LLM API rate limit is exceeded."""
    pass


class LLMResponseError(LLMError):
    """Raised when LLM response is invalid or cannot be parsed."""
    pass


class LLMContextTooLongError(LLMError):
    """Raised when context exceeds LLM token limits."""
    pass


# ============================================================================
# Validation Exceptions
# ============================================================================

class ValidationError(RedTeamKBError):
    """Raised when input validation fails."""
    
    def __init__(self, field: str, message: str):
        self.field = field
        super().__init__(
            message=f"Validation error for '{field}': {message}",
            details=f"Field: {field}"
        )


class InvalidOperationError(ValidationError):
    """Raised when an invalid operation is attempted."""
    
    def __init__(self, message: str):
        super().__init__(field="operation", message=message)


class InvalidSessionError(ValidationError):
    """Raised when session data is invalid."""
    
    def __init__(self, message: str):
        super().__init__(field="session", message=message)


# ============================================================================
# Processing Exceptions
# ============================================================================

class ProcessingError(RedTeamKBError):
    """Base exception for processing-related errors."""
    pass


class ExtractionError(ProcessingError):
    """Raised when text extraction from documents fails."""
    pass


class AnalysisError(ProcessingError):
    """Raised when analysis/processing fails."""
    pass


class CacheError(RedTeamKBError):
    """Raised when cache operations fail."""
    pass


# ============================================================================
# File Exceptions
# ============================================================================

class FileError(RedTeamKBError):
    """Base exception for file-related errors."""
    pass


class FileNotFoundError(FileError):
    """Raised when a file is not found."""
    
    def __init__(self, filepath: str):
        self.filepath = filepath
        super().__init__(
            message=f"File not found: {filepath}",
            details=f"Path: {filepath}"
        )


class FileUploadError(FileError):
    """Raised when file upload fails."""
    pass


class UnsupportedFileTypeError(FileError):
    """Raised when file type is not supported."""
    
    def __init__(self, file_type: str, supported_types: list[str]):
        self.file_type = file_type
        self.supported_types = supported_types
        super().__init__(
            message=f"Unsupported file type: {file_type}. Supported: {', '.join(supported_types)}",
            details=f"Received: {file_type}, Expected: {supported_types}"
        )


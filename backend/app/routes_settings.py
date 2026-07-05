"""
API routes for application settings management.
"""
import logging
from typing import List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.models_settings import DatabaseConfig, LLMConfig, Settings
from app.core.storage.settings_store import SettingsStore
from app.core.services.llm_factory import get_llm_service
from app.integrations.notifications import send_test_notification
from app.core.exceptions import RedTeamKBError

logger = logging.getLogger(__name__)
from app.utils.connection_test import (
    test_llm_connection as test_llm_connection_util,
    test_mongodb_connection,
    test_ollama_connection,
    test_postgresql_connection,
)
from app.utils.migration import migrate_json_to_mongodb, migrate_json_to_postgresql

router = APIRouter(prefix="/api/settings", tags=["settings"])

# Initialize settings store
settings_store = SettingsStore()


class TestDatabaseRequest(BaseModel):
    """Request model for testing database connection."""
    database_config: DatabaseConfig


class TestLLMRequest(BaseModel):
    """Request model for testing LLM connection."""
    llm_config: LLMConfig


class TestWebhookRequest(BaseModel):
    """Request model for testing webhook."""
    service: str = "teams"


class TestResponse(BaseModel):
    """Response model for connection tests."""
    success: bool
    message: str


class MigrationRequest(BaseModel):
    """Request model for migration."""
    target_backend: str  # "mongodb" or "postgresql"
    database_config: DatabaseConfig


class MigrationResponse(BaseModel):
    """Response model for migration."""
    operations_migrated: int
    sessions_migrated: int
    errors: List[str]


@router.get("")
async def get_settings() -> dict:
    """
    Get current application settings with vision support flag.
    
    Returns:
        Settings object with llm_supports_vision field added
    """
    try:
        settings = await settings_store.load_settings()
        
        # Check vision support
        llm_supports_vision = False
        if settings.llm_config:
            try:
                llm_service = get_llm_service(settings)
                llm_supports_vision = llm_service.supports_vision()
            except Exception:
                # If LLM service can't be created, vision support is False
                llm_supports_vision = False
        
        # Convert settings to dict and add vision support flag
        settings_dict = settings.model_dump()
        settings_dict["llm_supports_vision"] = llm_supports_vision
        
        return settings_dict
    except Exception as e:
        raise RedTeamKBError("Failed to load settings") from e


@router.put("", response_model=Settings)
async def update_settings(settings: Settings) -> Settings:
    """
    Update application settings.
    Validates settings before saving.
    
    Args:
        settings: New settings to save
        
    Returns:
        Updated settings object
    """
    try:
        # Validate settings (Pydantic will validate automatically)
        # Save settings
        await settings_store.save_settings(settings)
        return settings
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Invalid settings: {str(e)}")
    except Exception as e:
        raise RedTeamKBError("Failed to save settings") from e


@router.post("/test-db", response_model=TestResponse)
async def test_database_connection(request: TestDatabaseRequest) -> TestResponse:
    """
    Test database connection with provided configuration.
    
    Args:
        request: Database configuration to test
        
    Returns:
        Test result with success status and message
    """
    try:
        # Determine backend from config or try both
        # For now, we'll try MongoDB first, then PostgreSQL
        success, message = await test_mongodb_connection(request.database_config)
        if not success:
            # Try PostgreSQL
            success, message = await test_postgresql_connection(request.database_config)
        return TestResponse(success=success, message=message)
    except Exception as e:
        return TestResponse(success=False, message=f"Connection test failed: {str(e)}")


@router.post("/test-llm", response_model=TestResponse)
async def test_llm_connection(request: TestLLMRequest) -> TestResponse:
    """
    Test LLM connection with provided configuration.
    
    Args:
        request: LLM configuration to test
        
    Returns:
        Test result with success status and message
    """
    try:
        success, message = await test_llm_connection_util(request.llm_config)
        return TestResponse(success=success, message=message)
    except Exception as e:
        return TestResponse(success=False, message=f"Connection test failed: {str(e)}")


@router.post("/migrate", response_model=MigrationResponse)
async def migrate_data(request: MigrationRequest) -> MigrationResponse:
    """
    Trigger migration from JSON storage to database storage.
    
    Args:
        request: Migration request with target backend and database config
        
    Returns:
        Migration report with counts and errors
    """
    try:
        if request.target_backend.lower() == "mongodb":
            report = await migrate_json_to_mongodb(request.database_config)
            return MigrationResponse(
                operations_migrated=report["operations_migrated"],
                sessions_migrated=report["sessions_migrated"],
                errors=report["errors"]
            )
        elif request.target_backend.lower() == "postgresql":
            report = await migrate_json_to_postgresql(request.database_config)
            return MigrationResponse(
                operations_migrated=report["operations_migrated"],
                sessions_migrated=report["sessions_migrated"],
                errors=report["errors"]
            )
        else:
            raise HTTPException(
                status_code=400,
                detail=f"Unsupported target backend: {request.target_backend}"
            )
    except Exception as e:
        raise RedTeamKBError("Migration failed") from e


@router.get("/ollama-models")
async def list_ollama_models(endpoint: str) -> dict:
    """
    List available Ollama models from remote server.
    
    Args:
        endpoint: Ollama server endpoint (query parameter)
        
    Returns:
        Dictionary with list of available models
    """
    try:
        from app.core.services.ollama_service import OllamaService
        
        # Create temporary service to list models
        service = OllamaService(endpoint=endpoint, model_name="llama2")
        models = await service.list_available_models()
        await service.close()
        
        return {"models": models, "endpoint": endpoint}
    except Exception as e:
        raise RedTeamKBError("Failed to list Ollama models") from e


@router.post("/test-webhook", response_model=TestResponse)
async def test_webhook(request: TestWebhookRequest) -> TestResponse:
    """
    Test webhook notification by sending a test message.
    
    Args:
        request: Test webhook request with service type
        
    Returns:
        Test result with success status and message
    """
    try:
        service = request.service.lower()
        settings = await settings_store.load_settings()
        
        if not settings.webhook_config:
            return TestResponse(
                success=False,
                message="Webhook configuration not found. Please configure webhooks in settings."
            )
        
        if not settings.webhook_config.enabled:
            return TestResponse(
                success=False,
                message="Webhook notifications are disabled. Please enable them in settings."
            )
        
        webhook_url = None
        if service == "teams":
            webhook_url = settings.webhook_config.teams_webhook_url
            if not webhook_url:
                return TestResponse(
                    success=False,
                    message="Teams webhook URL not configured. Please add a Teams webhook URL in settings."
                )
        elif service == "slack":
            webhook_url = settings.webhook_config.slack_webhook_url
            if not webhook_url:
                return TestResponse(
                    success=False,
                    message="Slack webhook URL not configured. Please add a Slack webhook URL in settings."
                )
        else:
            return TestResponse(
                success=False,
                message=f"Invalid service: {service}. Must be 'teams' or 'slack'."
            )
        
        success, message = await send_test_notification(webhook_url, service)
        return TestResponse(success=success, message=message)
        
    except Exception as e:
        logger.error(f"Failed to test webhook: {e}", exc_info=True)
        return TestResponse(
            success=False,
            message=f"Failed to test webhook: {str(e)}"
        )


class RefreshMITREResponse(BaseModel):
    """Response model for MITRE data refresh."""
    success: bool
    strategies_count: int
    message: str


class SuggestAssociationsRequest(BaseModel):
    """Request payload for entity association suggestions."""
    seed_name: str = Field(..., min_length=1, max_length=200, description="Entity seed; sent to the configured LLM provider as plaintext")
    max_items: int = Field(default=20, ge=1, le=50)


class SuggestAssociationsResponse(BaseModel):
    """Response payload for entity association suggestions.

    `provider_used` is populated so the caller (and the UI) can surface which
    external LLM saw the seed value. The seed itself bypasses the privacy
    replacement pipeline by design: it is the thing the user is trying to
    generate rules for, and sanitizing it would strip the context the LLM
    needs to suggest associations.
    """
    success: bool
    seed_name: str
    suggestions: List[str]
    message: str
    provider_used: Optional[str] = None


@router.post("/refresh-mitre", response_model=RefreshMITREResponse)
async def refresh_mitre_data() -> RefreshMITREResponse:
    """
    Refresh MITRE ATT&CK detection strategies from official source.
    
    Fetches the latest detection strategies from the MITRE ATT&CK STIX data
    repository and updates the local cache.
    
    Returns:
        Refresh result with count of strategies fetched
    """
    try:
        from app.utils.mitre_fetcher import update_detection_strategies_cache
        from app.modules.red_team.detection_strategies import reload_detection_strategy_service
        
        # Fetch and cache new data
        count = update_detection_strategies_cache()
        
        # Reload the service to pick up new data
        reload_detection_strategy_service()
        
        return RefreshMITREResponse(
            success=True,
            strategies_count=count,
            message=f"Successfully fetched {count} detection strategies from MITRE ATT&CK"
        )
    except Exception as e:
        logger.error(f"Failed to refresh MITRE data: {e}", exc_info=True)
        return RefreshMITREResponse(
            success=False,
            strategies_count=0,
            message=f"Failed to refresh MITRE data: {str(e)}"
        )


@router.post("/privacy/suggest-associations", response_model=SuggestAssociationsResponse)
async def suggest_entity_associations(
    request: SuggestAssociationsRequest,
) -> SuggestAssociationsResponse:
    """
    Generate one-time seed association suggestions using configured LLM provider.

    The generated list is returned to the caller for user review/edit before saving.
    """
    try:
        seed_name = request.seed_name.strip()
        if not seed_name:
            return SuggestAssociationsResponse(
                success=False,
                seed_name=request.seed_name,
                suggestions=[],
                message="seed_name is required",
            )

        max_items = max(1, min(request.max_items, 50))

        app_settings = await settings_store.load_settings()
        llm_service = get_llm_service(app_settings)
        provider_used = app_settings.llm_provider.value if app_settings.llm_provider else None
        prompt = (
            "You are helping build a privacy protection alias list.\n"
            f"Given company/entity seed: {seed_name}\n"
            "Return ONLY valid JSON with this exact schema:\n"
            '{"associations": ["term1", "term2"]}\n'
            "Include affiliated brands, subsidiaries, common aliases, and related entities.\n"
            f"Limit to at most {max_items} items.\n"
            "No prose, no markdown, no code fences."
        )
        response_text = await llm_service.query(
            question=prompt,
            context="",
            scope="single",
            operation_name=None,
        )

        from app.utils.json_sanitizer import JsonSanitizer

        parsed = JsonSanitizer.parse_llm_json(response_text)
        suggestions_raw = parsed.get("associations", []) if isinstance(parsed, dict) else []

        if not isinstance(suggestions_raw, list):
            suggestions_raw = []

        suggestions: List[str] = []
        seen = set()
        seed_key = seed_name.casefold()
        for item in suggestions_raw:
            value = str(item).strip()
            if not value:
                continue
            key = value.casefold()
            if key == seed_key or key in seen:
                continue
            suggestions.append(value)
            seen.add(key)
            if len(suggestions) >= max_items:
                break

        return SuggestAssociationsResponse(
            success=True,
            seed_name=seed_name,
            suggestions=suggestions,
            message=f"Generated {len(suggestions)} association suggestions",
            provider_used=provider_used,
        )
    except Exception as e:
        logger.error(f"Failed to suggest associations: {e}", exc_info=True)
        return SuggestAssociationsResponse(
            success=False,
            seed_name=request.seed_name,
            suggestions=[],
            message=f"Failed to suggest associations: {str(e)}",
        )


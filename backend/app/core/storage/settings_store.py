"""
Settings storage for loading and saving application settings.

Secret fields (LLM API key, database password, webhook URLs) are
encrypted at rest via SettingsEncryptor when CYBEROPS_CREDENTIALS_KEY
is set. Non-secret fields stay plaintext so the file remains
inspectable. See `settings_encryption.py` for the threat model.
"""
import json
import logging
from pathlib import Path
from typing import Optional

import aiofiles
from aiofiles import os as aios

from app.config import settings as app_settings
from app.core.storage.settings_encryption import SettingsEncryptor
from app.models_settings import (
    LLMConfig,
    LLMProvider,
    PrivacyReplacementSettings,
    Settings,
    StorageBackend,
    WebhookConfig,
)
from app.core.services.privacy_defaults import get_default_sensitive_config

logger = logging.getLogger(__name__)


class SettingsStore:
    """Storage for application settings."""

    def __init__(
        self,
        settings_file: Optional[Path] = None,
        encryptor: Optional[SettingsEncryptor] = None,
    ):
        """
        Initialize settings store.

        Args:
            settings_file: Path to settings file (defaults to data/settings.json)
            encryptor: Field-level encryptor. Defaults to a new
                `SettingsEncryptor()` which reads the key from the
                environment. Tests inject a custom one.
        """
        if settings_file is None:
            settings_file = Path(app_settings.data_dir) / "settings.json"
        self.settings_file = settings_file
        self.encryptor = encryptor if encryptor is not None else SettingsEncryptor()
    
    async def _ensure_directory(self) -> None:
        """Ensure the settings file directory exists."""
        try:
            await aios.makedirs(self.settings_file.parent, exist_ok=True)
        except Exception as e:
            raise RuntimeError(f"Failed to create directory {self.settings_file.parent}: {e}")
    
    async def load_settings(self) -> Settings:
        """
        Load settings from file, or return default settings if file doesn't exist.
        
        Returns:
            Settings object (default or loaded from file)
        """
        # Check if settings file exists
        try:
            if not await aios.path.exists(self.settings_file):
                # Return default settings
                return self._get_default_settings()
        except Exception:
            # If we can't check, return defaults
            return self._get_default_settings()
        
        try:
            # Load settings from file
            async with aiofiles.open(self.settings_file, "r", encoding="utf-8") as f:
                content = await f.read()
                settings_dict = json.loads(content)

            # Decrypt secret fields before Pydantic parses the dict; the
            # model types expect plain strings, not marker dicts.
            decrypted_dict, had_plaintext_secrets = self.encryptor.decrypt_secrets(
                settings_dict
            )

            # Parse settings
            parsed_settings = Settings(**decrypted_dict)

            # Bootstrap sensitive defaults for legacy settings files missing this section
            privacy_dict = decrypted_dict.get("privacy_replacements") if isinstance(decrypted_dict, dict) else None
            missing_sensitive_defaults = not privacy_dict or "sensitive_defaults" not in privacy_dict
            if missing_sensitive_defaults:
                parsed_settings.privacy_replacements.sensitive_defaults = get_default_sensitive_config()
                await self.save_settings(parsed_settings)
            elif had_plaintext_secrets and self.encryptor.encryption_enabled:
                # Transparent migration: legacy plaintext secrets get
                # re-saved in encrypted form on first read under a key.
                logger.info(
                    "Migrating plaintext secret fields in settings.json to "
                    "encrypted form"
                )
                await self.save_settings(parsed_settings)

            return parsed_settings
        except json.JSONDecodeError as e:
            raise RuntimeError(f"Failed to parse settings file: {e}")
        except Exception as e:
            raise RuntimeError(f"Failed to load settings: {e}")
    
    async def save_settings(self, settings: Settings) -> None:
        """
        Save settings to file.
        
        Args:
            settings: Settings object to save
        """
        await self._ensure_directory()
        
        try:
            # Convert settings to dict
            settings_dict = settings.model_dump(mode="json")

            # Encrypt secret fields in place before hitting disk.
            encrypted_dict = self.encryptor.encrypt_secrets(settings_dict)

            # Save to file
            async with aiofiles.open(self.settings_file, "w", encoding="utf-8") as f:
                await f.write(json.dumps(encrypted_dict, indent=2, ensure_ascii=False))
        except Exception as e:
            raise RuntimeError(f"Failed to save settings: {e}")
    
    def _get_default_settings(self) -> Settings:
        """
        Get default settings.
        
        Returns:
            Default Settings object
        """
        # Create default LLM config with Claude
        # Try to get API key from environment if available
        api_key = getattr(app_settings, "anthropic_api_key", None)
        if api_key and api_key != "your-key-here":
            llm_config = LLMConfig(
                provider=LLMProvider.CLAUDE,
                api_key=api_key,
                model_name="claude-sonnet-4-5-20250929"
            )
        else:
            llm_config = None
        
        # Create default webhook config with sample Teams webhook
        webhook_config = WebhookConfig(
            teams_webhook_url="https://outlook.office.com/webhook/YOUR_WEBHOOK_ID@YOUR_TENANT_ID/IncomingWebhook/YOUR_KEY/YOUR_KEY",
            enabled=False
        )
        
        return Settings(
            storage_backend=StorageBackend.JSON,
            llm_provider=LLMProvider.CLAUDE,
            llm_config=llm_config,
            webhook_config=webhook_config,
            privacy_replacements=PrivacyReplacementSettings(
                enabled=True,
                restore_on_output=True,
                apply_to_question=True,
                apply_to_context=True,
                apply_to_ai_output=True,
                strict_privacy_mode=True,
                sensitive_defaults=get_default_sensitive_config(),
            ),
        )


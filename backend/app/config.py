"""
Configuration settings for the CyberOps Knowledge Base application.
Uses Pydantic Settings to load configuration from environment variables.
"""
import os
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Load .env file
# Find .env file in the backend directory (parent of app/)
_BACKEND_ROOT = Path(__file__).resolve().parent.parent
env_path = _BACKEND_ROOT / ".env"
load_dotenv(dotenv_path=env_path, override=True)


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""
    
    # Anthropic API configuration (optional at boot; configure via Settings UI or .env)
    anthropic_api_key: Optional[str] = None
    
    # Data directory: default is backend/data regardless of process cwd (fixes empty UI when
    # uvicorn is started from repo root). Relative DATA_DIR in env is resolved vs backend root.
    data_dir: str = str(_BACKEND_ROOT / "data")
    
    # Context configuration for Claude queries
    max_context_sessions: int = 20
    
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore"
    )

    @field_validator("data_dir", mode="after")
    @classmethod
    def resolve_data_dir(cls, v: str) -> str:
        p = Path(v)
        if not p.is_absolute():
            return str((_BACKEND_ROOT / p).resolve())
        return str(p.resolve())
    
    @property
    def sessions_dir(self) -> Path:
        """Get the path to the sessions directory."""
        return Path(self.data_dir) / "sessions"
    
    @property
    def terminal_logs_dir(self) -> Path:
        """Get the path to the terminal logs directory."""
        return Path(self.data_dir) / "terminal_logs"
    
    @property
    def screenshots_dir(self) -> Path:
        """Get the path to the screenshots directory."""
        return Path(self.data_dir) / "screenshots"
    
    @property
    def operations_dir(self) -> Path:
        """Get the path to the operations directory."""
        return Path(self.data_dir) / "operations"
    
    @property
    def faa_dir(self) -> Path:
        """Get the path to the FAA (Findings and Actions) directory."""
        return Path(self.data_dir) / "red_team" / "faa"
    
    @property
    def query_cache_dir(self) -> Path:
        """Get the path to the query cache directory."""
        return Path(self.data_dir) / "query_cache"
    
    @property
    def simulations_dir(self) -> Path:
        """Get the path to the simulations directory."""
        return Path(self.data_dir) / "simulations"


# Global settings instance
settings = Settings()

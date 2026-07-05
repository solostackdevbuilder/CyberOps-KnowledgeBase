"""
Settings models for storage backend and LLM provider configuration.
"""
import re
from enum import Enum
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


class StorageBackend(str, Enum):
    """Storage backend options."""
    JSON = "json"
    MONGODB = "mongodb"
    POSTGRESQL = "postgresql"


class LLMProvider(str, Enum):
    """LLM provider options."""
    CLAUDE = "claude"
    OPENAI = "openai"
    OLLAMA = "ollama"


class DatabaseConfig(BaseModel):
    """Database connection configuration."""
    connection_string: Optional[str] = Field(
        None,
        description="Full connection string (alternative to individual fields)"
    )
    host: Optional[str] = Field(None, description="Database host")
    port: Optional[int] = Field(None, description="Database port")
    database_name: Optional[str] = Field(None, description="Database name")
    username: Optional[str] = Field(None, description="Database username")
    password: Optional[str] = Field(None, description="Database password")
    
    @field_validator("port")
    @classmethod
    def validate_port(cls, v: Optional[int]) -> Optional[int]:
        """Validate port is in valid range."""
        if v is not None and (v < 1 or v > 65535):
            raise ValueError("Port must be between 1 and 65535")
        return v


class LLMConfig(BaseModel):
    """LLM provider configuration."""
    model_config = ConfigDict(protected_namespaces=())
    
    provider: LLMProvider = Field(..., description="LLM provider")
    api_key: Optional[str] = Field(None, description="API key for the provider")
    endpoint: Optional[str] = Field(
        None,
        description="Custom endpoint/base URL (for Ollama or custom OpenAI endpoints)"
    )
    model_name: Optional[str] = Field(
        None,
        description="Model name to use (e.g., 'gpt-4-turbo', 'llama2', 'claude-sonnet-4-5-20250929')"
    )
    
    @field_validator("endpoint")
    @classmethod
    def validate_endpoint(cls, v: Optional[str]) -> Optional[str]:
        """Validate endpoint URL format."""
        if v is not None and not (v.startswith("http://") or v.startswith("https://")):
            raise ValueError("Endpoint must be a valid HTTP/HTTPS URL")
        return v


class WebhookConfig(BaseModel):
    """Webhook configuration for external integrations."""
    teams_webhook_url: Optional[str] = Field(
        None,
        description="Microsoft Teams webhook URL for notifications"
    )
    slack_webhook_url: Optional[str] = Field(
        None,
        description="Slack webhook URL for notifications"
    )
    enabled: bool = Field(
        default=False,
        description="Enable webhook notifications"
    )
    
    @field_validator("teams_webhook_url", "slack_webhook_url")
    @classmethod
    def validate_webhook_url(cls, v: Optional[str]) -> Optional[str]:
        """Validate webhook URL format."""
        if v is not None:
            # Strip whitespace
            v = v.strip()
            # Allow empty strings (will be converted to None)
            if v == "":
                return None
            # Validate URL format
            if not (v.startswith("http://") or v.startswith("https://")):
                raise ValueError("Webhook URL must be a valid HTTP/HTTPS URL")
        return v


class PrivacyMatchType(str, Enum):
    """Privacy replacement matching behavior."""
    SUBSTRING = "substring"
    EXACT = "exact"


class SensitiveRuleSeverity(str, Enum):
    """Severity buckets for built-in sensitive rules."""
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"


class GenerationSource(str, Enum):
    """How an entity group was generated."""
    MANUAL = "manual"
    EXTERNAL_AI = "external_ai"
    CURATED = "curated"


class PrivacyReplacementRule(BaseModel):
    """Single before/after privacy replacement rule."""
    id: str = Field(..., description="Unique rule identifier")
    before: str = Field(..., description="Sensitive value to protect")
    after: str = Field(..., description="Safe placeholder value")
    match_type: PrivacyMatchType = Field(
        default=PrivacyMatchType.SUBSTRING,
        description="Whether to replace exact text or substring matches",
    )
    case_sensitive: bool = Field(
        default=False,
        description="Use case-sensitive matching when true",
    )
    whole_word: bool = Field(
        default=False,
        description="Match only whole-word boundaries when true",
    )

    @field_validator("id", "before", "after")
    @classmethod
    def validate_required_non_empty(cls, v: str) -> str:
        """Ensure required string fields are not blank."""
        value = v.strip()
        if not value:
            raise ValueError("Field cannot be empty")
        return value

    @field_validator("after")
    @classmethod
    def validate_not_same_value(cls, v: str, info) -> str:
        """Prevent no-op replacement rules."""
        before_value = info.data.get("before")
        if before_value is not None and before_value == v:
            raise ValueError("before and after must be different")
        return v


class SensitiveKeywordRule(BaseModel):
    """Keyword-driven sensitive content protection rule."""
    id: str = Field(..., description="Unique keyword rule ID")
    name: str = Field(..., description="Human-readable rule name")
    keyword: str = Field(..., description="Keyword marker to detect")
    replacement: str = Field(..., description="Replacement value")
    severity: SensitiveRuleSeverity = Field(
        default=SensitiveRuleSeverity.HIGH,
        description="Sensitivity level for this rule",
    )
    case_sensitive: bool = Field(
        default=False,
        description="Whether matching is case-sensitive",
    )
    enabled: bool = Field(
        default=True,
        description="Whether this rule is active",
    )

    @field_validator("id", "name", "keyword", "replacement")
    @classmethod
    def validate_non_empty(cls, v: str) -> str:
        value = v.strip()
        if not value:
            raise ValueError("Field cannot be empty")
        return value


class SensitiveRegexRule(BaseModel):
    """Regex-driven sensitive content protection rule."""
    id: str = Field(..., description="Unique regex rule ID")
    name: str = Field(..., description="Human-readable rule name")
    pattern: str = Field(..., description="Regex pattern to match")
    replacement: str = Field(..., description="Replacement value")
    severity: SensitiveRuleSeverity = Field(
        default=SensitiveRuleSeverity.CRITICAL,
        description="Sensitivity level for this rule",
    )
    enabled: bool = Field(
        default=True,
        description="Whether this rule is active",
    )

    @field_validator("id", "name", "pattern", "replacement")
    @classmethod
    def validate_non_empty(cls, v: str) -> str:
        value = v.strip()
        if not value:
            raise ValueError("Field cannot be empty")
        return value


class SensitiveDefaultsConfig(BaseModel):
    """Built-in local sensitive protections."""
    enabled: bool = Field(
        default=True,
        description="Enable built-in sensitive defaults",
    )
    keyword_rules: list[SensitiveKeywordRule] = Field(
        default_factory=list,
        description="Sensitive keyword rules",
    )
    regex_rules: list[SensitiveRegexRule] = Field(
        default_factory=list,
        description="Sensitive regex rules",
    )


class DomainAliasConfig(BaseModel):
    """Configuration for protected domain alias generation."""
    enabled: bool = Field(
        default=True,
        description="Enable domain aliasing",
    )
    alias_suffix: str = Field(
        default="example.com",
        description="Suffix used for generated alias domains",
    )
    stable_scope: str = Field(
        default="global",
        description="Alias stability scope",
    )

    @field_validator("alias_suffix")
    @classmethod
    def validate_alias_suffix(cls, v: str) -> str:
        value = v.strip().lower()
        if not value or "." not in value:
            raise ValueError("alias_suffix must be a valid domain suffix")
        return value

    @field_validator("stable_scope")
    @classmethod
    def validate_scope(cls, v: str) -> str:
        value = v.strip().lower()
        if value not in {"global", "operation", "request"}:
            raise ValueError("stable_scope must be one of: global, operation, request")
        return value


class EntityGroup(BaseModel):
    """Seed-driven organization/entity association group."""
    id: str = Field(..., description="Unique group identifier")
    name: str = Field(..., description="Display name for the group")
    seed_name: str = Field(..., description="Seed entity used for association generation")
    associated_terms: list[str] = Field(
        default_factory=list,
        description="Associated aliases, brands, subsidiaries, or related terms",
    )
    enabled: bool = Field(
        default=True,
        description="Whether this entity group is active",
    )
    generated_at: Optional[str] = Field(
        None,
        description="ISO timestamp when suggestions were generated",
    )
    generation_source: GenerationSource = Field(
        default=GenerationSource.MANUAL,
        description="Source used to generate this entity group",
    )
    last_reviewed_at: Optional[str] = Field(
        None,
        description="ISO timestamp when user last reviewed this group",
    )

    @field_validator("id", "name", "seed_name")
    @classmethod
    def validate_required(cls, v: str) -> str:
        value = v.strip()
        if not value:
            raise ValueError("Field cannot be empty")
        return value

    @field_validator("associated_terms")
    @classmethod
    def validate_terms(cls, values: list[str]) -> list[str]:
        normalized: list[str] = []
        seen: set[str] = set()
        for value in values:
            term = value.strip()
            if not term:
                continue
            key = term.casefold()
            if key in seen:
                continue
            normalized.append(term)
            seen.add(key)
        return normalized


class PrivacyReplacementSettings(BaseModel):
    """Settings for privacy replacement before/after LLM calls."""
    enabled: bool = Field(
        default=True,
        description="Enable privacy replacement processing",
    )
    restore_on_output: bool = Field(
        default=True,
        description="Restore safe placeholders back to originals in responses",
    )
    apply_to_question: bool = Field(
        default=True,
        description="Apply protection to the user question payload",
    )
    apply_to_context: bool = Field(
        default=True,
        description="Apply protection to context payloads",
    )
    apply_to_ai_output: bool = Field(
        default=True,
        description="Apply restoration before returning AI outputs",
    )
    strict_privacy_mode: bool = Field(
        default=True,
        description="Block outbound AI calls when protected values remain unmasked",
    )
    domain_alias_config: DomainAliasConfig = Field(
        default_factory=DomainAliasConfig,
        description="Protected domain aliasing settings",
    )
    rules: list[PrivacyReplacementRule] = Field(
        default_factory=list,
        description="List of explicit before/after replacement rules",
    )
    entity_groups: list[EntityGroup] = Field(
        default_factory=list,
        description="Seeded entity association groups",
    )
    sensitive_defaults: SensitiveDefaultsConfig = Field(
        default_factory=SensitiveDefaultsConfig,
        description="Built-in keyword/regex sensitive protections",
    )
    custom_regex_rules: list[SensitiveRegexRule] = Field(
        default_factory=list,
        description="User-defined regex rules; applied when privacy protection is enabled",
    )

    @field_validator("custom_regex_rules")
    @classmethod
    def validate_custom_regex_rules(cls, rules: list[SensitiveRegexRule]) -> list[SensitiveRegexRule]:
        seen: set[str] = set()
        for rule in rules:
            if rule.id in seen:
                raise ValueError(f"Duplicate custom regex rule id: '{rule.id}'")
            seen.add(rule.id)
            try:
                re.compile(rule.pattern)
            except re.error as exc:
                raise ValueError(
                    f"Invalid regex pattern in rule '{rule.name}' ({rule.id}): {exc}"
                ) from exc
        return rules

    @field_validator("rules")
    @classmethod
    def validate_unique_before_rules(
        cls, rules: list[PrivacyReplacementRule]
    ) -> list[PrivacyReplacementRule]:
        """Reject duplicate source values across rules."""
        seen: set[str] = set()
        for rule in rules:
            key = rule.before.casefold()
            if key in seen:
                raise ValueError(
                    f"Duplicate replacement source detected: '{rule.before}'"
                )
            seen.add(key)
        return rules

    @field_validator("entity_groups")
    @classmethod
    def validate_unique_group_ids(
        cls, groups: list[EntityGroup]
    ) -> list[EntityGroup]:
        seen: set[str] = set()
        for group in groups:
            if group.id in seen:
                raise ValueError(f"Duplicate entity group id detected: '{group.id}'")
            seen.add(group.id)
        return groups


class Settings(BaseModel):
    """Application settings for storage and LLM configuration."""
    storage_backend: StorageBackend = Field(
        default=StorageBackend.JSON,
        description="Storage backend to use"
    )
    database_config: Optional[DatabaseConfig] = Field(
        None,
        description="Database configuration (required for MongoDB/PostgreSQL)"
    )
    llm_provider: LLMProvider = Field(
        default=LLMProvider.CLAUDE,
        description="LLM provider to use"
    )
    llm_config: Optional[LLMConfig] = Field(
        None,
        description="LLM provider configuration"
    )
    webhook_config: Optional[WebhookConfig] = Field(
        None,
        description="Webhook configuration for external integrations"
    )
    privacy_replacements: PrivacyReplacementSettings = Field(
        default_factory=PrivacyReplacementSettings,
        description="Privacy replacement rules for LLM input/output protection",
    )
    
    @field_validator("database_config")
    @classmethod
    def validate_database_config(cls, v: Optional[DatabaseConfig], info) -> Optional[DatabaseConfig]:
        """Validate database config is provided when needed."""
        storage_backend = info.data.get("storage_backend")
        if storage_backend in [StorageBackend.MONGODB, StorageBackend.POSTGRESQL]:
            if v is None:
                raise ValueError(
                    f"database_config is required when storage_backend is {storage_backend}"
                )
            # Validate that either connection_string or required fields are provided
            if not v.connection_string:
                if not v.host or not v.database_name:
                    raise ValueError(
                        "Either connection_string or (host and database_name) must be provided"
                    )
        return v
    
    @field_validator("llm_config")
    @classmethod
    def validate_llm_config(cls, v: Optional[LLMConfig], info) -> Optional[LLMConfig]:
        """Validate LLM config matches provider."""
        llm_provider = info.data.get("llm_provider")
        if llm_provider and v:
            if v.provider != llm_provider:
                raise ValueError(
                    f"llm_config.provider ({v.provider}) must match llm_provider ({llm_provider})"
                )
            # Validate API key for providers that require it
            if llm_provider in [LLMProvider.CLAUDE, LLMProvider.OPENAI]:
                if not v.api_key:
                    raise ValueError(f"api_key is required for {llm_provider} provider")
            # Validate endpoint for Ollama
            if llm_provider == LLMProvider.OLLAMA:
                if not v.endpoint:
                    raise ValueError("endpoint is required for Ollama provider")
        return v


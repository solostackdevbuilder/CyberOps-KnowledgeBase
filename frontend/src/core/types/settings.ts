export type StorageBackend = 'json' | 'mongodb' | 'postgresql';

export type LLMProvider = 'claude' | 'openai' | 'ollama';

export interface DatabaseConfig {
  connection_string?: string;
  host?: string;
  port?: number;
  database_name?: string;
  username?: string;
  password?: string;
}

export interface LLMConfig {
  provider: LLMProvider;
  api_key?: string;
  endpoint?: string;
  model_name?: string;
}

export interface WebhookConfig {
  teams_webhook_url?: string;
  slack_webhook_url?: string;
  enabled: boolean;
}

export type PrivacyMatchType = 'substring' | 'exact';
export type SensitiveRuleSeverity = 'critical' | 'high' | 'medium';
export type GenerationSource = 'manual' | 'external_ai' | 'curated';

export interface PrivacyReplacementRule {
  id: string;
  before: string;
  after: string;
  match_type: PrivacyMatchType;
  case_sensitive: boolean;
  whole_word: boolean;
}

export interface PrivacyReplacementSettings {
  enabled: boolean;
  restore_on_output: boolean;
  apply_to_question?: boolean;
  apply_to_context?: boolean;
  apply_to_ai_output?: boolean;
  strict_privacy_mode?: boolean;
  domain_alias_config?: DomainAliasConfig;
  rules: PrivacyReplacementRule[];
  entity_groups?: EntityGroup[];
  sensitive_defaults?: SensitiveDefaultsConfig;
  custom_regex_rules?: SensitiveRegexRule[];
}

export interface DomainAliasConfig {
  enabled: boolean;
  alias_suffix: string;
  stable_scope: 'global' | 'operation' | 'request';
}

export interface EntityGroup {
  id: string;
  name: string;
  seed_name: string;
  associated_terms: string[];
  enabled: boolean;
  generated_at?: string;
  generation_source?: GenerationSource;
  last_reviewed_at?: string;
}

export interface SensitiveKeywordRule {
  id: string;
  name: string;
  keyword: string;
  replacement: string;
  severity: SensitiveRuleSeverity;
  case_sensitive: boolean;
  enabled: boolean;
}

export interface SensitiveRegexRule {
  id: string;
  name: string;
  pattern: string;
  replacement: string;
  severity: SensitiveRuleSeverity;
  enabled: boolean;
}

export interface SensitiveDefaultsConfig {
  enabled: boolean;
  keyword_rules: SensitiveKeywordRule[];
  regex_rules: SensitiveRegexRule[];
}

export interface Settings {
  storage_backend: StorageBackend;
  database_config?: DatabaseConfig;
  llm_provider: LLMProvider;
  llm_config?: LLMConfig;
  llm_supports_vision?: boolean;
  webhook_config?: WebhookConfig;
  privacy_replacements?: PrivacyReplacementSettings;
}

export interface ConnectionTestResult {
  success: boolean;
  message: string;
}

export interface MigrationResult {
  operations_migrated: number;
  sessions_migrated: number;
  errors: string[];
}

// OperationSummary is used in scope selectors (shared between core and red_team)
export interface OperationSummary {
  id: string;
  name: string;
  session_count: number;
  status: string;
}


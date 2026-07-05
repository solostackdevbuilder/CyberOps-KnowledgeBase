/**
 * Core/Settings API service
 * Uses the centralized API client for consistent error handling
 */
import { apiClient } from '../../services/apiClient';
import type {
  Settings,
  DatabaseConfig,
  LLMConfig,
  ConnectionTestResult,
  MigrationResult,
} from '../types/settings';

// Re-export error utilities for convenience
export { isApiError, getErrorMessage, ApiRequestError } from '../../services/apiClient';

// Settings API methods
export const getSettings = async (): Promise<Settings> => {
  const response = await apiClient.get<Settings>('/settings');
  return response.data;
};

export const updateSettings = async (settings: Settings): Promise<Settings> => {
  const response = await apiClient.put<Settings>('/settings', settings);
  return response.data;
};

export const testDatabaseConnection = async (
  config: DatabaseConfig
): Promise<ConnectionTestResult> => {
  const response = await apiClient.post<ConnectionTestResult>('/settings/test-db', {
    database_config: config,
  });
  return response.data;
};

export const testLLMConnection = async (
  config: LLMConfig
): Promise<ConnectionTestResult> => {
  const response = await apiClient.post<ConnectionTestResult>('/settings/test-llm', {
    llm_config: config,
  });
  return response.data;
};

export const migrateData = async (
  targetBackend: 'mongodb' | 'postgresql',
  config: DatabaseConfig
): Promise<MigrationResult> => {
  const response = await apiClient.post<MigrationResult>('/settings/migrate', {
    target_backend: targetBackend,
    database_config: config,
  });
  return response.data;
};

export const getOllamaModels = async (endpoint: string): Promise<string[]> => {
  const response = await apiClient.get<{ models: string[] }>('/settings/ollama-models', {
    params: { endpoint },
  });
  return response.data.models;
};

export interface AssociationSuggestionsResponse {
  success: boolean;
  seed_name: string;
  suggestions: string[];
  message: string;
  /** Name of the LLM provider the seed was sent to, so the UI can warn the user that the seed left the machine. */
  provider_used?: string | null;
}

export const suggestAssociations = async (
  seedName: string,
  maxItems: number = 20
): Promise<AssociationSuggestionsResponse> => {
  const response = await apiClient.post<AssociationSuggestionsResponse>(
    '/settings/privacy/suggest-associations',
    {
      seed_name: seedName,
      max_items: maxItems,
    }
  );
  return response.data;
};

export const testWebhook = async (service: 'teams' | 'slack' = 'teams'): Promise<ConnectionTestResult> => {
  const response = await apiClient.post<ConnectionTestResult>('/settings/test-webhook', {
    service,
  });
  return response.data;
};

export default apiClient;


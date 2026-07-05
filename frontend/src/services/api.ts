import axios from 'axios';
import type {
  Settings,
  DatabaseConfig,
  LLMConfig,
  ConnectionTestResult,
  MigrationResult,
} from '../types/settings';
import type {
  Session,
  SessionCreate,
  SessionUpdate,
  Operation,
  OperationCreate,
  OperationUpdate,
  ExtractedMetadata,
  QueryRequest,
  QueryResponse,
  ScreenshotExtraction,
  PaginatedOperations,
  PaginatedSessions,
} from '../types';
import type { OperationSummary } from '../types/settings';
import type { InsightsResponse } from '../types/insights';

const api = axios.create({
  baseURL: '/api',
  headers: {
    'Content-Type': 'application/json',
  },
});

// Settings API methods
export const getSettings = async (): Promise<Settings> => {
  const response = await api.get<Settings>('/settings');
  return response.data;
};

export const updateSettings = async (settings: Settings): Promise<Settings> => {
  const response = await api.put<Settings>('/settings', settings);
  return response.data;
};

export const testDatabaseConnection = async (
  config: DatabaseConfig
): Promise<ConnectionTestResult> => {
  const response = await api.post<ConnectionTestResult>('/settings/test-db', {
    database_config: config,
  });
  return response.data;
};

export const testLLMConnection = async (
  config: LLMConfig
): Promise<ConnectionTestResult> => {
  const response = await api.post<ConnectionTestResult>('/settings/test-llm', {
    llm_config: config,
  });
  return response.data;
};

export const migrateData = async (
  targetBackend: 'mongodb' | 'postgresql',
  config: DatabaseConfig
): Promise<MigrationResult> => {
  const response = await api.post<MigrationResult>('/settings/migrate', {
    target_backend: targetBackend,
    database_config: config,
  });
  return response.data;
};

export const getOllamaModels = async (endpoint: string): Promise<string[]> => {
  const response = await api.get<{ models: string[] }>('/settings/ollama-models', {
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
  const response = await api.post<AssociationSuggestionsResponse>(
    '/settings/privacy/suggest-associations',
    {
      seed_name: seedName,
      max_items: maxItems,
    }
  );
  return response.data;
};

// Operation API methods
export const createOperation = async (data: OperationCreate): Promise<Operation> => {
  const response = await api.post<Operation>('/operations', data);
  return response.data;
};

export interface GetOperationsParams {
  page?: number;
  pageSize?: number;
  status?: string;
}

export const getOperationsPaginated = async (
  params: GetOperationsParams = {}
): Promise<PaginatedOperations> => {
  const { page = 1, pageSize = 50, status } = params;
  const response = await api.get<PaginatedOperations>('/operations', {
    params: { page, page_size: pageSize, status },
  });
  return response.data;
};

// Backwards compatible - returns all items from first page
export const getOperations = async (): Promise<Operation[]> => {
  const response = await getOperationsPaginated({ page: 1, pageSize: 100 });
  return response?.items || [];
};

export const getOperation = async (id: string): Promise<Operation> => {
  const response = await api.get<Operation>(`/operations/${id}`);
  return response.data;
};

export const getOperationSessions = async (id: string): Promise<Session[]> => {
  const response = await api.get<Session[]>(`/operations/${id}/sessions`);
  return response.data;
};

export const getOperationsSummary = async (): Promise<OperationSummary[]> => {
  const response = await api.get<OperationSummary[]>('/operations/summary');
  return response.data;
};

export const updateOperation = async (
  id: string,
  data: OperationUpdate
): Promise<Operation> => {
  const response = await api.put<Operation>(`/operations/${id}`, data);
  return response.data;
};

export const deleteOperation = async (id: string): Promise<void> => {
  await api.delete(`/operations/${id}`);
};

// Session API methods
export const createSession = async (data: SessionCreate): Promise<Session> => {
  const response = await api.post<Session>('/sessions', data);
  return response.data;
};

export interface GetSessionsParams {
  page?: number;
  pageSize?: number;
  operationId?: string;
  search?: string;
}

export const getSessionsPaginated = async (
  params: GetSessionsParams = {}
): Promise<PaginatedSessions> => {
  const { page = 1, pageSize = 50, operationId, search } = params;
  const response = await api.get<PaginatedSessions>('/sessions', {
    params: { 
      page, 
      page_size: pageSize, 
      operation_id: operationId,
      search 
    },
  });
  return response.data;
};

// Backwards compatible - returns all items from first page
export const getSessions = async (operationId?: string): Promise<Session[]> => {
  const response = await getSessionsPaginated({ 
    page: 1, 
    pageSize: 100,
    operationId 
  });
  return response?.items || [];
};

export const getSession = async (id: string): Promise<Session> => {
  const response = await api.get<Session>(`/sessions/${id}`);
  return response.data;
};

export const updateSession = async (
  id: string,
  data: SessionUpdate
): Promise<Session> => {
  const response = await api.put<Session>(`/sessions/${id}`, data);
  return response.data;
};

export const deleteSession = async (id: string): Promise<void> => {
  await api.delete(`/sessions/${id}`);
};

// AI Metadata Extraction
export const extractMetadata = async (
  terminalContent: string
): Promise<ExtractedMetadata> => {
  const response = await api.post<ExtractedMetadata>('/sessions/extract', {
    terminal_content: terminalContent,
  });
  return response.data;
};

// Screenshot API methods
export const uploadScreenshot = async (
  sessionId: string,
  file: File,
  description?: string
): Promise<Session> => {
  const formData = new FormData();
  formData.append('file', file);
  if (description) {
    formData.append('description', description);
  }

  const response = await api.post<Session>(
    `/sessions/${sessionId}/screenshots`,
    formData,
    {
      headers: {
        'Content-Type': 'multipart/form-data',
      },
    }
  );
  return response.data;
};

export const getScreenshotUrl = (sessionId: string, filename: string): string => {
  return `/api/sessions/${sessionId}/screenshots/${filename}`;
};

export const retryExtraction = async (
  sessionId: string,
  filename: string
): Promise<ScreenshotExtraction> => {
  const response = await api.post<ScreenshotExtraction>(
    `/sessions/${sessionId}/screenshots/${filename}/extract`
  );
  return response.data;
};

export const reprocessAllScreenshots = async (
  sessionId: string
): Promise<ScreenshotExtraction[]> => {
  const response = await api.post<ScreenshotExtraction[]>(
    `/sessions/${sessionId}/screenshots/reprocess`
  );
  return response.data;
};

// Query API methods
export const query = async (data: QueryRequest): Promise<QueryResponse> => {
  const response = await api.post<QueryResponse>('/query', data);
  return response.data;
};

export const submitQuery = async (
  question: string,
  operationId?: string | null
): Promise<QueryResponse> => {
  const response = await api.post<QueryResponse>('/query', {
    question,
    operation_id: operationId,
  });
  return response.data;
};

// Insights API methods
export const generateInsights = async (
  operationIds: string[],
  forceRefresh: boolean = false
): Promise<InsightsResponse> => {
  const response = await api.post<InsightsResponse>(
    `/insights/generate?force_refresh=${forceRefresh}`,
    {
      operation_ids: operationIds.length === 0 ? 'all' : operationIds,
    }
  );
  return response.data;
};

export const getCachedInsights = async (
  operationIds: string[]
): Promise<InsightsResponse | null> => {
  try {
    const operationIdsParam =
      operationIds.length === 0
        ? 'all'
        : operationIds.join(',');
    const response = await api.get<{
      insights: InsightsResponse;
      cached_at: string;
      expires_at: string;
    }>(`/insights/cache?operation_ids=${operationIdsParam}`);
    return response.data.insights;
  } catch (err: any) {
    // Return null if no cache exists (404 or other error)
    if (err.response?.status === 404 || err.response?.status === 400) {
      return null;
    }
    throw err;
  }
};

// Timeline API methods
export interface TimelineEvent {
  id: string;
  title: string;
  type: 'operation' | 'session';
  start_time: string;
  end_time: string | null;
  operation_id: string | null;
  operation_name: string | null;
  status: string | null;
  metadata: Record<string, any> | null;
}

export interface TimelineResponse {
  events: TimelineEvent[];
  start_date: string;
  end_date: string;
  total_operations: number;
  total_sessions: number;
}

export interface NetworkNode {
  id: string;
  label: string;
  type: 'target' | 'operation' | 'session';
  metadata: Record<string, any> | null;
}

export interface NetworkEdge {
  from_id: string;
  to_id: string;
  label: string | null;
  type: string | null;
}

export interface NetworkDiagramResponse {
  nodes: NetworkNode[];
  edges: NetworkEdge[];
}

export const getOperationsTimeline = async (
  operationId?: string
): Promise<TimelineResponse> => {
  const params = operationId ? { operation_id: operationId } : {};
  const response = await api.get<TimelineResponse>('/timeline/operations', {
    params,
  });
  return response.data;
};

export const getNetworkDiagram = async (
  operationId?: string
): Promise<NetworkDiagramResponse> => {
  const params = operationId ? { operation_id: operationId } : {};
  const response = await api.get<NetworkDiagramResponse>('/timeline/network', {
    params,
  });
  return response.data;
};

export const getKillChainTimeline = async (
  operationId: string
): Promise<any> => {
  const response = await api.get(`/timeline/kill-chain/${operationId}`);
  return response.data;
};

// Command Analysis API methods
export interface CommandAnalysisResponse {
  total_commands: number;
  unique_commands: number;
  command_frequency: Record<string, number>;
  top_commands: Array<{ command: string; count: number }>;
  patterns: Array<{
    sequence: string[];
    frequency: number;
    length: number;
  }>;
  timeline: Array<{
    command: string;
    full_command: string;
    timestamp: string | null;
    session_id: string;
    line_number: number;
  }>;
  sessions_analyzed: number;
}

export const analyzeCommands = async (
  operationId?: string,
  sessionIds?: string
): Promise<CommandAnalysisResponse> => {
  const params: any = {};
  if (operationId) params.operation_id = operationId;
  if (sessionIds) params.session_ids = sessionIds;
  
  const response = await api.get<CommandAnalysisResponse>('/commands/analyze', {
    params,
  });
  return response.data;
};

export const getSessionCommands = async (
  sessionId: string
): Promise<any> => {
  const response = await api.get(`/commands/session/${sessionId}`);
  return response.data;
};

export const getCommandFrequency = async (
  operationId?: string
): Promise<any> => {
  const params = operationId ? { operation_id: operationId } : {};
  const response = await api.get('/commands/frequency', { params });
  return response.data;
};

export const getCommandPatterns = async (
  operationId?: string,
  minLength: number = 2
): Promise<any> => {
  const params: any = { min_length: minLength };
  if (operationId) params.operation_id = operationId;
  const response = await api.get('/commands/patterns', { params });
  return response.data;
};

export default api;


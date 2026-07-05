/**
 * Red Team API service
 * Uses the centralized API client for consistent error handling
 */
import { apiClient } from '../../../services/apiClient';
import type {
  Session,
  SessionCreate,
  SessionUpdate,
  QueryRequest,
  QueryResponse,
  Operation,
  OperationCreate,
  OperationUpdate,
  OperationSummary,
  ExtractedMetadata,
  ScreenshotExtraction,
  FAAItem,
  FAAItemCreate,
  FAAItemUpdate,
  DetectionStrategy,
} from '../types';
import type { InsightsResponse } from '../types/insights';

// Re-export error utilities for convenience
export { isApiError, getErrorMessage, ApiRequestError } from '../../../services/apiClient';

// Operation API methods
export const createOperation = async (data: OperationCreate): Promise<Operation> => {
  const response = await apiClient.post<Operation>('/operations', data);
  return response.data;
};

interface PaginatedResponse<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
}

export const getOperations = async (): Promise<Operation[]> => {
  const response = await apiClient.get<PaginatedResponse<Operation>>('/operations');
  // Handle both paginated and non-paginated responses for backwards compatibility
  if (response.data && Array.isArray(response.data)) {
    return response.data;
  }
  return response.data?.items || [];
};

export const getOperation = async (id: string): Promise<Operation> => {
  const response = await apiClient.get<Operation>(`/operations/${id}`);
  return response.data;
};

export const getOperationSessions = async (id: string): Promise<Session[]> => {
  const response = await apiClient.get<Session[]>(`/operations/${id}/sessions`);
  return response.data;
};

export const updateOperation = async (
  id: string,
  data: OperationUpdate
): Promise<Operation> => {
  const response = await apiClient.put<Operation>(`/operations/${id}`, data);
  return response.data;
};

export const deleteOperation = async (id: string): Promise<void> => {
  await apiClient.delete(`/operations/${id}`);
};

// Session API methods
export const createSession = async (data: SessionCreate): Promise<Session> => {
  const response = await apiClient.post<Session>('/sessions', data);
  return response.data;
};

export const getSessions = async (operationId?: string): Promise<Session[]> => {
  const params = operationId ? `?operation_id=${operationId}` : '';
  const response = await apiClient.get<PaginatedResponse<Session>>(`/sessions${params}`);
  // Handle both paginated and non-paginated responses for backwards compatibility
  if (response.data && Array.isArray(response.data)) {
    return response.data;
  }
  return response.data?.items || [];
};

export const getSession = async (id: string): Promise<Session> => {
  const response = await apiClient.get<Session>(`/sessions/${id}`);
  return response.data;
};

export const updateSession = async (
  id: string,
  data: SessionUpdate
): Promise<Session> => {
  const response = await apiClient.put<Session>(`/sessions/${id}`, data);
  return response.data;
};

export const deleteSession = async (id: string): Promise<void> => {
  await apiClient.delete(`/sessions/${id}`);
};

// AI Metadata Extraction
export const extractMetadata = async (
  terminalContent: string
): Promise<ExtractedMetadata> => {
  const response = await apiClient.post<ExtractedMetadata>('/sessions/extract', {
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

  const response = await apiClient.post<Session>(
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
  const response = await apiClient.post<ScreenshotExtraction>(
    `/sessions/${sessionId}/screenshots/${filename}/extract`
  );
  return response.data;
};

export const reprocessAllScreenshots = async (
  sessionId: string
): Promise<ScreenshotExtraction[]> => {
  const response = await apiClient.post<ScreenshotExtraction[]>(
    `/sessions/${sessionId}/screenshots/reprocess`
  );
  return response.data;
};

// Query API methods
export const query = async (data: QueryRequest): Promise<QueryResponse> => {
  const response = await apiClient.post<QueryResponse>('/query', data);
  return response.data;
};

export const submitQuery = async (
  question: string,
  operationId?: string | null
): Promise<QueryResponse> => {
  const response = await apiClient.post<QueryResponse>('/query', {
    question,
    operation_id: operationId,
  });
  return response.data;
};

export interface QueryHistoryItem {
  id: string;
  question: string;
  operation_id: string | null;
  created_at: string;
}

export const getQueryHistory = async (limit: number = 10): Promise<QueryHistoryItem[]> => {
  const response = await apiClient.get<QueryHistoryItem[]>(`/query/history?limit=${limit}`);
  return response.data;
};

export const getCachedQuery = async (cacheId: string): Promise<QueryResponse> => {
  const response = await apiClient.get<QueryResponse>(`/query/cache/${cacheId}`);
  return response.data;
};

export const deleteCachedQuery = async (cacheId: string): Promise<void> => {
  await apiClient.delete(`/query/cache/${cacheId}`);
};

export const getOperationsSummary = async (): Promise<OperationSummary[]> => {
  const response = await apiClient.get<OperationSummary[]>('/operations/summary');
  return response.data;
};

// Insights API methods
export const generateInsights = async (
  operationIds: string[],
  forceRefresh: boolean = false
): Promise<InsightsResponse> => {
  const response = await apiClient.post<InsightsResponse>(
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
    const response = await apiClient.get<{
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

// FAA (Findings and Actions) API methods
import type { FAAAnalysisResponse } from '../types';

export const analyzeSessionFAA = async (sessionId: string): Promise<FAAAnalysisResponse> => {
  const response = await apiClient.post<FAAAnalysisResponse>(`/sessions/${sessionId}/faa/analyze`);
  return response.data;
};

export const getFAAItems = async (
  sessionId: string,
  filters?: {
    classification?: 'action' | 'finding';
    mitre_technique?: string;
    severity?: 'critical' | 'high' | 'medium' | 'low';
  }
): Promise<FAAItem[]> => {
  const params = new URLSearchParams();
  if (filters?.classification) params.append('classification', filters.classification);
  if (filters?.mitre_technique) params.append('mitre_technique', filters.mitre_technique);
  if (filters?.severity) params.append('severity', filters.severity);
  
  const response = await apiClient.get<FAAItem[]>(
    `/sessions/${sessionId}/faa${params.toString() ? `?${params.toString()}` : ''}`
  );
  return response.data;
};

export const getFAAItem = async (faaId: string, sessionId: string): Promise<FAAItem> => {
  const response = await apiClient.get<FAAItem>(`/faa/${faaId}?session_id=${sessionId}`);
  return response.data;
};

export const updateFAAItem = async (
  faaId: string,
  sessionId: string,
  updates: FAAItemUpdate
): Promise<FAAItem> => {
  const response = await apiClient.put<FAAItem>(`/faa/${faaId}?session_id=${sessionId}`, updates);
  return response.data;
};

export const deleteFAAItem = async (faaId: string, sessionId: string): Promise<void> => {
  await apiClient.delete(`/faa/${faaId}?session_id=${sessionId}`);
};

export const createFAAItem = async (item: FAAItemCreate): Promise<FAAItem> => {
  const response = await apiClient.post<FAAItem>('/faa', item);
  return response.data;
};

// FAA Export API methods
export type FAAExportClassification = 'finding' | 'action';

export const exportOperationFAA = async (
  operationId: string,
  options?: { classification?: FAAExportClassification }
): Promise<Blob> => {
  const response = await apiClient.get(`/operations/${operationId}/faa/export`, {
    params: options?.classification ? { classification: options.classification } : undefined,
    responseType: 'blob',
  });
  return response.data;
};

export const exportSessionFAA = async (
  sessionId: string,
  options?: { classification?: FAAExportClassification }
): Promise<Blob> => {
  const response = await apiClient.get(`/sessions/${sessionId}/faa/export`, {
    params: options?.classification ? { classification: options.classification } : undefined,
    responseType: 'blob',
  });
  return response.data;
};

// Detection Strategy API methods

export const getDetectionStrategies = async (params?: {
  technique_id?: string;
  platform?: string;
  search?: string;
}): Promise<DetectionStrategy[]> => {
  const queryParams = new URLSearchParams();
  if (params?.technique_id) queryParams.append('technique_id', params.technique_id);
  if (params?.platform) queryParams.append('platform', params.platform);
  if (params?.search) queryParams.append('search', params.search);
  
  const response = await apiClient.get<DetectionStrategy[]>(
    `/detection-strategies${queryParams.toString() ? `?${queryParams.toString()}` : ''}`
  );
  return response.data;
};

export const getDetectionStrategy = async (strategyId: string): Promise<DetectionStrategy> => {
  const response = await apiClient.get<DetectionStrategy>(`/detection-strategies/${strategyId}`);
  return response.data;
};

export const getStrategiesForTechnique = async (techniqueId: string): Promise<DetectionStrategy[]> => {
  const response = await apiClient.get<DetectionStrategy[]>(
    `/detection-strategies/technique/${techniqueId}`
  );
  return response.data;
};

export const getCoverageGaps = async (techniqueIds: string[]): Promise<string[]> => {
  const response = await apiClient.post<string[]>('/detection-strategies/coverage-gaps', techniqueIds);
  return response.data;
};

export interface DefensiveGuidance {
  technique_id: string;
  title: string;
  what_to_check: string[];
  monitoring: string[];
  prevention: string[];
  mitre_url: string;
}

export interface OperationCoverage {
  operation_id: string;
  total_techniques: number;
  techniques_with_strategies: number;
  techniques_without_strategies: number;
  coverage_percentage: number;
  techniques_without_strategies_list: string[];
  detection_strategies: DetectionStrategy[];
  defensive_guidance?: DefensiveGuidance[];
  recommendations: string[];
}

export const getOperationCoverage = async (operationId: string): Promise<OperationCoverage> => {
  const response = await apiClient.post<OperationCoverage>(
    `/detection-strategies/operation/${operationId}/coverage`
  );
  return response.data;
};

export default apiClient;


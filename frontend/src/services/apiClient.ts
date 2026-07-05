/**
 * Centralized API client for the RedTeam Knowledge Base application.
 * 
 * Provides:
 * - Single shared axios instance with consistent configuration
 * - Request/response interceptors for error handling
 * - Type-safe API methods organized by domain
 * - Consistent error handling across all modules
 */
import axios, { AxiosError, AxiosInstance, AxiosResponse } from 'axios';

// ============================================================================
// Types
// ============================================================================

/**
 * Standard API error response structure
 */
export interface ApiError {
  error: string;
  message: string;
  detail?: string;
  field?: string;
  resource_type?: string;
  resource_id?: string;
}

/**
 * Wrapper for API responses with error handling
 */
export interface ApiResponse<T> {
  data: T;
  success: boolean;
  error?: ApiError;
}

/**
 * Configuration options for the API client
 */
export interface ApiClientConfig {
  baseURL?: string;
  timeout?: number;
  onError?: (error: ApiError) => void;
  onUnauthorized?: () => void;
}

// ============================================================================
// Error Handling
// ============================================================================

/**
 * Custom error class for API errors with typed error data
 */
export class ApiRequestError extends Error {
  public readonly statusCode: number;
  public readonly errorType: string;
  public readonly detail?: string;
  public readonly field?: string;

  constructor(
    message: string,
    statusCode: number,
    errorType: string = 'unknown_error',
    detail?: string,
    field?: string
  ) {
    super(message);
    this.name = 'ApiRequestError';
    this.statusCode = statusCode;
    this.errorType = errorType;
    this.detail = detail;
    this.field = field;
  }

  /**
   * Check if this is a specific error type
   */
  is(errorType: string): boolean {
    return this.errorType === errorType;
  }

  /**
   * Check if this is a client error (4xx)
   */
  isClientError(): boolean {
    return this.statusCode >= 400 && this.statusCode < 500;
  }

  /**
   * Check if this is a server error (5xx)
   */
  isServerError(): boolean {
    return this.statusCode >= 500;
  }

  /**
   * Check if this is a not found error
   */
  isNotFound(): boolean {
    return this.statusCode === 404;
  }

  /**
   * Check if this is a validation error
   */
  isValidationError(): boolean {
    return this.statusCode === 422;
  }

  /**
   * Check if this is a rate limit error
   */
  isRateLimited(): boolean {
    return this.statusCode === 429;
  }

  /**
   * Check if this is a service unavailable error
   */
  isServiceUnavailable(): boolean {
    return this.statusCode === 503;
  }
}

/**
 * Parse error response into ApiRequestError
 */
function parseErrorResponse(error: AxiosError<ApiError>): ApiRequestError {
  const statusCode = error.response?.status || 500;
  const data = error.response?.data;

  if (data && typeof data === 'object') {
    return new ApiRequestError(
      data.message || error.message || 'An unknown error occurred',
      statusCode,
      data.error || 'unknown_error',
      data.detail,
      data.field
    );
  }

  // Network error or other non-response error
  if (error.code === 'ECONNABORTED') {
    return new ApiRequestError(
      'Request timed out. Please try again.',
      408,
      'timeout'
    );
  }

  if (!error.response) {
    return new ApiRequestError(
      'Unable to connect to server. Please check your connection.',
      0,
      'network_error'
    );
  }

  return new ApiRequestError(
    error.message || 'An unknown error occurred',
    statusCode,
    'unknown_error'
  );
}

// ============================================================================
// API Client Factory
// ============================================================================

/**
 * Create a configured axios instance with interceptors
 */
export function createApiClient(config: ApiClientConfig = {}): AxiosInstance {
  const client = axios.create({
    baseURL: config.baseURL || '/api',
    timeout: config.timeout || 60000, // 60 second timeout
    headers: {
      'Content-Type': 'application/json',
    },
  });

  // Request interceptor
  client.interceptors.request.use(
    (requestConfig) => {
      // Log requests in development
      if (import.meta.env.DEV) {
        console.debug(`[API] ${requestConfig.method?.toUpperCase()} ${requestConfig.url}`);
      }
      return requestConfig;
    },
    (error) => {
      return Promise.reject(error);
    }
  );

  // Response interceptor
  client.interceptors.response.use(
    (response: AxiosResponse) => {
      return response;
    },
    (error: AxiosError<ApiError>) => {
      const apiError = parseErrorResponse(error);

      // Log errors in development
      if (import.meta.env.DEV) {
        console.error(`[API Error] ${apiError.statusCode}: ${apiError.message}`, {
          errorType: apiError.errorType,
          detail: apiError.detail,
        });
      }

      // Call custom error handler if provided
      if (config.onError) {
        config.onError({
          error: apiError.errorType,
          message: apiError.message,
          detail: apiError.detail,
          field: apiError.field,
        });
      }

      // Handle unauthorized (could trigger logout)
      if (apiError.statusCode === 401 && config.onUnauthorized) {
        config.onUnauthorized();
      }

      return Promise.reject(apiError);
    }
  );

  return client;
}

// ============================================================================
// Default Client Instance
// ============================================================================

/**
 * Default API client instance for the application
 */
export const apiClient = createApiClient();

// ============================================================================
// Utility Functions
// ============================================================================

/**
 * Helper to handle FormData requests (removes Content-Type to let browser set it)
 */
export async function postFormData<T>(
  client: AxiosInstance,
  url: string,
  formData: FormData
): Promise<T> {
  const response = await client.post<T>(url, formData, {
    headers: {
      'Content-Type': 'multipart/form-data',
    },
  });
  return response.data;
}

/**
 * Helper to download a file as blob
 */
export async function downloadBlob(
  client: AxiosInstance,
  url: string,
  params?: Record<string, string>
): Promise<Blob> {
  const response = await client.get(url, {
    responseType: 'blob',
    params,
  });
  return response.data;
}

/**
 * Helper to trigger file download in browser
 */
export function downloadFile(blob: Blob, filename: string): void {
  const url = window.URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.setAttribute('download', filename);
  document.body.appendChild(link);
  link.click();
  link.remove();
  window.URL.revokeObjectURL(url);
}

// ============================================================================
// Error Type Guards
// ============================================================================

/**
 * Check if an error is an ApiRequestError
 */
export function isApiError(error: unknown): error is ApiRequestError {
  return error instanceof ApiRequestError;
}

/**
 * Get user-friendly error message from any error
 */
export function getErrorMessage(error: unknown): string {
  if (isApiError(error)) {
    return error.message;
  }
  if (error instanceof Error) {
    return error.message;
  }
  return 'An unexpected error occurred';
}

/**
 * Get error details for logging/debugging
 */
export function getErrorDetails(error: unknown): Record<string, unknown> {
  if (isApiError(error)) {
    return {
      message: error.message,
      statusCode: error.statusCode,
      errorType: error.errorType,
      detail: error.detail,
      field: error.field,
    };
  }
  if (error instanceof Error) {
    return {
      message: error.message,
      name: error.name,
      stack: error.stack,
    };
  }
  return { error: String(error) };
}

export default apiClient;


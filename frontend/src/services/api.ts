import type {
  ApiResponse,
  QueryRequest,
  ClarifyRequest,
  ConfirmRequest,
  TableSchema,
  HistoryResponse,
} from '@/types';

// Read API base URL from Vite environment, falling back to empty string (which defaults to relative /api via Vite proxy)
const getApiBase = (): string => {
  const envBase = import.meta.env.VITE_API_BASE_URL || '';
  if (!envBase) return '/api';
  const cleanBase = envBase.replace(/\/$/, '');
  return cleanBase.endsWith('/api') ? cleanBase : `${cleanBase}/api`;
};

export class ApiError extends Error {
  status: number;
  detail: string;
  constructor(status: number, detail: string) {
    super(detail);
    this.status = status;
    this.detail = detail;
    this.name = 'ApiError';
  }
}

async function request<T>(url: string, options: RequestInit = {}): Promise<T> {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 30000);
  const baseUrl = getApiBase();

  try {
    const response = await fetch(`${baseUrl}${url}`, {
      ...options,
      signal: controller.signal,
      headers: {
        'Content-Type': 'application/json',
        ...options.headers,
      },
    });
    clearTimeout(timeout);

    if (!response.ok) {
      const body = await response.json().catch(() => ({}));
      const message = body.message || `Request failed with status ${response.status}`;
      throw new ApiError(response.status, message);
    }
    return await response.json();
  } catch (error) {
    clearTimeout(timeout);
    if (error instanceof ApiError) throw error;
    if (error instanceof DOMException && error.name === 'AbortError') {
      throw new ApiError(0, 'Request timed out after 30 seconds.');
    }
    throw new ApiError(0, 'Unable to connect to the backend server. Please check your connection.');
  }
}

/**
 * Execute natural language SQL text query
 */
export async function queryDatabase(payload: QueryRequest): Promise<ApiResponse> {
  return request<ApiResponse>('/query', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

/**
 * Execute natural language voice query via audio recording upload
 */
export async function voiceQuery(audioBlob: Blob, conversationId?: string, language?: string): Promise<ApiResponse> {
  const formData = new FormData();
  const mimeType = audioBlob.type.toLowerCase();
  const extension = mimeType.includes('webm')
    ? 'webm'
    : mimeType.includes('ogg')
    ? 'ogg'
    : mimeType.includes('mp3')
    ? 'mp3'
    : 'wav';

  formData.append('audio', audioBlob, `speech.${extension}`);
  if (conversationId) {
    formData.append('conversation_id', conversationId);
  }
  if (language) {
    formData.append('language', language);
  }

  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 45000);
  const baseUrl = getApiBase();

  try {
    const response = await fetch(`${baseUrl}/voice/query`, {
      method: 'POST',
      body: formData,
      signal: controller.signal,
    });
    clearTimeout(timeout);

    if (!response.ok) {
      const body = await response.json().catch(() => ({}));
      throw new ApiError(response.status, body.message || 'Voice transcription and processing failed.');
    }
    return await response.json();
  } catch (error) {
    clearTimeout(timeout);
    if (error instanceof ApiError) throw error;
    if (error instanceof DOMException && error.name === 'AbortError') {
      throw new ApiError(0, 'Voice processing timed out.');
    }
    throw new ApiError(0, 'Voice processing failed. Please try typing your query.');
  }
}

/**
 * Respond to an ambiguous query clarification request
 */
export async function clarifyQuery(payload: ClarifyRequest): Promise<ApiResponse> {
  return request<ApiResponse>('/query/clarify', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

/**
 * Confirm execution of a database-modifying query (INSERT / UPDATE / DELETE)
 */
export async function confirmQuery(payload: ConfirmRequest): Promise<ApiResponse> {
  return request<ApiResponse>('/query/confirm', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

/**
 * Fetch query status/details by request ID
 */
export async function getQuery(requestId: string): Promise<ApiResponse> {
  return request<ApiResponse>(`/query/${encodeURIComponent(requestId)}`, {
    method: 'GET',
  });
}

/**
 * Fetch database schema information
 */
export async function getSchema(): Promise<{ tables: Record<string, TableSchema> }> {
  return request<{ tables: Record<string, TableSchema> }>('/schema', {
    method: 'GET',
  });
}

/**
 * Fetch conversation query history
 */
export async function getHistory(conversationId: string): Promise<HistoryResponse> {
  return request<HistoryResponse>(`/history?conversation_id=${encodeURIComponent(conversationId)}`, {
    method: 'GET',
  });
}

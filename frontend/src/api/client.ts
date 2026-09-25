import type { ApiResponse, QueryRequest, ClarifyRequest, ConfirmRequest } from '@/types';

const API_BASE = '/api';

class ApiError extends Error {
  status: number;
  detail: string;
  constructor(status: number, detail: string) { super(detail); this.status = status; this.detail = detail; this.name = 'ApiError'; }
}

async function request<T>(url: string, options: RequestInit = {}): Promise<T> {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 30000);
  try {
    const response = await fetch(`${API_BASE}${url}`, { ...options, signal: controller.signal, headers: { 'Content-Type': 'application/json', ...options.headers } });
    clearTimeout(timeout);
    if (!response.ok) { const body = await response.json().catch(() => ({})); throw new ApiError(response.status, body.message || `Request failed: ${response.status}`); }
    return await response.json();
  } catch (error) {
    clearTimeout(timeout);
    if (error instanceof ApiError) throw error;
    if (error instanceof DOMException && error.name === 'AbortError') throw new ApiError(0, 'Request timed out.');
    throw new ApiError(0, 'Network error. Please try again.');
  }
}

export async function submitQuery(payload: QueryRequest): Promise<ApiResponse> { return request<ApiResponse>('/query', { method: 'POST', body: JSON.stringify(payload) }); }
export async function submitVoiceQuery(audioBlob: Blob): Promise<ApiResponse> { const fd = new FormData(); fd.append('audio', audioBlob, 'audio.wav'); try { const resp = await fetch(`${API_BASE}/voice/query`, { method: 'POST', body: fd }); if (!resp.ok) { const body = await resp.json().catch(() => ({})); throw new ApiError(resp.status, body.message || 'Voice transcription failed.'); } return await resp.json(); } catch (err) { if (err instanceof ApiError) throw err; throw new ApiError(0, 'Voice processing failed.'); } }
export async function submitClarification(payload: ClarifyRequest): Promise<ApiResponse> { return request<ApiResponse>('/query/clarify', { method: 'POST', body: JSON.stringify(payload) }); }
export async function confirmMutation(payload: ConfirmRequest): Promise<ApiResponse> { return request<ApiResponse>('/query/confirm', { method: 'POST', body: JSON.stringify(payload) }); }
export async function fetchSchema(): Promise<{ tables: Record<string, any> }> { return request('/schema'); }
export async function fetchHistory(conversationId: string): Promise<{ conversation_id: string; items: any[] }> { return request(`/history?conversation_id=${conversationId}`); }

export { ApiError };

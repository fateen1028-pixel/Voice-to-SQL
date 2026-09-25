import { useState, useCallback, useRef } from 'react';
import { submitQuery, submitVoiceQuery, submitClarification, confirmMutation, fetchSchema, fetchHistory } from '@/api/client';
import type { ApiResponse, TableSchema } from '@/types';

export function useVoice() {
  const [isRecording, setIsRecording] = useState(false);
  const [isProcessing, setIsProcessing] = useState(false);
  const [voiceError, setVoiceError] = useState<string | null>(null);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const audioChunksRef = useRef<Blob[]>([]);
  const streamRef = useRef<MediaStream | null>(null);

  const startRecording = useCallback(async (): Promise<ApiResponse | null> => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      streamRef.current = stream;
      audioChunksRef.current = [];
      const resultPromise = new Promise<ApiResponse | null>(async (resolve) => {
        const mr = new MediaRecorder(stream);
        mr.ondataavailable = (e) => { if (e.data.size > 0) audioChunksRef.current.push(e.data); };
        mr.onstop = async () => {
          setIsProcessing(true);
          const blob = new Blob(audioChunksRef.current, { type: 'audio/wav' });
          try { const r = await submitVoiceQuery(blob); resolve(r); } catch (err) { const msg = err instanceof Error ? err.message : 'Voice failed.'; setVoiceError(msg); resolve(null); } finally { setIsProcessing(false); stream.getTracks().forEach(t => t.stop()); streamRef.current = null; }
        };
        mr.start();
        mediaRecorderRef.current = mr;
        setIsRecording(true);
        setVoiceError(null);
      });
      return await resultPromise;
    } catch (err) {
      if (err instanceof DOMException && err.name === 'NotAllowedError') setVoiceError('Microphone permission denied. You can type instead.');
      else if (err instanceof DOMException && err.name === 'NotFoundError') setVoiceError('No microphone found. Please type instead.');
      else setVoiceError('Could not access microphone. Please use text input.');
      return null;
    }
  }, []);

  const stopRecording = useCallback(() => { if (mediaRecorderRef.current && isRecording) { mediaRecorderRef.current.stop(); setIsRecording(false); } }, [isRecording]);
  const cancelRecording = useCallback(() => { if (mediaRecorderRef.current) mediaRecorderRef.current.stop(); if (streamRef.current) { streamRef.current.getTracks().forEach(t => t.stop()); streamRef.current = null; } setIsRecording(false); setIsProcessing(false); }, []);
  const clearError = useCallback(() => setVoiceError(null), []);

  return { isRecording, isProcessing, voiceError, startRecording, stopRecording, cancelRecording, clearError };
}

export function useQuery() {
  const [result, setResult] = useState<ApiResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const execute = useCallback(async (payload: { message: string; conversation_id: string }): Promise<ApiResponse | null> => {
    setLoading(true); setError(null);
    try { const response = await submitQuery(payload); setResult(response); return response; } catch (err) { const msg = err instanceof Error ? err.message : 'An error occurred.'; setError(msg); return null; } finally { setLoading(false); }
  }, []);

  const clearResult = useCallback(() => { setResult(null); setError(null); }, []);
  return { result, loading, error, execute, clearResult };
}

export function useClarification() {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const respond = useCallback(async (requestId: string, selection: string): Promise<ApiResponse | null> => {
    setLoading(true); setError(null);
    try { return await submitClarification({ request_id: requestId, selection }); } catch (err) { const msg = err instanceof Error ? err.message : 'Clarification failed.'; setError(msg); return null; } finally { setLoading(false); }
  }, []);
  return { respond, loading, error };
}

export function useConfirmation() {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const confirm = useCallback(async (token: string): Promise<ApiResponse | null> => {
    setLoading(true); setError(null);
    try { return await confirmMutation({ confirmation_token: token }); } catch (err) { const msg = err instanceof Error ? err.message : 'Confirmation failed.'; setError(msg); return null; } finally { setLoading(false); }
  }, []);
  return { confirm, loading, error };
}

export function useSchema() {
  const [tables, setTables] = useState<Record<string, TableSchema>>({});
  const [loading, setLoading] = useState(false);
  const load = useCallback(async () => { setLoading(true); try { const data = await fetchSchema(); setTables(data.tables); } finally { setLoading(false); } }, []);
  return { tables, loading, load };
}

export function useHistory() {
  const [items, setItems] = useState<any[]>([]);
  const [loading, setLoading] = useState(false);
  const load = useCallback(async (conversationId: string) => { setLoading(true); try { const data = await fetchHistory(conversationId); setItems(data.items); } finally { setLoading(false); } }, []);
  return { items, loading, load };
}

import type { ApiResponse } from '@/types';
import { QueryResult } from './QueryResult';

interface Props {
  message: string;
  response: ApiResponse;
  timestamp: string;
  onConfirm: (token: string) => void;
  onClarify: (requestId: string, selection: string) => void;
  onRetry: (message: string) => void;
}

export function MessageBubble({ message, response, timestamp, onConfirm, onClarify, onRetry }: Props) {
  const time = new Date(timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  return (
    <div className="flex gap-3 py-3 md:py-4 animate-slide-up">
      <div className="flex-shrink-0 w-8 h-8 rounded-lg bg-surface-100 flex items-center justify-center mt-0.5">
        <svg className="w-4 h-4 text-brand-600" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" /></svg>
      </div>
      <div className="flex-1 min-w-0">
        <div className="mb-1"><span className="text-xs font-semibold text-surface-600">You</span><span className="text-xs text-surface-400 ml-2">{time}</span></div>
        <p className="text-sm text-surface-800 mb-3 leading-relaxed">{message}</p>
        <QueryResult response={response} onConfirm={onConfirm} onClarify={onClarify} onRetry={() => onRetry(message)} />
      </div>
    </div>
  );
}

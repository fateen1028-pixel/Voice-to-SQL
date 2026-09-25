import type { ReactNode } from 'react';

interface Props { children: ReactNode; }

export function Spinner({ size = 'md' }: { size?: 'sm' | 'md' | 'lg' } = {}) {
  const sizes = { sm: 'w-3 h-3', md: 'w-5 w-5', lg: 'w-7 h-7' };
  return <div className={`${sizes[size]} animate-spin rounded-full border-2 border-surface-300 border-t-brand-600`} role="status" aria-label="Loading"><span className="sr-only">Loading...</span></div>;
}

export function EmptyState({ message }: { message: string }) {
  return (
    <div className="flex flex-col items-center justify-center py-12 md:py-20 px-6 text-center animate-fade-in">
      <div className="w-20 h-20 rounded-2xl bg-brand-50 flex items-center justify-center mb-5">
        <svg className="w-10 h-10 text-brand-500" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" /></svg>
      </div>
      <p className="text-surface-500 text-lg font-light max-w-md leading-relaxed">{message}</p>
    </div>
  );
}

export function ErrorMessage({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div className="flex items-start gap-3 px-4 py-3 bg-red-50 border border-red-200 rounded-lg animate-slide-up" role="alert">
      <div className="w-5 h-5 flex-shrink-0 mt-0.5"><svg className="w-5 h-5 text-red-500" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-2.5L13.732 4c-.77-.833-1.964-.833-2.732 0L4.082 16.5c-.77.833.192 2.5 1.732 2.5z" /></svg></div>
      <p className="text-red-700 text-sm flex-1">{message}</p>
      {onRetry && <button onClick={onRetry} className="flex-shrink-0 text-red-600 text-sm font-medium hover:underline">Retry</button>}
    </div>
  );
}

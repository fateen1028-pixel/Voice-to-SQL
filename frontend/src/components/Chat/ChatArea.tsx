import { useCallback, useEffect, useRef, useState } from 'react';
import { confirmMutation, fetchHistory, fetchSchema, submitClarification, submitQuery } from '@/api/client';
import { InputArea } from '@/components/Input/InputArea';
import { QueryResult } from '@/components/Chat/QueryResult';
import { HistoryPanel } from '@/components/History/HistoryPanel';
import { SchemaPanel } from '@/components/Schema/SchemaPanel';
import type { ApiResponse, HistoryItem } from '@/types';

type Turn = { id: string; message: string; response: ApiResponse };

function icon(path: string) {
  return <svg aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8"><path strokeLinecap="round" strokeLinejoin="round" d={path} /></svg>;
}

function VoiceQlMark({ className = '' }: { className?: string }) {
  return <svg className={className} aria-hidden="true" viewBox="0 0 32 32" fill="none">
    <path d="M6 10.5v11M11 7v18M16 10.5v11" stroke="currentColor" strokeWidth="2.8" strokeLinecap="round" />
    <path d="M19 9.5v8.25a5.5 5.5 0 1 0 11 0V14" stroke="currentColor" strokeWidth="2.8" strokeLinecap="round" />
    <path d="M24.5 25.5v3M21.5 28.5h6" stroke="currentColor" strokeWidth="2.3" strokeLinecap="round" />
  </svg>;
}

export function ChatArea() {
  const [conversationId] = useState(() => crypto.randomUUID?.() ?? Math.random().toString(36).slice(2));
  const [turns, setTurns] = useState<Turn[]>([]);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [schemaOpen, setSchemaOpen] = useState(false);
  const [historyOpen, setHistoryOpen] = useState(false);
  const [history, setHistory] = useState<HistoryItem[]>([]);
  const [historyLoading, setHistoryLoading] = useState(false);
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => endRef.current?.scrollIntoView({ behavior: 'smooth' }), [turns, busy]);

  const append = useCallback((message: string, response: ApiResponse) => {
    setTurns((current) => [...current, { id: response.request_id ?? crypto.randomUUID?.() ?? String(Date.now()), message, response }]);
  }, []);

  const ask = useCallback(async (message: string) => {
    setNotice(null);
    setBusy(true);
    try {
      append(message, await submitQuery({ message, conversation_id: conversationId }));
    } catch (error) {
      setNotice(error instanceof Error ? error.message : 'Your request could not be sent.');
    } finally {
      setBusy(false);
    }
  }, [append, conversationId]);

  const handleClarify = useCallback(async (requestId: string, option: string) => {
    setBusy(true); setNotice(null);
    try { append(option, await submitClarification({ request_id: requestId, selection: option })); }
    catch (error) { setNotice(error instanceof Error ? error.message : 'The clarification could not be sent.'); }
    finally { setBusy(false); }
  }, [append]);

  const handleConfirm = useCallback(async (token: string) => {
    setBusy(true); setNotice(null);
    try { append('Confirm this change', await confirmMutation({ confirmation_token: token })); }
    catch (error) { setNotice(error instanceof Error ? error.message : 'The change could not be confirmed.'); }
    finally { setBusy(false); }
  }, [append]);

  const toggleHistory = useCallback(async () => {
    if (historyOpen) {
      setHistoryOpen(false);
      return;
    }

    setHistoryOpen(true);
    setHistoryLoading(true);
    setNotice(null);
    try {
      setHistory((await fetchHistory(conversationId)).items);
    } catch {
      setNotice('Conversation history is unavailable right now.');
    } finally {
      setHistoryLoading(false);
    }
  }, [conversationId, historyOpen]);

  return (
    <div className="app-shell">
      <header className="topbar">
        <div className="brand"><span className="brand-mark"><VoiceQlMark /></span><span>VoiceQL</span></div>
        <div className="topbar-actions">
          <button className="icon-button" onClick={toggleHistory} aria-label="Show conversation history" title="Conversation history">{icon('M12 8v4l2.75 2.75M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0')}</button>
          <button className="icon-button" onClick={() => setSchemaOpen(true)} aria-label="Show database schema" title="Database schema">{icon('M4 7c0 2.2 3.6 4 8 4s8-1.8 8-4-3.6-4-8-4-8 1.8-8 4Zm0 0v10c0 2.2 3.6 4 8 4s8-1.8 8-4V7')}</button>
        </div>
      </header>

      <main className={turns.length ? 'workspace workspace-active' : 'workspace'} aria-live="polite">
        {turns.length === 0 ? (
          <section className="welcome">
            <span className="welcome-mark"><VoiceQlMark /></span>
            <h1>What do you need to know?</h1>
            <p>Ask about your data in everyday language, or say it out loud.</p>
          </section>
        ) : (
          <section className="turn-list" aria-label="Query conversation">
            {turns.map((turn) => <article className="turn" key={turn.id}>
              <div className="user-question">{turn.message}</div>
              <QueryResult response={turn.response} onClarify={handleClarify} onConfirm={handleConfirm} onRetry={() => ask(turn.message)} />
            </article>)}
            {busy && <div className="processing"><span className="processing-dot" />Working with your request</div>}
          </section>
        )}
        {notice && <div className="notice" role="alert"><span>{notice}</span><button onClick={() => setNotice(null)} aria-label="Dismiss message">{icon('M6 6l12 12M18 6 6 18')}</button></div>}
        {historyOpen && <section className="history" aria-label="Conversation history"><div className="history-heading">This conversation</div>{historyLoading ? <p>Loading conversation history...</p> : <HistoryPanel items={history} onSelect={ask} />}</section>}
        <div ref={endRef} />
      </main>

      <footer className="composer-wrap"><InputArea disabled={busy} conversationId={conversationId} onSubmit={ask} onVoiceResult={(message, response) => append(message, response)} onError={setNotice} /></footer>
      <SchemaPanel isOpen={schemaOpen} onClose={() => setSchemaOpen(false)} loadSchema={fetchSchema} />
    </div>
  );
}

import type { ApiResponse } from '@/types';

interface Props { response: ApiResponse; onConfirm: (token: string) => void; onClarify: (requestId: string, selection: string) => void; onRetry: () => void; }

function SqlBlock({ sql }: { sql: string }) { return <details className="sql-details"><summary>Generated SQL</summary><pre><code>{sql}</code></pre></details>; }

export function QueryResult({ response, onClarify, onConfirm, onRetry }: Props) {
  if (response.status === 'SUCCESS') return <div className="result-card success-result">
    {response.explanation && <p className="result-summary">{response.explanation}</p>}
    {response.row_count !== null && response.row_count !== undefined && !response.rows && <p className="result-summary">{response.message || `${response.row_count} record(s) affected.`}</p>}
    {response.columns && response.rows && <div className="table-scroll"><table><thead><tr>{response.columns.map((column) => <th key={column}>{column}</th>)}</tr></thead><tbody>{response.rows.map((row, rowIndex) => <tr key={rowIndex}>{response.columns!.map((column) => <td key={column}>{format(row[column])}</td>)}</tr>)}</tbody></table></div>}
    {response.rows?.length === 0 && <p className="result-summary">No matching records were found.</p>}
    {response.sql && <SqlBlock sql={response.sql} />}
  </div>;

  if (response.status === 'CLARIFICATION_REQUIRED') return <div className="result-card"><p className="result-summary">{response.question}</p><div className="option-list">{response.options?.map((option) => <button key={option} disabled={!response.request_id} onClick={() => response.request_id && onClarify(response.request_id, option)}>{option}</button>)}</div></div>;

  if (response.status === 'CONFIRMATION_REQUIRED') return <div className="result-card caution-result"><p className="eyebrow">Confirmation required</p><p className="result-summary">{response.message}</p>{response.estimated_affected_rows !== null && response.estimated_affected_rows !== undefined && <p className="muted">Estimated affected records: {response.estimated_affected_rows}</p>}{response.sql && <SqlBlock sql={response.sql} />}<button className="confirm-button" disabled={!response.confirmation_token} onClick={() => response.confirmation_token && onConfirm(response.confirmation_token)}>Confirm change</button></div>;

  const retryable = ['FAILED', 'VALIDATION_FAILED', 'EXECUTION_FAILED', 'RETRY_REQUIRED', 'INVALID_CONFIRMATION'].includes(response.status);
  return <div className={`result-card ${response.status === 'SECURITY_VIOLATION' ? 'caution-result' : 'error-result'}`}><p className="result-summary">{response.message || 'The request could not be completed.'}</p>{response.validation?.issues?.length ? <ul className="issue-list">{response.validation.issues.map((issue) => <li key={issue}>{issue}</li>)}</ul> : null}{response.sql && <SqlBlock sql={response.sql} />}{retryable && <button className="text-button" onClick={onRetry}>Try again</button>}</div>;
}

function format(value: unknown) { if (value === null || value === undefined) return '—'; if (typeof value === 'object') return JSON.stringify(value); return String(value); }

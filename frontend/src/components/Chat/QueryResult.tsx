import { useState } from 'react';
import type { ApiResponse, VisualizationConfig } from '@/types';

interface Props {
  response: ApiResponse;
  onConfirm: (token: string) => void;
  onClarify: (requestId: string, selection: string) => void;
  onRetry: () => void;
}

function SqlBlock({ sql }: { sql: string }) {
  return (
    <details className="sql-details">
      <summary>Generated SQL</summary>
      <pre>
        <code>{sql}</code>
      </pre>
    </details>
  );
}

function formatValue(value: unknown): string {
  if (value === null || value === undefined) return '—';
  if (typeof value === 'object') return JSON.stringify(value);
  return String(value);
}

function VisualizationView({ config, rows }: { config: VisualizationConfig; rows?: Record<string, any>[] | null }) {
  if (!config || !rows || rows.length === 0) return null;

  const { type, x_axis, y_axis, title } = config;

  if (type === 'kpi' || (rows.length === 1 && Object.keys(rows[0]).length === 1)) {
    const key = Object.keys(rows[0])[0];
    const val = rows[0][key];
    return (
      <div className="kpi-card my-3 p-4 rounded-xl bg-surface-50 border border-surface-200 text-center">
        <p className="text-xs font-medium text-surface-500 uppercase tracking-wider">{title || key}</p>
        <p className="text-3xl font-bold text-brand-600 mt-1">{formatValue(val)}</p>
      </div>
    );
  }

  if ((type === 'bar' || type === 'pie' || type === 'line') && x_axis && y_axis) {
    const numericValues = rows.map((r) => Number(r[y_axis]) || 0);
    const maxVal = Math.max(...numericValues, 1);

    return (
      <div className="chart-card my-3 p-4 rounded-xl bg-surface-50 border border-surface-200">
        {title && <p className="text-xs font-semibold text-surface-600 mb-3">{title}</p>}
        <div className="space-y-2">
          {rows.slice(0, 10).map((row, idx) => {
            const xVal = String(row[x_axis] ?? `Item ${idx + 1}`);
            const yVal = Number(row[y_axis]) || 0;
            const pct = Math.min(100, Math.max(5, (yVal / maxVal) * 100));

            return (
              <div key={idx} className="flex items-center gap-3 text-xs">
                <span className="w-28 truncate font-medium text-surface-700" title={xVal}>
                  {xVal}
                </span>
                <div className="flex-1 bg-surface-200 h-4 rounded-full overflow-hidden flex items-center">
                  <div
                    className="bg-brand-500 h-full rounded-full transition-all duration-300 flex items-center justify-end px-2"
                    style={{ width: `${pct}%` }}
                  >
                    <span className="text-[10px] text-white font-medium">{yVal}</span>
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      </div>
    );
  }

  return null;
}

export function QueryResult({ response, onClarify, onConfirm, onRetry }: Props) {
  const [cancelled, setCancelled] = useState(false);

  if (response.status === 'SUCCESS') {
    return (
      <div className="result-card success-result">
        {response.explanation && <p className="result-summary">{response.explanation}</p>}

        {response.visualization && (
          <VisualizationView config={response.visualization} rows={response.rows} />
        )}

        {response.row_count !== null && response.row_count !== undefined && !response.rows && (
          <p className="result-summary">{response.message || `${response.row_count} record(s) affected.`}</p>
        )}

        {response.columns && response.rows && (
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  {response.columns.map((column) => (
                    <th key={column}>{column}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {response.rows.map((row, rowIndex) => (
                  <tr key={rowIndex}>
                    {response.columns!.map((column) => (
                      <td key={column}>{formatValue(row[column])}</td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {response.rows?.length === 0 && <p className="result-summary">No matching records were found.</p>}
        {response.sql && <SqlBlock sql={response.sql} />}
      </div>
    );
  }

  if (response.status === 'CLARIFICATION_REQUIRED') {
    return (
      <div className="result-card">
        <p className="result-summary font-medium">{response.question || 'Please clarify your intent:'}</p>
        <div className="option-list mt-3 flex flex-wrap gap-2">
          {response.options?.map((option) => (
            <button
              key={option}
              disabled={!response.request_id}
              onClick={() => response.request_id && onClarify(response.request_id, option)}
            >
              {option}
            </button>
          ))}
        </div>
      </div>
    );
  }

  if (response.status === 'CONFIRMATION_REQUIRED') {
    if (cancelled) {
      return (
        <div className="result-card text-surface-500 italic">
          <p>Operation cancelled by user.</p>
        </div>
      );
    }

    const isDelete = response.operation === 'DELETE';
    const isUpdate = response.operation === 'UPDATE';

    return (
      <div className={`result-card ${isDelete ? 'border-red-500 bg-red-50/20' : 'caution-result'}`}>
        <p className="eyebrow font-semibold text-amber-600 uppercase tracking-wider text-xs">
          {isDelete ? '🚨 Dangerous Operation Confirmation' : 'Confirmation Required'}
        </p>

        <p className="result-summary mt-1 font-medium">
          {response.message ||
            (isDelete
              ? 'This action will permanently delete records from the database.'
              : isUpdate
              ? 'This operation will modify existing database records.'
              : 'Please confirm before execution.')}
        </p>

        {response.estimated_affected_rows !== null && response.estimated_affected_rows !== undefined && (
          <p className="muted text-xs text-surface-600 mt-1">
            Estimated affected records: <strong>{response.estimated_affected_rows}</strong>
          </p>
        )}

        {response.sql && <SqlBlock sql={response.sql} />}

        <div className="flex gap-3 mt-4">
          <button
            className={`confirm-button ${isDelete ? 'bg-red-600 hover:bg-red-700 text-white' : ''}`}
            disabled={!response.confirmation_token}
            onClick={() => response.confirmation_token && onConfirm(response.confirmation_token)}
          >
            {isDelete ? 'Confirm Delete' : 'Confirm Change'}
          </button>
          <button
            className="px-4 py-2 text-sm rounded-lg border border-surface-300 text-surface-700 hover:bg-surface-100"
            onClick={() => setCancelled(true)}
          >
            Cancel
          </button>
        </div>
      </div>
    );
  }

  if (response.status === 'RETRY_REQUIRED') {
    return (
      <div className="result-card caution-result">
        <p className="result-summary text-amber-700 font-medium">
          {response.message || "Can't understand, please say again."}
        </p>
        <p className="text-xs text-surface-500 mt-1">
          Please click the microphone button below to record your voice query again.
        </p>
        <button className="text-button mt-3 font-semibold text-brand-600 hover:underline" onClick={onRetry}>
          🎤 Speak Again
        </button>
      </div>
    );
  }

  const isSecurity = response.status === 'SECURITY_VIOLATION';
  const retryable = ['FAILED', 'VALIDATION_FAILED', 'EXECUTION_FAILED', 'INVALID_CONFIRMATION'].includes(response.status);

  return (
    <div className={`result-card ${isSecurity ? 'caution-result' : 'error-result'}`}>
      <p className="result-summary">{response.message || 'The request could not be completed.'}</p>
      {response.validation?.issues?.length ? (
        <ul className="issue-list mt-2 space-y-1 text-xs text-red-600">
          {response.validation.issues.map((issue, idx) => (
            <li key={idx}>• {issue}</li>
          ))}
        </ul>
      ) : null}
      {response.sql && <SqlBlock sql={response.sql} />}
      {retryable && (
        <button className="text-button mt-3" onClick={onRetry}>
          Try again
        </button>
      )}
    </div>
  );
}

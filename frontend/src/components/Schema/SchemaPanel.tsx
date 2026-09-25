import { useEffect, useState } from 'react';
import type { TableSchema } from '@/types';

interface Props { isOpen: boolean; onClose: () => void; loadSchema: () => Promise<{ tables: Record<string, TableSchema> }>; }

export function SchemaPanel({ isOpen, onClose, loadSchema }: Props) {
  const [tables, setTables] = useState<Record<string, TableSchema>>({});
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => { if (!isOpen || Object.keys(tables).length) return; setLoading(true); loadSchema().then((data) => setTables(data.tables)).catch(() => setError('Schema details are unavailable right now.')).finally(() => setLoading(false)); }, [isOpen, loadSchema, tables]);
  if (!isOpen) return null;
  return <div className="panel-layer" role="presentation" onMouseDown={onClose}><aside className="schema-panel" role="dialog" aria-modal="true" aria-label="Database schema" onMouseDown={(event) => event.stopPropagation()}><header><div><p className="eyebrow">Available data</p><h2>Database schema</h2></div><button className="icon-button" onClick={onClose} aria-label="Close schema">×</button></header>{loading && <p className="panel-message">Loading schema...</p>}{error && <p className="panel-message">{error}</p>}{!loading && !error && <div className="schema-list">{Object.entries(tables).map(([table, info]) => <details key={table}><summary><span>{table}</span><span>{info.columns.length} columns</span></summary><div className="column-list">{info.columns.map((column) => <div key={column.name}><code>{column.name}</code><span>{column.type}{column.primary_key ? ' · primary' : ''}</span></div>)}</div></details>)}{Object.keys(tables).length === 0 && <p className="panel-message">No tables were returned.</p>}</div>}</aside></div>;
}

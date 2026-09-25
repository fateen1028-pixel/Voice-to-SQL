import type { HistoryItem } from '@/types';

interface Props {
  items: HistoryItem[];
  onSelect: (message: string) => void;
}

export function HistoryPanel({ items, onSelect }: Props) {
  if (items.length === 0) return <p className="text-sm text-surface-400">No conversation history yet.</p>;
  return (
    <div className="space-y-1">
      {items.slice(-10).reverse().map((item, i) => (
        <button key={i} onClick={() => onSelect(item.message)} className="w-full text-left px-3 py-2 rounded-lg hover:bg-surface-100 transition-colors group">
          <p className="text-sm text-surface-700 truncate group-hover:text-brand-600 transition-colors">{item.message}</p>
          <p className="text-xs text-surface-400 mt-0.5">{new Date(item.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}</p>
        </button>
      ))}
    </div>
  );
}

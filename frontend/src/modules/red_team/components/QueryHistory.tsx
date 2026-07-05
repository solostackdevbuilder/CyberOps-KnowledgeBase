import { useState, useEffect } from 'react';
import { History, Clock, RotateCcw, Trash2 } from 'lucide-react';
import {
  getQueryHistory,
  getCachedQuery,
  deleteCachedQuery,
  type QueryHistoryItem,
} from '../services/api';
import type { QueryResponse } from '../types';

interface QueryHistoryProps {
  onSelectQuery: (query: string, response: QueryResponse) => void;
  onRerunQuery: (query: string) => void;
  refreshTrigger?: string;
}

function QueryHistory({ onSelectQuery, onRerunQuery, refreshTrigger }: QueryHistoryProps) {
  const [history, setHistory] = useState<QueryHistoryItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [deletingId, setDeletingId] = useState<string | null>(null);

  useEffect(() => {
    loadHistory();
  }, [refreshTrigger]);

  const loadHistory = async () => {
    setLoading(true);
    try {
      const data = await getQueryHistory(10);
      // Deduplicate: keep only the most recent entry for each unique question
      const uniqueQueries = new Map<string, QueryHistoryItem>();
      for (const item of data) {
        const question = item.question.trim().toLowerCase();
        const existing = uniqueQueries.get(question);
        if (!existing || new Date(item.created_at) > new Date(existing.created_at)) {
          uniqueQueries.set(question, item);
        }
      }
      // Convert back to array and sort by created_at (newest first)
      const deduplicated = Array.from(uniqueQueries.values()).sort(
        (a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime()
      );
      setHistory(deduplicated);
    } catch (err) {
      console.error('Failed to load query history:', err);
    } finally {
      setLoading(false);
    }
  };

  const handleQueryClick = async (item: QueryHistoryItem) => {
    setSelectedId(item.id);
    try {
      const cachedResponse = await getCachedQuery(item.id);
      onSelectQuery(item.question, cachedResponse);
    } catch (err) {
      console.error('Failed to load cached query:', err);
      // If cache fails, just rerun the query
      onRerunQuery(item.question);
    }
  };

  const handleRerun = (e: React.MouseEvent, item: QueryHistoryItem) => {
    e.stopPropagation();
    onRerunQuery(item.question);
  };

  const handleDelete = async (e: React.MouseEvent, item: QueryHistoryItem) => {
    e.stopPropagation();

    const shouldDelete = window.confirm('Delete this cached query from history?');
    if (!shouldDelete) return;

    setDeletingId(item.id);
    try {
      await deleteCachedQuery(item.id);
      setHistory((prev) => prev.filter((entry) => entry.id !== item.id));
      if (selectedId === item.id) {
        setSelectedId(null);
      }
    } catch (err) {
      console.error('Failed to delete cached query:', err);
    } finally {
      setDeletingId(null);
    }
  };

  const formatDate = (dateString: string) => {
    const date = new Date(dateString);
    const now = new Date();
    const diffMs = now.getTime() - date.getTime();
    const diffHours = Math.floor(diffMs / 3600000);

    // Show "Just now" if within the last hour
    if (diffHours < 1) {
      return 'Just now';
    } else {
      // After 1 hour, show date and time
      return date.toLocaleString('en-US', {
        month: 'short',
        day: 'numeric',
        hour: 'numeric',
        minute: '2-digit',
        year: date.getFullYear() !== now.getFullYear() ? 'numeric' : undefined,
      });
    }
  };

  return (
    <div className="h-full flex flex-col">
      <div className="flex items-center gap-2 mb-4 pb-3 border-b border-gray-700">
        <History className="h-5 w-5 text-gray-400" />
        <h2 className="text-lg font-semibold text-white">Query History</h2>
      </div>

      {loading ? (
        <div className="flex items-center justify-center py-8 text-gray-500">
          <Clock className="h-5 w-5 mr-2 animate-spin" />
          Loading...
        </div>
      ) : history.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-8 text-gray-500 text-sm">
          <History className="h-8 w-8 mb-2 opacity-50" />
          <p>No queries yet</p>
        </div>
      ) : (
        <div className="flex-1 overflow-y-auto space-y-2">
          {history.map((item) => (
            <div
              key={item.id}
              className={`p-3 rounded-lg border cursor-pointer transition-colors ${
                selectedId === item.id
                  ? 'bg-blue-600/20 border-blue-500/50'
                  : 'bg-gray-800/50 border-gray-700 hover:bg-gray-800 hover:border-gray-600'
              }`}
              onClick={() => handleQueryClick(item)}
            >
              <div className="flex items-start justify-between gap-2 mb-2">
                <p className="text-sm text-gray-300 line-clamp-2 flex-1">
                  {item.question}
                </p>
                <div className="flex items-center gap-1">
                  <button
                    onClick={(e) => handleRerun(e, item)}
                    className="flex-shrink-0 p-1.5 rounded hover:bg-gray-700 transition-colors"
                    title="Rerun query"
                    disabled={deletingId === item.id}
                  >
                    <RotateCcw className="h-4 w-4 text-gray-400 hover:text-blue-400" />
                  </button>
                  <button
                    onClick={(e) => handleDelete(e, item)}
                    className="flex-shrink-0 p-1.5 rounded hover:bg-red-900/30 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                    title="Delete cached query"
                    disabled={deletingId === item.id}
                  >
                    <Trash2 className="h-4 w-4 text-red-400" />
                  </button>
                </div>
              </div>
              <div className="flex items-center gap-2 text-xs text-gray-500">
                <Clock className="h-3 w-3" />
                <span>{formatDate(item.created_at)}</span>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

export default QueryHistory;


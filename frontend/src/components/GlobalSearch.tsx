import { useState, useEffect, useRef, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { Search, X, Clock, Code, Activity } from 'lucide-react';
import { getSessions, getOperations } from '../modules/red_team/services/api';
import type { Session, Operation } from '../modules/red_team/types';

interface SearchResult {
  id: string;
  type: 'session' | 'operation' | 'action';
  title: string;
  subtitle?: string;
  action: () => void;
}

interface GlobalSearchProps {
  isOpen: boolean;
  onClose: () => void;
}

export default function GlobalSearch({ isOpen, onClose }: GlobalSearchProps) {
  const navigate = useNavigate();
  const [query, setQuery] = useState('');
  const [results, setResults] = useState<SearchResult[]>([]);
  const [selectedIndex, setSelectedIndex] = useState(0);
  const [recentSearches, setRecentSearches] = useState<string[]>([]);
  const [sessions, setSessions] = useState<Session[]>([]);
  const [operations, setOperations] = useState<Operation[]>([]);
  const inputRef = useRef<HTMLInputElement>(null);
  const resultsRef = useRef<HTMLDivElement>(null);

  // Load sessions and operations
  const loadData = async () => {
    try {
      const [sessionsData, operationsData] = await Promise.all([
        getSessions(),
        getOperations(),
      ]);
      setSessions(sessionsData);
      setOperations(operationsData);
    } catch (err) {
      console.error('Failed to load search data:', err);
    }
  };

  // Load recent searches from localStorage
  const loadRecentSearches = () => {
    const stored = localStorage.getItem('recentSearches');
    if (stored) {
      try {
        setRecentSearches(JSON.parse(stored));
      } catch {
        setRecentSearches([]);
      }
    }
  };

  // Load data on mount
  useEffect(() => {
    if (isOpen) {
      loadData();
      loadRecentSearches();
      // Focus input when opened
      setTimeout(() => inputRef.current?.focus(), 100);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isOpen]);

  // Save search to recent searches
  const saveRecentSearch = (searchQuery: string) => {
    if (!searchQuery.trim()) return;
    const updated = [
      searchQuery,
      ...recentSearches.filter((s) => s !== searchQuery),
    ].slice(0, 5);
    setRecentSearches(updated);
    localStorage.setItem('recentSearches', JSON.stringify(updated));
  };

  // Perform search
  useEffect(() => {
    if (!query.trim()) {
      setResults([]);
      setSelectedIndex(0);
      return;
    }

    const searchResults: SearchResult[] = [];

    // Quick actions
    if (query.toLowerCase().startsWith('new')) {
      searchResults.push({
        id: 'action-new-session',
        type: 'action',
        title: 'New Session',
        subtitle: 'Create a new session',
        action: () => {
          saveRecentSearch(query);
          navigate('/create');
          onClose();
        },
      });
    }

    // Search sessions
    const searchLower = query.toLowerCase();
    sessions.forEach((session) => {
      const matchesTitle = session.title.toLowerCase().includes(searchLower);
      const matchesDescription = session.description?.toLowerCase().includes(searchLower);
      const matchesTags = session.tags.some((tag) =>
        tag.toLowerCase().includes(searchLower)
      );
      const matchesOperator = session.operator_name.toLowerCase().includes(searchLower);
      const matchesTerminal = session.terminal_content.toLowerCase().includes(searchLower);

      if (matchesTitle || matchesDescription || matchesTags || matchesOperator || matchesTerminal) {
        const operation = operations.find((op) => op.id === session.operation_id);
        searchResults.push({
          id: `session-${session.id}`,
          type: 'session',
          title: session.title,
          subtitle: `${operation?.name || 'Unknown'} • ${session.operator_name}`,
          action: () => {
            saveRecentSearch(query);
            navigate(`/session/${session.id}`);
            onClose();
          },
        });
      }
    });

    // Search operations
    operations.forEach((operation) => {
      if (
        operation.name.toLowerCase().includes(searchLower) ||
        operation.description?.toLowerCase().includes(searchLower)
      ) {
        searchResults.push({
          id: `operation-${operation.id}`,
          type: 'operation',
          title: operation.name,
          subtitle: operation.description || `${operation.session_ids.length} sessions`,
          action: () => {
            saveRecentSearch(query);
            navigate(`/operations/${operation.id}`);
            onClose();
          },
        });
      }
    });

    setResults(searchResults);
    setSelectedIndex(0);
  }, [query, sessions, operations, navigate, onClose]);

  // Handle keyboard navigation
  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      if (e.key === 'ArrowDown') {
        e.preventDefault();
        setSelectedIndex((prev) => Math.min(prev + 1, results.length - 1));
      } else if (e.key === 'ArrowUp') {
        e.preventDefault();
        setSelectedIndex((prev) => Math.max(prev - 1, 0));
      } else if (e.key === 'Enter' && results[selectedIndex]) {
        e.preventDefault();
        results[selectedIndex].action();
      } else if (e.key === 'Escape') {
        e.preventDefault();
        onClose();
      }
    },
    [results, selectedIndex, onClose]
  );

  // Scroll selected item into view
  useEffect(() => {
    if (resultsRef.current) {
      const selectedElement = resultsRef.current.children[selectedIndex] as HTMLElement;
      if (selectedElement) {
        selectedElement.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
      }
    }
  }, [selectedIndex]);

  // Handle click outside
  useEffect(() => {
    if (!isOpen) return;

    const handleClickOutside = (e: MouseEvent) => {
      const target = e.target as HTMLElement;
      if (!target.closest('.global-search-container')) {
        onClose();
      }
    };

    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, [isOpen, onClose]);

  if (!isOpen) return null;

  const getIcon = (type: string) => {
    switch (type) {
      case 'session':
        return <Code className="h-4 w-4" />;
      case 'operation':
        return <Activity className="h-4 w-4" />;
      case 'action':
        return <Search className="h-4 w-4" />;
      default:
        return <Search className="h-4 w-4" />;
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center pt-[20vh]">
      <div className="fixed inset-0 bg-black/50" onClick={onClose} />
      <div className="global-search-container relative w-full max-w-2xl mx-4">
        <div className="bg-gray-800 border border-gray-700 rounded-lg shadow-2xl overflow-hidden">
          {/* Search Input */}
          <div className="flex items-center px-4 py-3 border-b border-gray-700">
            <Search className="h-5 w-5 text-gray-400 mr-3" />
            <input
              ref={inputRef}
              type="text"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="Search sessions, operations, or type 'new' for actions..."
              className="flex-1 bg-transparent text-white placeholder-gray-500 outline-none text-lg"
            />
            <button
              onClick={onClose}
              className="ml-3 p-1 hover:bg-gray-700 rounded transition-colors"
            >
              <X className="h-5 w-5 text-gray-400" />
            </button>
          </div>

          {/* Results */}
          <div
            ref={resultsRef}
            className="max-h-96 overflow-y-auto"
            style={{ maxHeight: '24rem' }}
          >
            {query.trim() ? (
              results.length > 0 ? (
                <div className="py-2">
                  {results.map((result, index) => (
                    <button
                      key={result.id}
                      onClick={result.action}
                      className={`w-full px-4 py-3 flex items-start hover:bg-gray-700 transition-colors ${
                        index === selectedIndex ? 'bg-gray-700' : ''
                      }`}
                    >
                      <div className="text-gray-400 mr-3 mt-0.5">
                        {getIcon(result.type)}
                      </div>
                      <div className="flex-1 text-left">
                        <div className="text-white font-medium">{result.title}</div>
                        {result.subtitle && (
                          <div className="text-sm text-gray-400 mt-0.5">
                            {result.subtitle}
                          </div>
                        )}
                      </div>
                    </button>
                  ))}
                </div>
              ) : (
                <div className="px-4 py-8 text-center text-gray-400">
                  No results found
                </div>
              )
            ) : (
              <div className="py-2">
                {recentSearches.length > 0 && (
                  <div className="px-4 py-2 text-xs text-gray-500 uppercase tracking-wide">
                    Recent Searches
                  </div>
                )}
                {recentSearches.map((search, index) => (
                  <button
                    key={index}
                    onClick={() => {
                      setQuery(search);
                      inputRef.current?.focus();
                    }}
                    className="w-full px-4 py-2 flex items-center hover:bg-gray-700 transition-colors text-left"
                  >
                    <Clock className="h-4 w-4 text-gray-500 mr-3" />
                    <span className="text-gray-300">{search}</span>
                  </button>
                ))}
                <div className="px-4 py-2 text-xs text-gray-500 mt-4">
                  <div className="mb-2">Quick filters:</div>
                  <div className="flex flex-wrap gap-2">
                    <button
                      onClick={() => {
                        setQuery('new');
                        inputRef.current?.focus();
                      }}
                      className="px-2 py-1 bg-gray-700 hover:bg-gray-600 rounded text-xs"
                    >
                      new
                    </button>
                  </div>
                </div>
              </div>
            )}
          </div>

          {/* Footer */}
          <div className="px-4 py-2 border-t border-gray-700 flex items-center justify-between text-xs text-gray-500">
            <div className="flex items-center gap-4">
              <span>↑↓ Navigate</span>
              <span>↵ Select</span>
              <span>Esc Close</span>
            </div>
            {query.trim() && (
              <span>{results.length} result{results.length !== 1 ? 's' : ''}</span>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}


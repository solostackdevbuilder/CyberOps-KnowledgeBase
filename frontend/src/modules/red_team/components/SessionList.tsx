import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Plus,
  Calendar,
  Tag,
  Code,
  Loader2,
  Filter,
  List,
  Grid3x3,
  Clock,
  ArrowUpDown,
  Edit,
  Trash2,
  Image as ImageIcon,
  Search,
  X,
} from 'lucide-react';
import { getSessions, getOperations, deleteSession } from '../services/api';
import { useKeyboardShortcuts } from '../../../hooks/useKeyboardShortcuts';
import QuickSessionCreate from '../../../components/QuickSessionCreate';
import type { Session, Operation } from '../types';

type ViewMode = 'card' | 'list' | 'timeline';
type SortField = 'date' | 'title' | 'operator' | 'operation';
type SortDirection = 'asc' | 'desc';

function SessionList() {
  const navigate = useNavigate();
  const [sessions, setSessions] = useState<Session[]>([]);
  const [allSessions, setAllSessions] = useState<Session[]>([]);
  const [operations, setOperations] = useState<Operation[]>([]);
  const [selectedOperationId, setSelectedOperationId] = useState<string>('');
  const [searchQuery, setSearchQuery] = useState('');
  const [viewMode, setViewMode] = useState<ViewMode>('list');
  const [sortField, setSortField] = useState<SortField>('date');
  const [sortDirection, setSortDirection] = useState<SortDirection>('desc');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [hoveredSession, setHoveredSession] = useState<string | null>(null);
  const [quickCreateOpen, setQuickCreateOpen] = useState(false);

  useEffect(() => {
    loadSessions();
    loadOperations();
    // Load saved preferences
    const savedView = localStorage.getItem('sessionListView') as ViewMode;
    if (savedView && ['card', 'list', 'timeline'].includes(savedView)) {
      setViewMode(savedView);
    }
  }, []);

  useEffect(() => {
    let filtered = [...allSessions];

    // Filter by operation
    if (selectedOperationId) {
      filtered = filtered.filter((s) => s.operation_id === selectedOperationId);
    }

    // Filter by search query
    if (searchQuery.trim()) {
      const query = searchQuery.toLowerCase();
      filtered = filtered.filter(
        (s) =>
          s.title.toLowerCase().includes(query) ||
          s.description?.toLowerCase().includes(query) ||
          s.operator_name.toLowerCase().includes(query) ||
          s.tags.some((tag) => tag.toLowerCase().includes(query)) ||
          s.terminal_content.toLowerCase().includes(query)
      );
    }

    // Sort
    filtered.sort((a, b) => {
      let comparison = 0;
      switch (sortField) {
        case 'date':
          comparison =
            new Date(a.updated_at).getTime() - new Date(b.updated_at).getTime();
          break;
        case 'title':
          comparison = a.title.localeCompare(b.title);
          break;
        case 'operator':
          comparison = a.operator_name.localeCompare(b.operator_name);
          break;
        case 'operation':
          const opA = getOperationName(a.operation_id);
          const opB = getOperationName(b.operation_id);
          comparison = opA.localeCompare(opB);
          break;
      }
      return sortDirection === 'asc' ? comparison : -comparison;
    });

    setSessions(filtered);
  }, [selectedOperationId, searchQuery, allSessions, sortField, sortDirection]);

  const loadSessions = async () => {
    try {
      setLoading(true);
      const data = await getSessions();
      setAllSessions(data);
      setError(null);
    } catch (err: any) {
      setError(err.response?.data?.detail || err.message || 'Failed to load sessions');
    } finally {
      setLoading(false);
    }
  };

  const loadOperations = async () => {
    try {
      const data = await getOperations();
      setOperations(data);
    } catch (err: any) {
      console.error('Failed to load operations:', err);
    }
  };

  const getOperationName = (operationId: string) => {
    const operation = operations.find((op) => op.id === operationId);
    return operation?.name || 'Unknown Operation';
  };

  const formatDate = (dateString: string) => {
    const date = new Date(dateString);
    return date.toLocaleDateString('en-US', {
      year: 'numeric',
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    });
  };

  const formatDateShort = (dateString: string) => {
    const date = new Date(dateString);
    const now = new Date();
    const diffMs = now.getTime() - date.getTime();
    const diffDays = Math.floor(diffMs / (1000 * 60 * 60 * 24));

    if (diffDays === 0) return 'Today';
    if (diffDays === 1) return 'Yesterday';
    if (diffDays < 7) return `${diffDays} days ago`;
    return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
  };

  const truncateText = (text: string, maxLength: number) => {
    if (text.length <= maxLength) return text;
    return text.substring(0, maxLength) + '...';
  };

  const handleSort = (field: SortField) => {
    if (sortField === field) {
      setSortDirection(sortDirection === 'asc' ? 'desc' : 'asc');
    } else {
      setSortField(field);
      setSortDirection('desc');
    }
  };

  const handleViewModeChange = (mode: ViewMode) => {
    setViewMode(mode);
    localStorage.setItem('sessionListView', mode);
  };

  const handleDelete = async (sessionId: string, e?: React.MouseEvent) => {
    if (e) e.stopPropagation();
    if (!window.confirm('Are you sure you want to delete this session?')) return;

    try {
      await deleteSession(sessionId);
      loadSessions();
    } catch (err: any) {
      setError(err.response?.data?.detail || err.message || 'Failed to delete session');
    }
  };

  const handleQuickCreate = () => {
    setQuickCreateOpen(true);
  };

  // Keyboard shortcuts
  useKeyboardShortcuts([
    {
      key: 'n',
      action: handleQuickCreate,
      description: 'Create new session',
      global: false,
    },
  ]);

  if (loading) {
    return (
      <div className="flex flex-col justify-center items-center min-h-[400px] gap-4">
        <Loader2 className="h-8 w-8 animate-spin text-neon-cyan" />
        <span className="text-gray-400 text-sm font-mono">Loading sessions...</span>
      </div>
    );
  }

  const renderCardView = () => (
    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
      {sessions.map((session) => (
        <div
          key={session.id}
          onClick={() => navigate(`/session/${session.id}`)}
          onMouseEnter={() => setHoveredSession(session.id)}
          onMouseLeave={() => setHoveredSession(null)}
          className="bg-gray-800 border border-gray-700 rounded-lg p-6 cursor-pointer hover:border-blue-500 transition-all relative group"
        >
          <div className="flex justify-between items-start mb-2">
            <h2 className="text-xl font-semibold text-white truncate flex-1">
              {session.title}
            </h2>
            {hoveredSession === session.id && (
              <div className="flex gap-1 ml-2" onClick={(e) => e.stopPropagation()}>
                <button
                  onClick={() => navigate(`/session/${session.id}/edit`)}
                  className="p-1 hover:bg-gray-700 rounded transition-colors"
                  title="Edit"
                >
                  <Edit className="h-4 w-4 text-gray-400" />
                </button>
                <button
                  onClick={(e) => handleDelete(session.id, e)}
                  className="p-1 hover:bg-gray-700 rounded transition-colors"
                  title="Delete"
                >
                  <Trash2 className="h-4 w-4 text-red-400" />
                </button>
              </div>
            )}
          </div>

          <div className="mb-2">
            <a
              href={`/operations/${session.operation_id}`}
              onClick={(e) => {
                e.stopPropagation();
                navigate(`/operations/${session.operation_id}`);
              }}
              className="text-sm text-blue-400 hover:text-blue-300 transition-colors"
            >
              {getOperationName(session.operation_id)}
            </a>
            <span className="text-gray-500 text-sm ml-2">• {session.operator_name}</span>
          </div>

          {session.description && (
            <p className="text-gray-400 text-sm mb-3 line-clamp-2">{session.description}</p>
          )}

          <div className="mb-3">
            <div className="flex items-center text-gray-500 text-xs mb-2">
              <Calendar className="h-3 w-3 mr-1" />
              {formatDate(session.updated_at)}
            </div>
            <div className="flex items-start text-gray-500 text-xs">
              <Code className="h-3 w-3 mr-1 mt-0.5 flex-shrink-0" />
              <span className="font-mono text-xs">
                {truncateText(session.terminal_content, 100)}
              </span>
            </div>
          </div>

          {session.tags.length > 0 && (
            <div className="flex flex-wrap gap-2">
              {session.tags.map((tag, index) => (
                <span
                  key={index}
                  className="inline-flex items-center px-2 py-1 rounded bg-gray-700 text-gray-300 text-xs"
                >
                  <Tag className="h-3 w-3 mr-1" />
                  {tag}
                </span>
              ))}
            </div>
          )}

          {session.screenshots.length > 0 && (
            <div className="mt-3 text-xs text-gray-500 flex items-center">
              <ImageIcon className="h-3 w-3 mr-1" />
              {session.screenshots.length} screenshot{session.screenshots.length !== 1 ? 's' : ''}
            </div>
          )}
        </div>
      ))}
    </div>
  );

  const renderListView = () => (
    <div className="bg-gray-800 border border-gray-700 rounded-lg overflow-hidden">
      <table className="w-full">
        <thead className="bg-gray-700">
          <tr>
            <th className="px-4 py-3 text-left text-xs font-medium text-gray-300 uppercase tracking-wider">
              Title
            </th>
            <th
              className="px-4 py-3 text-left text-xs font-medium text-gray-300 uppercase tracking-wider cursor-pointer hover:bg-gray-600"
              onClick={() => handleSort('operation')}
            >
              <div className="flex items-center gap-1">
                Operation
                <ArrowUpDown className="h-3 w-3" />
              </div>
            </th>
            <th
              className="px-4 py-3 text-left text-xs font-medium text-gray-300 uppercase tracking-wider cursor-pointer hover:bg-gray-600"
              onClick={() => handleSort('operator')}
            >
              <div className="flex items-center gap-1">
                Operator
                <ArrowUpDown className="h-3 w-3" />
              </div>
            </th>
            <th
              className="px-4 py-3 text-left text-xs font-medium text-gray-300 uppercase tracking-wider cursor-pointer hover:bg-gray-600"
              onClick={() => handleSort('date')}
            >
              <div className="flex items-center gap-1">
                Date
                <ArrowUpDown className="h-3 w-3" />
              </div>
            </th>
            <th className="px-4 py-3 text-left text-xs font-medium text-gray-300 uppercase tracking-wider">
              Tags
            </th>
            <th className="px-4 py-3 text-right text-xs font-medium text-gray-300 uppercase tracking-wider">
              Actions
            </th>
          </tr>
        </thead>
        <tbody className="divide-y divide-gray-700">
          {sessions.map((session) => (
            <tr
              key={session.id}
              onClick={() => navigate(`/session/${session.id}`)}
              onMouseEnter={() => setHoveredSession(session.id)}
              onMouseLeave={() => setHoveredSession(null)}
              className="hover:bg-gray-700/50 cursor-pointer transition-colors"
            >
              <td className="px-4 py-3">
                <div className="text-white font-medium">{session.title}</div>
                {session.description && (
                  <div className="text-sm text-gray-400 truncate max-w-md">
                    {session.description}
                  </div>
                )}
              </td>
              <td className="px-4 py-3">
                <a
                  href={`/operations/${session.operation_id}`}
                  onClick={(e) => {
                    e.stopPropagation();
                    navigate(`/operations/${session.operation_id}`);
                  }}
                  className="text-blue-400 hover:text-blue-300 text-sm"
                >
                  {getOperationName(session.operation_id)}
                </a>
              </td>
              <td className="px-4 py-3 text-sm text-gray-300">{session.operator_name}</td>
              <td className="px-4 py-3 text-sm text-gray-400">
                {formatDateShort(session.updated_at)}
              </td>
              <td className="px-4 py-3">
                <div className="flex flex-wrap gap-1">
                  {session.tags.slice(0, 3).map((tag, index) => (
                    <span
                      key={index}
                      className="inline-flex items-center px-2 py-0.5 rounded bg-gray-700 text-gray-300 text-xs"
                    >
                      {tag}
                    </span>
                  ))}
                  {session.tags.length > 3 && (
                    <span className="text-xs text-gray-500">+{session.tags.length - 3}</span>
                  )}
                </div>
              </td>
              <td className="px-4 py-3">
                <div className="flex justify-end gap-1" onClick={(e) => e.stopPropagation()}>
                  {hoveredSession === session.id && (
                    <>
                      <button
                        onClick={() => navigate(`/session/${session.id}/edit`)}
                        className="p-1 hover:bg-gray-600 rounded transition-colors"
                        title="Edit"
                      >
                        <Edit className="h-4 w-4 text-gray-400" />
                      </button>
                      <button
                        onClick={(e) => handleDelete(session.id, e)}
                        className="p-1 hover:bg-gray-600 rounded transition-colors"
                        title="Delete"
                      >
                        <Trash2 className="h-4 w-4 text-red-400" />
                      </button>
                    </>
                  )}
                </div>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );

  const renderTimelineView = () => {
    // Group sessions by date
    const grouped = sessions.reduce((acc, session) => {
      const date = new Date(session.updated_at).toLocaleDateString('en-US', {
        year: 'numeric',
        month: 'long',
        day: 'numeric',
      });
      if (!acc[date]) acc[date] = [];
      acc[date].push(session);
      return acc;
    }, {} as Record<string, Session[]>);

    return (
      <div className="space-y-8">
        {Object.entries(grouped).map(([date, dateSessions]) => (
          <div key={date}>
            <div className="flex items-center mb-4">
              <div className="flex-1 border-t border-gray-700"></div>
              <h3 className="px-4 text-lg font-semibold text-white">{date}</h3>
              <div className="flex-1 border-t border-gray-700"></div>
            </div>
            <div className="space-y-4">
              {dateSessions.map((session) => (
                <div
                  key={session.id}
                  onClick={() => navigate(`/session/${session.id}`)}
                  onMouseEnter={() => setHoveredSession(session.id)}
                  onMouseLeave={() => setHoveredSession(null)}
                  className="bg-gray-800 border border-gray-700 rounded-lg p-4 cursor-pointer hover:border-blue-500 transition-colors relative"
                >
                  <div className="flex items-start justify-between">
                    <div className="flex-1">
                      <div className="flex items-center gap-3 mb-2">
                        <div className="w-2 h-2 bg-blue-500 rounded-full"></div>
                        <h3 className="text-lg font-semibold text-white">{session.title}</h3>
                        <span className="text-sm text-gray-400">
                          {new Date(session.updated_at).toLocaleTimeString('en-US', {
                            hour: '2-digit',
                            minute: '2-digit',
                          })}
                        </span>
                      </div>
                      <div className="ml-5 text-sm text-gray-400">
                        <span className="text-blue-400">{getOperationName(session.operation_id)}</span>
                        <span className="mx-2">•</span>
                        <span>{session.operator_name}</span>
                      </div>
                      {session.description && (
                        <p className="ml-5 mt-2 text-sm text-gray-400">{session.description}</p>
                      )}
                      {session.tags.length > 0 && (
                        <div className="ml-5 mt-2 flex flex-wrap gap-2">
                          {session.tags.map((tag, index) => (
                            <span
                              key={index}
                              className="inline-flex items-center px-2 py-0.5 rounded bg-gray-700 text-gray-300 text-xs"
                            >
                              {tag}
                            </span>
                          ))}
                        </div>
                      )}
                    </div>
                    {hoveredSession === session.id && (
                      <div className="flex gap-1" onClick={(e) => e.stopPropagation()}>
                        <button
                          onClick={() => navigate(`/session/${session.id}/edit`)}
                          className="p-1 hover:bg-gray-700 rounded transition-colors"
                          title="Edit"
                        >
                          <Edit className="h-4 w-4 text-gray-400" />
                        </button>
                        <button
                          onClick={(e) => handleDelete(session.id, e)}
                          className="p-1 hover:bg-gray-700 rounded transition-colors"
                          title="Delete"
                        >
                          <Trash2 className="h-4 w-4 text-red-400" />
                        </button>
                      </div>
                    )}
                  </div>
                </div>
              ))}
            </div>
          </div>
        ))}
      </div>
    );
  };

  return (
    <div>
      <div className="flex justify-between items-center mb-6">
        <h1 className="text-3xl font-bold text-white font-display tracking-wide">
          <span className="text-neon-cyan">_</span>Sessions
        </h1>
        <div className="flex items-center gap-3">
          <button
            onClick={handleQuickCreate}
            className="px-4 py-2 bg-gradient-to-r from-neon-green/20 to-neon-cyan/20 hover:from-neon-green/30 hover:to-neon-cyan/30 text-neon-green border border-neon-green/50 hover:border-neon-green rounded-md transition-all duration-300 flex items-center font-mono text-sm uppercase tracking-wider hover:shadow-glow-green"
            title="New Session (N)"
          >
            <Plus className="h-4 w-4 mr-2" />
            New Session
          </button>
        </div>
      </div>

      {error && (
        <div className="mb-4 p-4 bg-neon-red/10 border border-neon-red/50 rounded-md text-neon-red">
          {error}
        </div>
      )}

      {/* Search and Filters */}
      <div className="mb-6 space-y-4">
        <div className="flex items-center gap-4">
          <div className="flex-1 relative">
            <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 h-4 w-4 text-neon-cyan" />
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="Search sessions by title, description, tags, operator, or content..."
              className="w-full pl-10 pr-4 py-2 bg-cyber-black border border-cyber-border rounded-md text-neon-green placeholder-gray-600 focus:outline-none focus:border-neon-cyan focus:shadow-glow-cyan font-mono text-sm transition-all duration-300"
            />
            {searchQuery && (
              <button
                onClick={() => setSearchQuery('')}
                className="absolute right-3 top-1/2 transform -translate-y-1/2 p-1 hover:bg-cyber-gray rounded"
              >
                <X className="h-4 w-4 text-gray-400" />
              </button>
            )}
          </div>
        </div>

        <div className="flex items-center gap-4 flex-wrap">
          <div className="flex items-center gap-2">
            <Filter className="h-4 w-4 text-gray-400" />
            <label htmlFor="operation-filter" className="text-sm font-medium text-gray-300">
              Operation:
            </label>
            <select
              id="operation-filter"
              value={selectedOperationId}
              onChange={(e) => setSelectedOperationId(e.target.value)}
              className="px-3 py-1.5 bg-gray-800 border border-gray-700 rounded-md text-white text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
            >
              <option value="">All Operations</option>
              {operations.map((op) => (
                <option key={op.id} value={op.id}>
                  {op.name}
                </option>
              ))}
            </select>
            {selectedOperationId && (
              <button
                onClick={() => setSelectedOperationId('')}
                className="text-sm text-gray-400 hover:text-white underline"
              >
                Clear
              </button>
            )}
          </div>

          {/* View Mode Toggle */}
          <div className="flex items-center gap-2 ml-auto">
            <span className="text-sm text-gray-400">View:</span>
            <div className="flex bg-gray-800 border border-gray-700 rounded-md overflow-hidden">
              <button
                onClick={() => handleViewModeChange('list')}
                className={`px-3 py-1.5 transition-colors ${
                  viewMode === 'list'
                    ? 'bg-blue-600 text-white'
                    : 'text-gray-400 hover:bg-gray-700'
                }`}
                title="List View"
              >
                <List className="h-4 w-4" />
              </button>
              <button
                onClick={() => handleViewModeChange('card')}
                className={`px-3 py-1.5 transition-colors ${
                  viewMode === 'card'
                    ? 'bg-blue-600 text-white'
                    : 'text-gray-400 hover:bg-gray-700'
                }`}
                title="Card View"
              >
                <Grid3x3 className="h-4 w-4" />
              </button>
              <button
                onClick={() => handleViewModeChange('timeline')}
                className={`px-3 py-1.5 transition-colors ${
                  viewMode === 'timeline'
                    ? 'bg-blue-600 text-white'
                    : 'text-gray-400 hover:bg-gray-700'
                }`}
                title="Timeline View"
              >
                <Clock className="h-4 w-4" />
              </button>
            </div>
          </div>
        </div>
      </div>

      {sessions.length === 0 ? (
        <div className="text-center py-12">
          <Code className="h-16 w-16 mx-auto text-gray-600 mb-4" />
          <p className="text-gray-400 text-lg mb-4">
            {searchQuery || selectedOperationId
              ? 'No sessions match your filters'
              : 'No sessions yet'}
          </p>
          {!searchQuery && !selectedOperationId && (
            <button
              onClick={handleQuickCreate}
              className="px-6 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-md transition-colors"
            >
              Create Your First Session
            </button>
          )}
        </div>
      ) : (
        <>
          <div className="mb-4 text-sm text-gray-400">
            Showing {sessions.length} of {allSessions.length} session{sessions.length !== 1 ? 's' : ''}
          </div>
          {viewMode === 'list' && renderListView()}
          {viewMode === 'card' && renderCardView()}
          {viewMode === 'timeline' && renderTimelineView()}
        </>
      )}

      {/* Floating Action Button */}
      <button
        onClick={handleQuickCreate}
        className="fixed bottom-8 right-8 w-14 h-14 bg-blue-600 hover:bg-blue-700 text-white rounded-full shadow-lg flex items-center justify-center transition-all hover:scale-110 z-40"
        title="Quick Create Session (N)"
      >
        <Plus className="h-6 w-6" />
      </button>

      {/* Quick Create Modal */}
      <QuickSessionCreate
        isOpen={quickCreateOpen}
        onClose={() => setQuickCreateOpen(false)}
      />
    </div>
  );
}

export default SessionList;

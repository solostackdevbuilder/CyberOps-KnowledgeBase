import { useEffect, useState, useRef } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { ArrowLeft, Edit, Trash2, Loader2, Plus, Calendar, Activity, Download, Shield, ExternalLink, AlertTriangle, ChevronDown, Send } from 'lucide-react';
import { getOperation, getOperationSessions, deleteOperation, exportOperationFAA, getOperationCoverage } from '../services/api';
import type { OperationCoverage } from '../services/api';
import type { Operation, Session } from '../types';
import { downloadBlob } from '../../../utils/download';

function OperationDetail() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [operation, setOperation] = useState<Operation | null>(null);
  const [sessions, setSessions] = useState<Session[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadingSessions, setLoadingSessions] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [deleting, setDeleting] = useState(false);
  const [exporting, setExporting] = useState(false);
  const [showExportMenu, setShowExportMenu] = useState(false);
  const exportMenuRef = useRef<HTMLDivElement>(null);
  const [activeTab, setActiveTab] = useState<'sessions' | 'defensive'>('sessions');
  const [coverage, setCoverage] = useState<OperationCoverage | null>(null);
  const [loadingCoverage, setLoadingCoverage] = useState(false);

  useEffect(() => {
    if (id) {
      loadOperation();
      loadSessions();
    }
  }, [id]);

  useEffect(() => {
    if (id && activeTab === 'defensive') {
      loadCoverage();
    }
  }, [id, activeTab]);

  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (exportMenuRef.current && !exportMenuRef.current.contains(event.target as Node)) {
        setShowExportMenu(false);
      }
    };
    if (showExportMenu) {
      document.addEventListener('mousedown', handleClickOutside);
    }
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, [showExportMenu]);

  const loadCoverage = async () => {
    if (!id) return;
    try {
      setLoadingCoverage(true);
      const data = await getOperationCoverage(id);
      setCoverage(data);
    } catch (err: any) {
      console.error('Failed to load coverage:', err);
      setCoverage(null);
    } finally {
      setLoadingCoverage(false);
    }
  };

  const loadOperation = async () => {
    try {
      setLoading(true);
      const data = await getOperation(id!);
      setOperation(data);
      setError(null);
    } catch (err: any) {
      setError(err.response?.data?.detail || err.message || 'Failed to load operation');
    } finally {
      setLoading(false);
    }
  };

  const loadSessions = async () => {
    try {
      setLoadingSessions(true);
      const data = await getOperationSessions(id!);
      // Sort by updated_at descending (most recent first)
      data.sort((a, b) => new Date(b.updated_at).getTime() - new Date(a.updated_at).getTime());
      setSessions(data);
    } catch (err: any) {
      console.error('Failed to load sessions:', err);
    } finally {
      setLoadingSessions(false);
    }
  };

  const handleDelete = async () => {
    if (!id || !operation || !window.confirm(`Are you sure you want to delete operation "${operation.name}"? This action cannot be undone.`)) {
      return;
    }

    try {
      setDeleting(true);
      await deleteOperation(id);
      navigate('/operations');
    } catch (err: any) {
      setError(err.response?.data?.detail || err.message || 'Failed to delete operation');
      setDeleting(false);
    }
  };

  const handleExportFAA = async (
    classification: 'all' | 'finding' | 'action' = 'all',
    format: 'csv' | 'rto' = 'csv'
  ) => {
    if (!id || !operation) return;

    try {
      setExporting(true);
      setShowExportMenu(false);
      setError(null);

      const operationNameSafe = operation.name.replace(/[^a-z0-9]/gi, '_').substring(0, 50);
      const dateStr = new Date().toISOString().slice(0, 19).replace(/[:-]/g, '').replace('T', '_');

      if (format === 'rto') {
        const blob = await exportOperationFAA(id);
        downloadBlob(blob, `rto_manager_operation_${operationNameSafe}_faa_${dateStr}.csv`);
        return;
      }

      const exportOpts =
        classification === 'all' ? undefined : { classification };
      const blob = await exportOperationFAA(id, exportOpts);
      const suffix =
        classification === 'finding'
          ? '_findings'
          : classification === 'action'
            ? '_actions'
            : '';
      downloadBlob(blob, `operation_${operationNameSafe}_faa${suffix}_${dateStr}.csv`);
    } catch (err: any) {
      setError(err.response?.data?.detail || err.message || 'Failed to export FAA data');
    } finally {
      setExporting(false);
    }
  };

  const formatDate = (dateString: string) => {
    const date = new Date(dateString);
    return date.toLocaleDateString('en-US', {
      year: 'numeric',
      month: 'long',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    });
  };

  const getStatusColor = (status: string) => {
    switch (status.toLowerCase()) {
      case 'active':
        return 'bg-green-600/20 text-green-400 border-green-600/30';
      case 'completed':
        return 'bg-blue-600/20 text-blue-400 border-blue-600/30';
      case 'on-hold':
        return 'bg-yellow-600/20 text-yellow-400 border-yellow-600/30';
      default:
        return 'bg-gray-600/20 text-gray-400 border-gray-600/30';
    }
  };

  if (loading) {
    return (
      <div className="flex justify-center items-center min-h-[400px]">
        <Loader2 className="h-8 w-8 animate-spin text-blue-500" />
      </div>
    );
  }

  if (error && !operation) {
    return (
      <div>
        <button
          onClick={() => navigate('/operations')}
          className="mb-4 flex items-center text-gray-400 hover:text-white transition-colors"
        >
          <ArrowLeft className="h-4 w-4 mr-2" />
          Back to Operations
        </button>
        <div className="p-4 bg-red-900/50 border border-red-700 rounded-md text-red-200">
          {error}
        </div>
      </div>
    );
  }

  if (!operation) {
    return null;
  }

  return (
    <div className="max-w-6xl mx-auto">
      <button
        onClick={() => navigate('/operations')}
        className="mb-4 flex items-center text-gray-400 hover:text-white transition-colors"
      >
        <ArrowLeft className="h-4 w-4 mr-2" />
        Back to Operations
      </button>

      {error && (
        <div className="mb-4 p-4 bg-red-900/50 border border-red-700 rounded-md text-red-200">
          {error}
        </div>
      )}

      <div className="bg-gray-800 border border-gray-700 rounded-lg p-6 mb-6">
        <div className="flex justify-between items-start mb-4">
          <div className="flex-1">
            <div className="flex items-center gap-3 mb-2">
              <h1 className="text-3xl font-bold text-white">{operation.name}</h1>
              <span className={`px-3 py-1 rounded text-sm border ${getStatusColor(operation.status)}`}>
                {operation.status}
              </span>
            </div>
            {operation.description && (
              <p className="text-gray-400 mb-4 whitespace-pre-wrap">{operation.description}</p>
            )}
            <div className="text-sm text-gray-500">
              <div className="flex items-center mb-1">
                <Calendar className="h-4 w-4 mr-1" />
                Created: {formatDate(operation.created_at)}
              </div>
              <div className="flex items-center">
                <Activity className="h-4 w-4 mr-1" />
                {operation.session_ids.length} session{operation.session_ids.length !== 1 ? 's' : ''}
              </div>
            </div>
          </div>
          <div className="flex space-x-2">
            <div className="relative" ref={exportMenuRef}>
              <button
                type="button"
                onClick={() => setShowExportMenu((o) => !o)}
                disabled={exporting || operation.session_ids.length === 0}
                className="px-4 py-2 bg-green-600 hover:bg-green-700 text-white rounded-md transition-colors flex items-center disabled:opacity-50 disabled:cursor-not-allowed"
                title="Export findings and actions"
              >
                {exporting ? (
                  <>
                    <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                    Exporting...
                  </>
                ) : (
                  <>
                    <Download className="h-4 w-4 mr-2" />
                    Export
                    <ChevronDown className="h-4 w-4 ml-1" />
                  </>
                )}
              </button>
              {showExportMenu && !exporting && operation.session_ids.length > 0 && (
                <div className="absolute right-0 mt-2 w-64 bg-gray-800 border border-gray-700 rounded-md shadow-lg z-20 py-1">
                  <button
                    type="button"
                    onClick={() => handleExportFAA('all', 'csv')}
                    className="w-full px-4 py-2 text-left text-sm text-white hover:bg-gray-700 flex items-center gap-2 rounded-t-md"
                  >
                    <Download className="h-4 w-4 shrink-0" />
                    Export all (CSV)
                  </button>
                  <button
                    type="button"
                    onClick={() => handleExportFAA('finding', 'csv')}
                    className="w-full px-4 py-2 text-left text-sm text-white hover:bg-gray-700 flex items-center gap-2"
                  >
                    <Download className="h-4 w-4 shrink-0" />
                    Export findings only (template)
                  </button>
                  <button
                    type="button"
                    onClick={() => handleExportFAA('action', 'csv')}
                    className="w-full px-4 py-2 text-left text-sm text-white hover:bg-gray-700 flex items-center gap-2"
                  >
                    <Download className="h-4 w-4 shrink-0" />
                    Export actions only (CSV)
                  </button>
                  <div className="border-t border-gray-700 my-1" />
                  <button
                    type="button"
                    onClick={() => handleExportFAA('all', 'rto')}
                    className="w-full px-4 py-2 text-left text-sm text-white hover:bg-gray-700 flex items-center gap-2 rounded-b-md"
                  >
                    <Send className="h-4 w-4 shrink-0" />
                    Export to RTO Manager
                  </button>
                </div>
              )}
            </div>
            <button
              onClick={() => navigate(`/operations/${operation.id}/edit`)}
              className="px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-md transition-colors flex items-center"
              title="Edit operation"
            >
              <Edit className="h-4 w-4 mr-2" />
              Edit
            </button>
            <button
              onClick={handleDelete}
              disabled={deleting}
              className="px-4 py-2 bg-red-600 hover:bg-red-700 text-white rounded-md transition-colors flex items-center disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {deleting ? (
                <>
                  <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                  Deleting...
                </>
              ) : (
                <>
                  <Trash2 className="h-4 w-4 mr-2" />
                  Delete
                </>
              )}
            </button>
          </div>
        </div>
      </div>

      <div className="bg-gray-800 border border-gray-700 rounded-lg p-6">
        {/* Tabs */}
        <div className="flex border-b border-gray-700 mb-4">
          <button
            onClick={() => setActiveTab('sessions')}
            className={`px-6 py-3 text-sm font-medium transition-colors ${
              activeTab === 'sessions'
                ? 'text-white border-b-2 border-blue-500'
                : 'text-gray-400 hover:text-gray-300'
            }`}
          >
            Sessions
          </button>
          <button
            onClick={() => setActiveTab('defensive')}
            className={`px-6 py-3 text-sm font-medium transition-colors flex items-center gap-2 ${
              activeTab === 'defensive'
                ? 'text-white border-b-2 border-blue-500'
                : 'text-gray-400 hover:text-gray-300'
            }`}
          >
            <Shield className="h-4 w-4" />
            Defensive View
          </button>
        </div>

        {activeTab === 'sessions' ? (
          <>
            <div className="flex justify-between items-center mb-4">
              <h2 className="text-xl font-semibold text-white">Sessions</h2>
              <button
                onClick={() => navigate(`/create?operation_id=${operation.id}`)}
                className="px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-md transition-colors flex items-center"
              >
                <Plus className="h-4 w-4 mr-2" />
                New Session
              </button>
            </div>

        {loadingSessions ? (
          <div className="flex justify-center items-center py-8">
            <Loader2 className="h-6 w-6 animate-spin text-blue-500" />
          </div>
        ) : sessions.length === 0 ? (
          <div className="text-center py-12">
            <p className="text-gray-400 mb-4">No sessions in this operation yet</p>
            <button
              onClick={() => navigate(`/create?operation_id=${operation.id}`)}
              className="px-6 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-md transition-colors"
            >
              Create First Session
            </button>
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {sessions.map((session) => (
              <div
                key={session.id}
                onClick={() => navigate(`/session/${session.id}`)}
                className="bg-gray-900 border border-gray-700 rounded-lg p-4 cursor-pointer hover:border-blue-500 transition-colors"
              >
                <h3 className="text-lg font-semibold text-white mb-2 truncate">
                  {session.title}
                </h3>
                <div className="text-sm text-gray-500 mb-2">
                  Operator: {session.operator_name}
                </div>
                <div className="text-xs text-gray-500">
                  Updated: {formatDate(session.updated_at)}
                </div>
                {session.tags.length > 0 && (
                  <div className="flex flex-wrap gap-1 mt-2">
                    {session.tags.slice(0, 3).map((tag, index) => (
                      <span
                        key={index}
                        className="px-2 py-0.5 bg-gray-700 text-gray-300 rounded text-xs"
                      >
                        {tag}
                      </span>
                    ))}
                    {session.tags.length > 3 && (
                      <span className="px-2 py-0.5 text-gray-500 text-xs">
                        +{session.tags.length - 3}
                      </span>
                    )}
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
          </>
        ) : (
          <div>
            <h2 className="text-xl font-semibold text-white mb-4 flex items-center">
              <Shield className="h-5 w-5 mr-2 text-blue-400" />
              Detection Coverage Analysis
            </h2>
            
            {loadingCoverage ? (
              <div className="flex justify-center items-center py-12">
                <Loader2 className="h-6 w-6 animate-spin text-blue-500" />
              </div>
            ) : coverage ? (
              <div className="space-y-6">
                {/* Coverage Summary */}
                <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
                  <div className="bg-gray-900 border border-gray-700 rounded-lg p-4">
                    <div className="text-sm text-gray-400 mb-1">Total Techniques</div>
                    <div className="text-2xl font-bold text-white">{coverage.total_techniques}</div>
                  </div>
                  <div className="bg-green-900/20 border border-green-700/50 rounded-lg p-4">
                    <div className="text-sm text-gray-400 mb-1">With Strategies</div>
                    <div className="text-2xl font-bold text-green-400">{coverage.techniques_with_strategies}</div>
                  </div>
                  <div className="bg-yellow-900/20 border border-yellow-700/50 rounded-lg p-4">
                    <div className="text-sm text-gray-400 mb-1">Without Strategies</div>
                    <div className="text-2xl font-bold text-yellow-400">{coverage.techniques_without_strategies}</div>
                  </div>
                  <div className="bg-blue-900/20 border border-blue-700/50 rounded-lg p-4">
                    <div className="text-sm text-gray-400 mb-1">Coverage</div>
                    <div className="text-2xl font-bold text-blue-400">{coverage.coverage_percentage.toFixed(0)}%</div>
                  </div>
                </div>

                {/* Defensive Observations */}
                {coverage.defensive_guidance && coverage.defensive_guidance.length > 0 && (
                  <div className="bg-yellow-900/20 border border-yellow-700/50 rounded-lg p-6">
                    <h3 className="text-lg font-semibold text-yellow-300 mb-4 flex items-center gap-2">
                      <AlertTriangle className="h-5 w-5" />
                      Defensive Observations
                    </h3>
                    <p className="text-gray-300 mb-4">
                      These techniques have no formal detection strategies. Use the guidance below to implement custom detection:
                    </p>
                    <div className="space-y-4">
                      {coverage.defensive_guidance.map((guidance) => (
                        <div
                          key={guidance.technique_id}
                          className="bg-gray-900/50 border border-gray-700 rounded-lg p-4"
                        >
                          <div className="flex items-start justify-between mb-3">
                            <div>
                              <a
                                href={guidance.mitre_url}
                                target="_blank"
                                rel="noopener noreferrer"
                                className="text-yellow-400 hover:text-yellow-300 font-semibold flex items-center gap-2"
                              >
                                {guidance.technique_id} - {guidance.title}
                                <ExternalLink className="h-4 w-4" />
                              </a>
                            </div>
                          </div>
                          
                          <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mt-4">
                            <div>
                              <h4 className="text-sm font-semibold text-blue-300 mb-2">What to Check For:</h4>
                              <ul className="space-y-1 text-xs text-gray-300">
                                {guidance.what_to_check.map((item, idx) => (
                                  <li key={idx} className="flex items-start gap-2">
                                    <span className="text-blue-400 mt-1">•</span>
                                    <span>{item}</span>
                                  </li>
                                ))}
                              </ul>
                            </div>
                            
                            <div>
                              <h4 className="text-sm font-semibold text-green-300 mb-2">Monitoring:</h4>
                              <ul className="space-y-1 text-xs text-gray-300">
                                {guidance.monitoring.map((item, idx) => (
                                  <li key={idx} className="flex items-start gap-2">
                                    <span className="text-green-400 mt-1">•</span>
                                    <span>{item}</span>
                                  </li>
                                ))}
                              </ul>
                            </div>
                            
                            <div>
                              <h4 className="text-sm font-semibold text-purple-300 mb-2">Prevention:</h4>
                              <ul className="space-y-1 text-xs text-gray-300">
                                {guidance.prevention.map((item, idx) => (
                                  <li key={idx} className="flex items-start gap-2">
                                    <span className="text-purple-400 mt-1">•</span>
                                    <span>{item}</span>
                                  </li>
                                ))}
                              </ul>
                            </div>
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {/* Detection Strategies */}
                {coverage.detection_strategies.length > 0 && (
                  <div className="bg-blue-900/20 border border-blue-700/50 rounded-lg p-6">
                    <h3 className="text-lg font-semibold text-blue-300 mb-4">Detection Strategies</h3>
                    <div className="space-y-3">
                      {coverage.detection_strategies.map((strategy) => (
                        <div
                          key={strategy.id}
                          className="bg-gray-900 border border-gray-700 rounded-lg p-4"
                        >
                          <div className="flex items-start justify-between mb-2">
                            <div>
                              <a
                                href={`https://attack.mitre.org/detectionstrategies/${strategy.id}`}
                                target="_blank"
                                rel="noopener noreferrer"
                                className="text-blue-400 hover:text-blue-300 font-semibold flex items-center gap-2"
                              >
                                {strategy.id} - {strategy.name}
                                <ExternalLink className="h-4 w-4" />
                              </a>
                              {strategy.description && (
                                <p className="text-gray-400 text-sm mt-1">{strategy.description}</p>
                              )}
                            </div>
                          </div>
                          <div className="flex flex-wrap gap-2 mt-3">
                            {strategy.platforms.length > 0 && (
                              <div className="flex items-center gap-1 text-xs text-gray-400">
                                <span className="font-medium">Platforms:</span>
                                {strategy.platforms.join(', ')}
                              </div>
                            )}
                            {strategy.techniques.length > 0 && (
                              <div className="flex items-center gap-1 text-xs text-gray-400">
                                <span className="font-medium">Techniques:</span>
                                {strategy.techniques.slice(0, 3).join(', ')}
                                {strategy.techniques.length > 3 && ` +${strategy.techniques.length - 3} more`}
                              </div>
                            )}
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {/* Recommendations */}
                {coverage.recommendations.length > 0 && (
                  <div className="bg-gray-900 border border-gray-700 rounded-lg p-6">
                    <h3 className="text-lg font-semibold text-white mb-4">Recommendations</h3>
                    <ul className="space-y-2">
                      {coverage.recommendations.map((rec, index) => (
                        <li key={index} className="text-gray-300 flex items-start gap-2">
                          <span className="text-blue-400 mt-1">•</span>
                          <span>{rec}</span>
                        </li>
                      ))}
                    </ul>
                  </div>
                )}

                {coverage.total_techniques === 0 && (
                  <div className="text-center py-12 text-gray-400">
                    <p>No techniques found in this operation's FAA items.</p>
                    <p className="text-sm mt-2">Analyze sessions for FAA to see detection coverage.</p>
                  </div>
                )}
              </div>
            ) : (
              <div className="text-center py-12 text-gray-400">
                <p>Failed to load coverage data or no techniques found.</p>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

export default OperationDetail;


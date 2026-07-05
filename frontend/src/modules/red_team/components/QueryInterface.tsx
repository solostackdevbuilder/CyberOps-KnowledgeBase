import { useState, useEffect } from 'react';
import { Loader2, MessageSquare, Zap, Search, FileText, BarChart3, ShieldCheck, ShieldAlert, AlertTriangle } from 'lucide-react';
import { submitQuery, getOperationsSummary } from '../services/api';
import { getSettings } from '../../../core/services/api';
import type { QueryResponse, OperationSummary } from '../types';
import type { Settings } from '../../../core/types/settings';
import OperationScopeSelector from './OperationScopeSelector';
import QueryHistory from './QueryHistory';
import AnswerCard from '../../../core/components/query/AnswerCard';
import SourceCard from '../../../core/components/query/SourceCard';
import IOCDisplay, { extractIOCs } from '../../../core/components/query/IOCDisplay';

function QueryInterface() {
  const [queryText, setQueryText] = useState('');
  const [loading, setLoading] = useState(false);
  const [loadingOperations, setLoadingOperations] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [response, setResponse] = useState<QueryResponse | null>(null);
  const [settings, setSettings] = useState<Settings | null>(null);
  const [selectedOperation, setSelectedOperation] = useState<string>('all');
  const [operations, setOperations] = useState<OperationSummary[]>([]);
  const [operationsError, setOperationsError] = useState<string | null>(null);

  useEffect(() => {
    loadSettings();
    loadOperations();
  }, []);

  const loadSettings = async () => {
    try {
      const data = await getSettings();
      setSettings(data);
    } catch (err) {
      // Silently fail - don't block the UI if settings can't be loaded
      console.error('Failed to load settings:', err);
    }
  };

  const loadOperations = async () => {
    setLoadingOperations(true);
    setOperationsError(null);
    try {
      const ops = await getOperationsSummary();
      setOperations(ops);
    } catch (err: any) {
      console.error('Failed to load operations:', err);
      setOperationsError(
        err.response?.data?.detail || err.message || 'Failed to load operations'
      );
      // Default to "all" if operations can't be loaded
      setSelectedOperation('all');
    } finally {
      setLoadingOperations(false);
    }
  };

  const getProviderDisplay = () => {
    if (!settings || !settings.llm_config) return null;

    const provider = settings.llm_provider;
    const model = settings.llm_config.model_name;

    const providerNames: Record<string, string> = {
      claude: 'Claude',
      openai: 'OpenAI',
      ollama: 'Ollama',
    };

    const providerName = providerNames[provider] || provider;

    // Format model name for display - show a simplified version
    let modelDisplay = '';
    if (model) {
      // For Claude models like "claude-3-5-sonnet-20241022", show "3.5 Sonnet"
      if (provider === 'claude' && model.includes('sonnet')) {
        const match = model.match(/claude-(\d+)-(\d+)-sonnet/);
        if (match) {
          modelDisplay = `${match[1]}.${match[2]} Sonnet`;
        } else if (model.includes('opus')) {
          modelDisplay = 'Opus';
        } else if (model.includes('haiku')) {
          modelDisplay = 'Haiku';
        } else {
          modelDisplay = model.split('-').slice(-2, -1)[0] || model;
        }
      } else if (provider === 'openai') {
        // For OpenAI, show simplified name like "GPT-4 Turbo"
        modelDisplay = model.replace('gpt-', 'GPT-').replace(/-/g, ' ');
      } else {
        // For Ollama, just show the model name
        modelDisplay = model;
      }
      modelDisplay = ` (${modelDisplay})`;
    }

    return `${providerName}${modelDisplay}`;
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!queryText.trim()) return;

    setLoading(true);
    setError(null);
    setResponse(null);

    try {
      const operationId = selectedOperation === 'all' ? null : selectedOperation;
      const result = await submitQuery(queryText, operationId);
      setResponse(result);
      // Refresh history after successful query
      // We'll trigger this via a key change in QueryHistory component
    } catch (err: any) {
      setError(err.response?.data?.detail || err.message || 'Failed to process query');
      // Reset to "all" if operation was invalid
      if (err.response?.status === 404 && selectedOperation !== 'all') {
        setSelectedOperation('all');
      }
    } finally {
      setLoading(false);
    }
  };

  const handleSelectCachedQuery = (query: string, response: QueryResponse) => {
    setQueryText(query);
    setResponse(response);
    setError(null);
  };

  const handleRerunQuery = async (query: string) => {
    setQueryText(query);
    setResponse(null);
    setError(null);
    
    // Submit the query programmatically
    setLoading(true);
    try {
      const operationId = selectedOperation === 'all' ? null : selectedOperation;
      const result = await submitQuery(query, operationId);
      setResponse(result);
    } catch (err: any) {
      setError(err.response?.data?.detail || err.message || 'Failed to process query');
      if (err.response?.status === 404 && selectedOperation !== 'all') {
        setSelectedOperation('all');
      }
    } finally {
      setLoading(false);
    }
  };

  const getLoadingMessage = () => {
    if (selectedOperation === 'all') {
      const totalSessions = operations.reduce((sum, op) => sum + op.session_count, 0);
      return `Querying ${totalSessions} sessions from all operations...`;
    } else {
      const operation = operations.find((op) => op.id === selectedOperation);
      if (operation) {
        return `Querying ${operation.session_count} sessions from ${operation.name}...`;
      }
      return 'Querying...';
    }
  };

  const totalSessions = operations.reduce((sum, op) => sum + op.session_count, 0);
  const selectedOp = operations.find((op) => op.id === selectedOperation);

  return (
    <div className="max-w-7xl mx-auto">
      {/* Header - Keep Using: Claude in top-right */}
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-3xl font-bold text-white flex items-center">
          <MessageSquare className="h-8 w-8 mr-3" />
          Query Knowledge Base
        </h1>
        {settings && getProviderDisplay() && (
          <div className="flex items-center text-sm text-gray-400 bg-gray-800/50 px-3 py-1.5 rounded-md border border-gray-700">
            <Zap className="h-4 w-4 mr-1.5 text-blue-400" />
            <span>
              Using: <span className="text-gray-300">{getProviderDisplay()}</span>
            </span>
          </div>
        )}
      </div>

      {/* Three-column layout */}
      <div className="flex gap-6">
        {/* Left column - Query history */}
        <div className="w-[280px] flex-shrink-0">
          <div className="sticky top-6 bg-gray-800 border border-gray-700 rounded-lg p-4 h-[calc(100vh-8rem)]">
            <QueryHistory
              onSelectQuery={handleSelectCachedQuery}
              onRerunQuery={handleRerunQuery}
              refreshTrigger={response?.answer}
            />
          </div>
        </div>

        {/* Middle column - Query input and results (wider) */}
        <div className="flex-1 min-w-0">
          <div className="bg-gray-800 border border-gray-700 rounded-lg p-6 mb-6">
            <p className="text-gray-400 mb-4">
              Ask questions about your red team sessions. AI will analyze your terminal logs
              and provide insights.
            </p>
            <div className="text-sm text-gray-500">
              <p>Example queries:</p>
              <ul className="list-disc list-inside mt-2 space-y-1">
                <li>"What ports were scanned in recent sessions?"</li>
                <li>"What tools were used for reconnaissance?"</li>
                <li>"Summarize the findings from the last week"</li>
              </ul>
            </div>
          </div>

          <form onSubmit={handleSubmit} className="mb-6">
            <div className="bg-gray-800 border border-gray-700 rounded-lg p-4">
              {operationsError && (
                <div className="mb-4 p-3 bg-yellow-900/30 border border-yellow-700/50 rounded-md text-yellow-200 text-sm">
                  {operationsError}. Defaulting to "All Operations".
                </div>
              )}

              {selectedOperation !== 'all' && selectedOp && selectedOp.session_count === 0 && (
                <div className="mb-4 p-3 bg-gray-700/50 border border-gray-600 rounded-md text-gray-400 text-sm">
                  This operation has no sessions yet.
                </div>
              )}

              <textarea
                value={queryText}
                onChange={(e) => setQueryText(e.target.value)}
                placeholder="Enter your question here..."
                rows={4}
                className="w-full px-4 py-2 bg-gray-900 border border-gray-700 rounded-md text-white placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent resize-y"
                disabled={loading}
              />
              <div className="mt-4 flex justify-end">
                <button
                  type="submit"
                  disabled={loading || !queryText.trim() || loadingOperations}
                  className="px-6 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-md transition-colors disabled:opacity-50 disabled:cursor-not-allowed flex items-center"
                >
                  {loading ? (
                    <>
                      <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                      {getLoadingMessage()}
                    </>
                  ) : (
                    <>
                      <Search className="h-4 w-4 mr-2" />
                      Query
                    </>
                  )}
                </button>
              </div>
            </div>
          </form>

          {error && (
            <div className="mb-6 p-4 bg-red-900/50 border border-red-700 rounded-md text-red-200">
              {error}
            </div>
          )}

          {response && (
            <div className="space-y-6">
              {/* Scope Information Card with Confidence */}
              <div className="bg-gradient-to-br from-gray-800/90 to-gray-900/90 border border-gray-700/50 rounded-xl p-5 shadow-lg">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-3">
                    <div className="p-2 bg-blue-500/10 rounded-lg border border-blue-500/20">
                      <BarChart3 className="h-5 w-5 text-blue-400" />
                    </div>
                    <div className="flex-1">
                      {response.scope === 'all' ? (
                        <div className="text-sm text-gray-300">
                          Found results across{' '}
                          <span className="font-semibold text-white">
                            {response.operation_count || 0}
                          </span>{' '}
                          operation{response.operation_count !== 1 ? 's' : ''} (
                          <span className="font-semibold text-white">{response.session_count}</span>{' '}
                          session{response.session_count !== 1 ? 's' : ''})
                        </div>
                      ) : (
                        <div className="text-sm text-gray-300">
                          Results from{' '}
                          <span className="font-semibold text-white">{response.scope}</span> (
                          <span className="font-medium">{response.session_count}</span> session
                          {response.session_count !== 1 ? 's' : ''} queried)
                        </div>
                      )}
                    </div>
                  </div>
                  
                  {/* Confidence Badge */}
                  {response.confidence !== undefined && (
                    <div className={`flex items-center gap-2 px-3 py-1.5 rounded-lg border ${
                      response.confidence >= 0.8 
                        ? 'bg-green-500/10 border-green-500/30 text-green-400'
                        : response.confidence >= 0.5
                        ? 'bg-yellow-500/10 border-yellow-500/30 text-yellow-400'
                        : 'bg-red-500/10 border-red-500/30 text-red-400'
                    }`}>
                      {response.confidence >= 0.8 ? (
                        <ShieldCheck className="h-4 w-4" />
                      ) : response.confidence >= 0.5 ? (
                        <ShieldAlert className="h-4 w-4" />
                      ) : (
                        <AlertTriangle className="h-4 w-4" />
                      )}
                      <span className="text-sm font-medium">
                        {Math.round(response.confidence * 100)}% confidence
                      </span>
                    </div>
                  )}
                </div>
                
                {/* Validation Warnings */}
                {response.validation_warnings && response.validation_warnings.length > 0 && (
                  <div className="mt-4 p-3 bg-yellow-900/20 border border-yellow-700/30 rounded-lg">
                    <div className="flex items-center gap-2 text-yellow-400 text-sm font-medium mb-2">
                      <AlertTriangle className="h-4 w-4" />
                      Validation Notes
                    </div>
                    <ul className="text-sm text-yellow-200/80 space-y-1">
                      {response.validation_warnings.slice(0, 3).map((warning, idx) => (
                        <li key={idx} className="flex items-start gap-2">
                          <span className="text-yellow-500">•</span>
                          {warning}
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
              </div>

              {/* Answer Card */}
              <AnswerCard answer={response.answer} />

              {/* IOCs Display */}
              {(() => {
                const iocs = extractIOCs(response.answer);
                if (iocs.ips.length > 0 || iocs.domains.length > 0 || iocs.hashes.length > 0) {
                  return <IOCDisplay iocs={iocs} />;
                }
                return null;
              })()}

              {/* Sources */}
              {response.sources && response.sources.length > 0 && (
                <div className="bg-gradient-to-br from-gray-800/90 to-gray-900/90 border border-gray-700/50 rounded-xl p-6 shadow-lg">
                  <div className="flex items-center gap-3 mb-5 pb-4 border-b border-gray-700/50">
                    <div className="p-2 bg-purple-500/10 rounded-lg border border-purple-500/20">
                      <FileText className="h-5 w-5 text-purple-400" />
                    </div>
                    <h3 className="text-lg font-semibold text-white">
                      Source Sessions
                    </h3>
                    <span className="px-2.5 py-1 bg-purple-500/20 text-purple-300 rounded-md text-xs font-semibold border border-purple-500/30">
                      {response.sources.length}
                    </span>
                  </div>
                  <div className="space-y-3">
                    {response.sources.map((source) => (
                      <SourceCard
                        key={source.session_id}
                        id={source.operation_id || source.session_id}
                        title={source.session_title}
                        timestamp={source.timestamp}
                        operationName={source.operation_name}
                        navigateTo={`/session/${source.session_id}`}
                        showOperationName={response.scope === 'all'}
                      />
                    ))}
                  </div>
                </div>
              )}

              {response.sources && response.sources.length === 0 && (
                <div className="bg-gray-800/50 border border-gray-700/50 rounded-xl p-6 text-center">
                  <FileText className="h-12 w-12 mx-auto mb-3 text-gray-600 opacity-50" />
                  <p className="text-sm text-gray-500">No relevant sessions found.</p>
                </div>
              )}
            </div>
          )}

          {!response && !loading && (
            <div className="text-center py-12 text-gray-500">
              <MessageSquare className="h-16 w-16 mx-auto mb-4 opacity-50" />
              <p>Enter a query above to get started</p>
            </div>
          )}
        </div>

        {/* Right column - Scope selector sidebar (280px, sticky) */}
        <div className="w-[280px] flex-shrink-0">
          <div className="sticky top-6 bg-gray-800 border border-gray-700 rounded-lg p-4 h-[calc(100vh-8rem)]">
            <OperationScopeSelector
              operations={operations}
              selectedOperation={selectedOperation}
              onChange={setSelectedOperation}
              totalSessions={totalSessions}
              loading={loadingOperations}
            />
          </div>
        </div>
      </div>
    </div>
  );
}

export default QueryInterface;

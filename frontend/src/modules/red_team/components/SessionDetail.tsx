import { useEffect, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { ArrowLeft, Loader2, Image as ImageIcon, CheckCircle2, XCircle, Info, AlertTriangle, RefreshCw, Eye, Search, FileText, Code, Globe } from 'lucide-react';
import { getSession, deleteSession, getOperation, retryExtraction, reprocessAllScreenshots, getScreenshotUrl } from '../services/api';
import ScreenshotUpload from './ScreenshotUpload';
import ExtractionResult from './ExtractionResult';
import FAATab from './FAATab';
import SessionHeader from './SessionHeader';
import TerminalViewer from '../../../components/TerminalViewer';
import type { Session, Operation, ScreenshotExtraction } from '../types';

function SessionDetail() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [session, setSession] = useState<Session | null>(null);
  const [operation, setOperation] = useState<Operation | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [deleting, setDeleting] = useState(false);
  const [showUpload, setShowUpload] = useState(false);
  const [reprocessing, setReprocessing] = useState(false);
  const [expandedExtractions, setExpandedExtractions] = useState<Set<string>>(new Set());
  const [extractionSearch, setExtractionSearch] = useState('');
  const [activeTab, setActiveTab] = useState<'terminal' | 'screenshots' | 'faa'>('faa');

  useEffect(() => {
    if (id) {
      loadSession();
    }
  }, [id]);

  const loadSession = async () => {
    try {
      setLoading(true);
      const data = await getSession(id!);
      setSession(data);
      
      // Load operation details
      try {
        const opData = await getOperation(data.operation_id);
        setOperation(opData);
      } catch (err) {
        console.error('Failed to load operation:', err);
      }
      
      setError(null);
    } catch (err: any) {
      setError(err.response?.data?.detail || err.message || 'Failed to load session');
    } finally {
      setLoading(false);
    }
  };

  const handleDelete = async () => {
    if (!id || !window.confirm('Are you sure you want to delete this session? This action cannot be undone.')) {
      return;
    }

    try {
      setDeleting(true);
      await deleteSession(id);
      navigate('/');
    } catch (err: any) {
      setError(err.response?.data?.detail || err.message || 'Failed to delete session');
      setDeleting(false);
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

  const handleScreenshotUploaded = () => {
    setShowUpload(false);
    loadSession();
  };

  const handleRetryExtraction = async (filename: string) => {
    if (!id) return;
    try {
      await retryExtraction(id, filename);
      loadSession();
    } catch (err: any) {
      setError(err.response?.data?.detail || err.message || 'Failed to retry extraction');
    }
  };

  const handleReprocessAll = async () => {
    if (!id) return;
    try {
      setReprocessing(true);
      await reprocessAllScreenshots(id);
      loadSession();
    } catch (err: any) {
      setError(err.response?.data?.detail || err.message || 'Failed to reprocess screenshots');
    } finally {
      setReprocessing(false);
    }
  };

  const toggleExtraction = (filename: string) => {
    const newSet = new Set(expandedExtractions);
    if (newSet.has(filename)) {
      newSet.delete(filename);
    } else {
      newSet.add(filename);
    }
    setExpandedExtractions(newSet);
  };

  const getExtractionStats = () => {
    if (!session?.screenshot_extractions) {
      return {
        total: session?.screenshots.length || 0,
        extracted: 0,
        pending: 0,
        failed: 0,
      };
    }

    const total = session.screenshots.length;
    const extracted = session.screenshot_extractions.filter(
      e => e.extraction_status === 'success'
    ).length;
    const failed = session.screenshot_extractions.filter(
      e => e.extraction_status === 'failed'
    ).length;
    const pending = total - session.screenshot_extractions.length;

    return { total, extracted, pending, failed };
  };

  const getExtractionForScreenshot = (filename: string): ScreenshotExtraction | undefined => {
    return session?.screenshot_extractions?.find(e => e.filename === filename);
  };

  const getStatusBadge = (extraction: ScreenshotExtraction | undefined) => {
    if (!extraction) {
      return (
        <span className="px-2 py-0.5 text-xs bg-gray-700 text-gray-300 rounded border border-gray-600">
          No extraction
        </span>
      );
    }

    switch (extraction.extraction_status) {
      case 'success':
        return (
          <span className="px-2 py-0.5 text-xs bg-green-900/50 text-green-300 rounded border border-green-600 flex items-center gap-1">
            <CheckCircle2 className="h-3 w-3" />
            Extracted
          </span>
        );
      case 'failed':
        return (
          <span className="px-2 py-0.5 text-xs bg-red-900/50 text-red-300 rounded border border-red-600 flex items-center gap-1">
            <XCircle className="h-3 w-3" />
            Failed
          </span>
        );
      case 'no_text':
        return (
          <span className="px-2 py-0.5 text-xs bg-yellow-900/50 text-yellow-300 rounded border border-yellow-600 flex items-center gap-1">
            <Info className="h-3 w-3" />
            No text
          </span>
        );
      case 'not_supported':
        return (
          <span className="px-2 py-0.5 text-xs bg-orange-900/50 text-orange-300 rounded border border-orange-600 flex items-center gap-1">
            <AlertTriangle className="h-3 w-3" />
            Not supported
          </span>
        );
      default:
        return null;
    }
  };

  const getBorderColor = (extraction: ScreenshotExtraction | undefined) => {
    if (!extraction) return 'border-gray-700';
    switch (extraction.extraction_status) {
      case 'success':
        return 'border-green-600';
      case 'failed':
        return 'border-red-600';
      case 'no_text':
        return 'border-yellow-600';
      case 'not_supported':
        return 'border-orange-600';
      default:
        return 'border-gray-700';
    }
  };

  const filteredExtractions = () => {
    if (!session?.screenshot_extractions) return [];
    if (!extractionSearch.trim()) return session.screenshot_extractions;
    
    const searchLower = extractionSearch.toLowerCase();
    return session.screenshot_extractions.filter(e => 
      e.extracted_text?.toLowerCase().includes(searchLower) ||
      e.filename.toLowerCase().includes(searchLower) ||
      e.analysis?.toLowerCase().includes(searchLower)
    );
  };

  if (loading) {
    return (
      <div className="flex justify-center items-center min-h-[400px]">
        <Loader2 className="h-8 w-8 animate-spin text-blue-500" />
      </div>
    );
  }

  if (error && !session) {
    return (
      <div>
        <button
          onClick={() => navigate('/')}
          className="mb-4 flex items-center text-gray-400 hover:text-white transition-colors"
        >
          <ArrowLeft className="h-4 w-4 mr-2" />
          Back to Sessions
        </button>
        <div className="p-4 bg-red-900/50 border border-red-700 rounded-md text-red-200">
          {error}
        </div>
      </div>
    );
  }

  if (!session) {
    return null;
  }

  return (
    <div className="max-w-6xl mx-auto">
      <SessionHeader
        session={session}
        operation={operation}
        deleting={deleting}
        onEdit={() => navigate(`/session/${session.id}/edit`)}
        onDelete={handleDelete}
      />

      {error && (
        <div className="mb-4 p-4 bg-red-900/50 border border-red-700 rounded-md text-red-200">
          {error}
        </div>
      )}

      {/* Tabs */}
      <div className="bg-gray-800 border border-gray-700 rounded-lg mb-6">
        <div className="border-b border-gray-700">
          <nav className="flex space-x-8 px-6">
            <button
              onClick={() => setActiveTab('faa')}
              className={`py-4 px-1 border-b-2 font-medium text-sm flex items-center gap-2 ${
                activeTab === 'faa'
                  ? 'border-blue-500 text-blue-400'
                  : 'border-transparent text-gray-400 hover:text-gray-300'
              }`}
            >
              <AlertTriangle className="h-4 w-4" />
              Findings & Actions
            </button>
            <button
              onClick={() => setActiveTab('terminal')}
              className={`py-4 px-1 border-b-2 font-medium text-sm flex items-center gap-2 ${
                activeTab === 'terminal'
                  ? 'border-blue-500 text-blue-400'
                  : 'border-transparent text-gray-400 hover:text-gray-300'
              }`}
            >
              <Code className="h-4 w-4" />
              Terminal
            </button>
            <button
              onClick={() => setActiveTab('screenshots')}
              className={`py-4 px-1 border-b-2 font-medium text-sm flex items-center gap-2 ${
                activeTab === 'screenshots'
                  ? 'border-blue-500 text-blue-400'
                  : 'border-transparent text-gray-400 hover:text-gray-300'
              }`}
            >
              <ImageIcon className="h-4 w-4" />
              Screenshots ({session.screenshots.length})
            </button>
          </nav>
        </div>

        <div className="p-6">
          {activeTab === 'faa' && <FAATab sessionId={session.id} />}
          
          {activeTab === 'terminal' && (
            <TerminalViewer content={session.terminal_content} title="Terminal Content" />
          )}

          {activeTab === 'screenshots' && (
            <div>
              <div className="flex justify-between items-center mb-4">
                <div>
                  <h2 className="text-xl font-semibold text-white flex items-center mb-2">
                    <ImageIcon className="h-5 w-5 mr-2" />
                    Screenshots ({session.screenshots.length})
                  </h2>
                  {(() => {
                    const stats = getExtractionStats();
                    return (
                      <div className="flex flex-wrap gap-4 text-xs text-gray-400">
                        <span>{stats.total} screenshots uploaded</span>
                        {stats.extracted > 0 && <span className="text-green-400">{stats.extracted} with extracted text</span>}
                        {stats.pending > 0 && <span className="text-gray-500">{stats.pending} pending extraction</span>}
                        {stats.failed > 0 && <span className="text-red-400">{stats.failed} failed extraction</span>}
                      </div>
                    );
                  })()}
                </div>
                <div className="flex gap-2">
                  {session.screenshots.length > 0 && (
                    <button
                      onClick={handleReprocessAll}
                      disabled={reprocessing}
                      className="px-4 py-2 bg-purple-600 hover:bg-purple-700 text-white rounded-md transition-colors text-sm disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2"
                      title="Re-extract text from all screenshots"
                    >
                      {reprocessing ? (
                        <>
                          <Loader2 className="h-4 w-4 animate-spin" />
                          Processing...
                        </>
                      ) : (
                        <>
                          <RefreshCw className="h-4 w-4" />
                          Re-extract All
                        </>
                      )}
                    </button>
                  )}
                  <button
                    onClick={() => setShowUpload(!showUpload)}
                    className="px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-md transition-colors text-sm"
                  >
                    {showUpload ? 'Cancel' : 'Upload Screenshot'}
                  </button>
                </div>
              </div>

        {showUpload && (
          <div className="mb-6">
            <ScreenshotUpload
              sessionId={session.id}
              onUploaded={handleScreenshotUploaded}
            />
          </div>
        )}

        {session.screenshots.length === 0 ? (
          <p className="text-gray-400">No screenshots yet</p>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {session.screenshots.map((screenshot, index) => {
              const extraction = getExtractionForScreenshot(screenshot.filename);
              const isExpanded = expandedExtractions.has(screenshot.filename);
              return (
                <div
                  key={index}
                  className={`bg-gray-900 border-2 rounded-lg overflow-hidden ${getBorderColor(extraction)}`}
                >
                  <div className="relative">
                    <img
                      src={getScreenshotUrl(session.id, screenshot.filename)}
                      alt={screenshot.description || `Screenshot ${index + 1}`}
                      className="w-full h-48 object-contain bg-gray-950"
                    />
                    <div className="absolute top-2 right-2">
                      {getStatusBadge(extraction)}
                    </div>
                  </div>
                  <div className="p-3">
                    {screenshot.description && (
                      <p className="text-sm text-gray-300 mb-1">{screenshot.description}</p>
                    )}
                    {screenshot.source_url && (
                      <a
                        href={screenshot.source_url}
                        target="_blank"
                        rel="noopener noreferrer"
                        title={screenshot.source_title || screenshot.source_url}
                        className="flex items-center gap-1.5 text-xs text-[#00d4ff] hover:underline mb-1 truncate"
                      >
                        <Globe className="h-3 w-3 flex-shrink-0" />
                        <span className="truncate">
                          {screenshot.source_domain || screenshot.source_url}
                          {screenshot.source_title ? ` - ${screenshot.source_title}` : ''}
                        </span>
                      </a>
                    )}
                    <div className="flex items-center justify-between mb-2">
                      <p className="text-xs text-gray-500">
                        {formatDate(screenshot.timestamp)}
                      </p>
                      {extraction && extraction.extracted_text && (
                        <button
                          onClick={() => toggleExtraction(screenshot.filename)}
                          className="flex items-center gap-1 px-2 py-1 text-xs bg-blue-600 hover:bg-blue-700 text-white rounded transition-colors"
                          aria-label={isExpanded ? 'Hide extracted text' : 'View extracted text'}
                        >
                          <Eye className="h-3 w-3" />
                          {isExpanded ? 'Hide' : 'View'} Text
                        </button>
                      )}
                    </div>
                    {isExpanded && extraction && (
                      <div className="mt-3 pt-3 border-t border-gray-700">
                        <ExtractionResult
                          extraction={extraction}
                          onRetry={() => handleRetryExtraction(screenshot.filename)}
                        />
                      </div>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        )}
            </div>
          )}
        </div>
      </div>

      {/* Extracted Screenshot Content Section */}
      {session.screenshot_extractions && session.screenshot_extractions.length > 0 && (
        <div className="bg-gray-800 border border-gray-700 rounded-lg p-6 mt-6">
          <div className="flex justify-between items-center mb-4">
            <h2 className="text-xl font-semibold text-white flex items-center">
              <FileText className="h-5 w-5 mr-2" />
              Extracted Screenshot Content
            </h2>
          </div>

          {/* Search/Filter */}
          <div className="mb-4">
            <div className="relative">
              <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 h-4 w-4 text-gray-400" />
              <input
                type="text"
                value={extractionSearch}
                onChange={(e) => setExtractionSearch(e.target.value)}
                placeholder="Search extracted text..."
                className="w-full pl-10 pr-4 py-2 bg-gray-900 border border-gray-700 rounded-md text-white placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
              />
            </div>
          </div>

          {/* Extracted Texts */}
          <div className="space-y-4">
            {filteredExtractions().map((extraction, index) => {
              const screenshot = session.screenshots.find(s => s.filename === extraction.filename);
              return (
                <div
                  key={index}
                  className="bg-gray-900 border border-gray-700 rounded-lg p-4"
                >
                  <div className="flex items-start justify-between mb-2">
                    <div className="flex-1">
                      <div className="flex items-center gap-2 mb-1">
                        <span className="text-sm font-medium text-white">
                          {screenshot?.description || extraction.filename}
                        </span>
                        {getStatusBadge(extraction)}
                      </div>
                      {screenshot && (
                        <p className="text-xs text-gray-500">
                          {formatDate(screenshot.timestamp)}
                        </p>
                      )}
                    </div>
                  </div>
                  {extraction.extracted_text && (
                    <div className="mt-3">
                      <ExtractionResult
                        extraction={extraction}
                        onRetry={() => handleRetryExtraction(extraction.filename)}
                      />
                    </div>
                  )}
                </div>
              );
            })}
          </div>

          {filteredExtractions().length === 0 && extractionSearch && (
            <p className="text-gray-400 text-center py-4">
              No extracted text matches your search
            </p>
          )}
        </div>
      )}
    </div>
  );
}

export default SessionDetail;


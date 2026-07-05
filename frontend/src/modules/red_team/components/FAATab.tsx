import { useEffect, useState, useRef } from 'react';
import { Loader2, Search, Filter, Plus, AlertCircle, Download, ChevronDown, Send, ShieldCheck, ShieldAlert, Info } from 'lucide-react';
import {
  analyzeSessionFAA,
  getFAAItems,
  updateFAAItem,
  deleteFAAItem,
  createFAAItem,
  exportSessionFAA,
} from '../services/api';
import type { FAAItem, FAAItemCreate, FAAItemUpdate } from '../types';
import FAAItemCard from './FAAItemCard';
import FAAEditModal from './FAAEditModal';
import FAAAddModal from './FAAAddModal';
import { downloadBlob } from '../../../utils/download';

interface ValidationSummary {
  total_items_from_llm: number;
  validated_items: number;
  dropped_items: number;
  average_confidence: number;
  items_needing_review: number;
  mitre_corrections_made: number;
  grounding_issues: number;
}

interface FAATabProps {
  sessionId: string;
}

function FAATab({ sessionId }: FAATabProps) {
  const [items, setItems] = useState<FAAItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [analyzing, setAnalyzing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [editingItem, setEditingItem] = useState<FAAItem | null>(null);
  const [showAddModal, setShowAddModal] = useState(false);
  const [exporting, setExporting] = useState(false);
  const [showExportMenu, setShowExportMenu] = useState(false);
  const exportMenuRef = useRef<HTMLDivElement>(null);
  // Validation state
  const [validationSummary, setValidationSummary] = useState<ValidationSummary | null>(null);
  const [validationWarnings, setValidationWarnings] = useState<string[]>([]);
  const [showValidationDetails, setShowValidationDetails] = useState(false);
  
  // Filters
  const [classificationFilter, setClassificationFilter] = useState<'all' | 'action' | 'finding'>('all');
  const [mitreFilter, setMitreFilter] = useState('');
  const [severityFilter, setSeverityFilter] = useState<'all' | 'critical' | 'high' | 'medium' | 'low'>('all');

  useEffect(() => {
    loadItems();
  }, [sessionId]);

  const loadItems = async () => {
    try {
      setLoading(true);
      setError(null);
      const data = await getFAAItems(sessionId);
      setItems(data);
    } catch (err: any) {
      setError(err.response?.data?.detail || err.message || 'Failed to load FAA items');
    } finally {
      setLoading(false);
    }
  };

  const handleAnalyze = async () => {
    try {
      setAnalyzing(true);
      setError(null);
      setValidationSummary(null);
      setValidationWarnings([]);
      
      const response = await analyzeSessionFAA(sessionId);
      
      // Handle new validated response format
      setItems(response.items);
      setValidationSummary(response.validation_summary);
      setValidationWarnings(response.warnings || []);
      
      // Auto-show validation details if there are issues
      if (response.validation_summary.dropped_items > 0 || 
          response.validation_summary.items_needing_review > 0 ||
          response.warnings.length > 0) {
        setShowValidationDetails(true);
      }
    } catch (err: any) {
      setError(err.response?.data?.detail || err.message || 'Failed to analyze session');
    } finally {
      setAnalyzing(false);
    }
  };

  const handleEdit = (item: FAAItem) => {
    setEditingItem(item);
  };

  const handleSaveEdit = async (updates: FAAItemUpdate) => {
    if (!editingItem) return;
    try {
      const updated = await updateFAAItem(editingItem.id, sessionId, updates);
      setItems(items.map(item => item.id === updated.id ? updated : item));
      setEditingItem(null);
    } catch (err: any) {
      setError(err.response?.data?.detail || err.message || 'Failed to update item');
    }
  };

  const handleDelete = async (itemId: string) => {
    if (!window.confirm('Are you sure you want to delete this item?')) {
      return;
    }
    try {
      await deleteFAAItem(itemId, sessionId);
      setItems(items.filter(item => item.id !== itemId));
    } catch (err: any) {
      setError(err.response?.data?.detail || err.message || 'Failed to delete item');
    }
  };

  const handleAdd = async (item: FAAItemCreate) => {
    try {
      const newItem = await createFAAItem(item);
      setItems([newItem, ...items]);
      setShowAddModal(false);
    } catch (err: any) {
      setError(err.response?.data?.detail || err.message || 'Failed to create item');
    }
  };

  const handleExport = async (
    format: 'csv' | 'rto' = 'csv',
    classification: 'all' | 'finding' | 'action' = 'all'
  ) => {
    try {
      setExporting(true);
      setError(null);
      setShowExportMenu(false);

      const dateStr = new Date().toISOString().slice(0, 19).replace(/[:-]/g, '').replace('T', '_');
      let filename: string;

      if (format === 'rto') {
        const blob = await exportSessionFAA(sessionId);
        filename = `rto_manager_${sessionId}_faa_${dateStr}.csv`;
        downloadBlob(blob, filename);
        return;
      }

      const exportOpts =
        classification === 'all' ? undefined : { classification };
      const blob = await exportSessionFAA(sessionId, exportOpts);

      const suffix =
        classification === 'finding'
          ? '_findings'
          : classification === 'action'
            ? '_actions'
            : '';
      filename = `session_${sessionId}_faa${suffix}_${dateStr}.csv`;

      downloadBlob(blob, filename);
    } catch (err: any) {
      setError(err.response?.data?.detail || err.message || 'Failed to export FAA data');
    } finally {
      setExporting(false);
    }
  };

  // Close export menu when clicking outside
  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (exportMenuRef.current && !exportMenuRef.current.contains(event.target as Node)) {
        setShowExportMenu(false);
      }
    };

    if (showExportMenu) {
      document.addEventListener('mousedown', handleClickOutside);
    }

    return () => {
      document.removeEventListener('mousedown', handleClickOutside);
    };
  }, [showExportMenu]);

  // Get unique MITRE techniques for filter
  const uniqueMitreTechniques = Array.from(
    new Set(items.map(item => item.mitre_technique).filter(Boolean))
  ) as string[];

  // Filter items
  const filteredItems = items.filter(item => {
    if (classificationFilter !== 'all' && item.classification !== classificationFilter) {
      return false;
    }
    if (mitreFilter && item.mitre_technique !== mitreFilter) {
      return false;
    }
    if (severityFilter !== 'all' && item.severity !== severityFilter) {
      return false;
    }
    return true;
  });

  const stats = {
    total: items.length,
    findings: items.filter(i => i.classification === 'finding').length,
    actions: items.filter(i => i.classification === 'action').length,
  };

  if (loading) {
    return (
      <div className="flex justify-center items-center py-12">
        <Loader2 className="h-8 w-8 animate-spin text-blue-500" />
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {error && (
        <div className="p-4 bg-red-900/50 border border-red-700 rounded-md text-red-200 flex items-center gap-2">
          <AlertCircle className="h-5 w-5" />
          {error}
        </div>
      )}

      {/* Validation Summary Banner */}
      {validationSummary && (
        <div className={`p-4 rounded-lg border ${
          validationSummary.dropped_items > 0 || validationSummary.items_needing_review > 0
            ? 'bg-yellow-900/30 border-yellow-700'
            : 'bg-green-900/30 border-green-700'
        }`}>
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              {validationSummary.dropped_items > 0 || validationSummary.items_needing_review > 0 ? (
                <ShieldAlert className="h-5 w-5 text-yellow-400" />
              ) : (
                <ShieldCheck className="h-5 w-5 text-green-400" />
              )}
              <div>
                <span className="font-medium text-white">
                  Hallucination Guard: {validationSummary.validated_items} items validated
                </span>
                <span className="text-gray-400 ml-2">
                  (avg confidence: {(validationSummary.average_confidence * 100).toFixed(0)}%)
                </span>
              </div>
            </div>
            <button
              onClick={() => setShowValidationDetails(!showValidationDetails)}
              className="text-sm text-blue-400 hover:text-blue-300 flex items-center gap-1"
            >
              <Info className="h-4 w-4" />
              {showValidationDetails ? 'Hide' : 'Show'} Details
            </button>
          </div>
          
          {showValidationDetails && (
            <div className="mt-4 grid grid-cols-2 md:grid-cols-4 gap-4 text-sm">
              <div className="bg-gray-800/50 p-3 rounded">
                <div className="text-gray-400">From LLM</div>
                <div className="text-xl font-bold text-white">{validationSummary.total_items_from_llm}</div>
              </div>
              <div className="bg-gray-800/50 p-3 rounded">
                <div className="text-gray-400">Validated</div>
                <div className="text-xl font-bold text-green-400">{validationSummary.validated_items}</div>
              </div>
              <div className="bg-gray-800/50 p-3 rounded">
                <div className="text-gray-400">Dropped</div>
                <div className={`text-xl font-bold ${validationSummary.dropped_items > 0 ? 'text-red-400' : 'text-gray-400'}`}>
                  {validationSummary.dropped_items}
                </div>
              </div>
              <div className="bg-gray-800/50 p-3 rounded">
                <div className="text-gray-400">Need Review</div>
                <div className={`text-xl font-bold ${validationSummary.items_needing_review > 0 ? 'text-yellow-400' : 'text-gray-400'}`}>
                  {validationSummary.items_needing_review}
                </div>
              </div>
            </div>
          )}
          
          {showValidationDetails && validationWarnings.length > 0 && (
            <div className="mt-4">
              <div className="text-sm font-medium text-yellow-400 mb-2">Validation Warnings:</div>
              <ul className="text-sm text-gray-300 space-y-1">
                {validationWarnings.slice(0, 5).map((warning, idx) => (
                  <li key={idx} className="flex items-start gap-2">
                    <span className="text-yellow-500">•</span>
                    {warning}
                  </li>
                ))}
                {validationWarnings.length > 5 && (
                  <li className="text-gray-500">...and {validationWarnings.length - 5} more</li>
                )}
              </ul>
            </div>
          )}
        </div>
      )}

      {/* Header */}
      <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4">
        <div>
          <h2 className="text-2xl font-bold text-white mb-2">Findings & Actions</h2>
          <div className="flex gap-4 text-sm text-gray-400">
            <span>{stats.total} total</span>
            <span className="text-red-400">{stats.findings} findings</span>
            <span className="text-gray-400">{stats.actions} actions</span>
          </div>
        </div>
        <div className="flex gap-2">
          <div className="relative" ref={exportMenuRef}>
            <button
              onClick={() => setShowExportMenu(!showExportMenu)}
              disabled={exporting || items.length === 0}
              className="px-4 py-2 bg-green-600 hover:bg-green-700 text-white rounded-md transition-colors disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2"
              title="Export options"
            >
              {exporting ? (
                <>
                  <Loader2 className="h-4 w-4 animate-spin" />
                  Exporting...
                </>
              ) : (
                <>
                  <Download className="h-4 w-4" />
                  Export
                  <ChevronDown className="h-4 w-4" />
                </>
              )}
            </button>
            {showExportMenu && !exporting && (
              <div className="absolute right-0 mt-2 w-64 bg-gray-800 border border-gray-700 rounded-md shadow-lg z-10 py-1">
                <button
                  onClick={() => handleExport('csv', 'all')}
                  className="w-full px-4 py-2 text-left text-sm text-white hover:bg-gray-700 flex items-center gap-2 rounded-t-md"
                >
                  <Download className="h-4 w-4 shrink-0" />
                  Export all (CSV)
                </button>
                <button
                  onClick={() => handleExport('csv', 'finding')}
                  disabled={stats.findings === 0}
                  className="w-full px-4 py-2 text-left text-sm text-white hover:bg-gray-700 flex items-center gap-2 disabled:opacity-40 disabled:cursor-not-allowed"
                >
                  <Download className="h-4 w-4 shrink-0" />
                  Export findings only (template)
                </button>
                <button
                  onClick={() => handleExport('csv', 'action')}
                  disabled={stats.actions === 0}
                  className="w-full px-4 py-2 text-left text-sm text-white hover:bg-gray-700 flex items-center gap-2 disabled:opacity-40 disabled:cursor-not-allowed"
                >
                  <Download className="h-4 w-4 shrink-0" />
                  Export actions only (CSV)
                </button>
                <div className="border-t border-gray-700 my-1" />
                <button
                  onClick={() => handleExport('rto')}
                  className="w-full px-4 py-2 text-left text-sm text-white hover:bg-gray-700 flex items-center gap-2 rounded-b-md"
                >
                  <Send className="h-4 w-4 shrink-0" />
                  Export to RTO Manager
                </button>
              </div>
            )}
          </div>
          <button
            onClick={handleAnalyze}
            disabled={analyzing}
            className="px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-md transition-colors disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2"
          >
            {analyzing ? (
              <>
                <Loader2 className="h-4 w-4 animate-spin" />
                Analyzing...
              </>
            ) : (
              <>
                <Search className="h-4 w-4" />
                Analyze Session
              </>
            )}
          </button>
          <button
            onClick={() => setShowAddModal(true)}
            className="px-4 py-2 bg-gray-600 hover:bg-gray-700 text-white rounded-md transition-colors flex items-center gap-2"
          >
            <Plus className="h-4 w-4" />
            Add Manual Item
          </button>
        </div>
      </div>

      {/* Filters */}
      <div className="bg-gray-800 border border-gray-700 rounded-lg p-4">
        <div className="flex items-center gap-2 mb-3">
          <Filter className="h-4 w-4 text-gray-400" />
          <span className="text-sm font-medium text-gray-300">Filters</span>
        </div>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <div>
            <label className="block text-xs text-gray-400 mb-1">Classification</label>
            <select
              value={classificationFilter}
              onChange={(e) => setClassificationFilter(e.target.value as typeof classificationFilter)}
              className="w-full px-3 py-2 bg-gray-900 border border-gray-700 rounded-md text-white text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
            >
              <option value="all">All</option>
              <option value="action">Actions</option>
              <option value="finding">Findings</option>
            </select>
          </div>
          <div>
            <label className="block text-xs text-gray-400 mb-1">MITRE Technique</label>
            <select
              value={mitreFilter}
              onChange={(e) => setMitreFilter(e.target.value)}
              className="w-full px-3 py-2 bg-gray-900 border border-gray-700 rounded-md text-white text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
            >
              <option value="">All</option>
              {uniqueMitreTechniques.map(tech => (
                <option key={tech} value={tech}>{tech}</option>
              ))}
            </select>
          </div>
          <div>
            <label className="block text-xs text-gray-400 mb-1">Severity (Findings)</label>
            <select
              value={severityFilter}
              onChange={(e) => setSeverityFilter(e.target.value as typeof severityFilter)}
              className="w-full px-3 py-2 bg-gray-900 border border-gray-700 rounded-md text-white text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
            >
              <option value="all">All</option>
              <option value="critical">Critical</option>
              <option value="high">High</option>
              <option value="medium">Medium</option>
              <option value="low">Low</option>
            </select>
          </div>
        </div>
      </div>

      {/* Items List */}
      {filteredItems.length === 0 ? (
        <div className="bg-gray-800 border border-gray-700 rounded-lg p-12 text-center">
          {items.length === 0 ? (
            <div>
              <p className="text-gray-400 mb-4">
                No FAA items yet. Click 'Analyze Session' to automatically classify findings and actions.
              </p>
            </div>
          ) : (
            <p className="text-gray-400">No items match the current filters.</p>
          )}
        </div>
      ) : (
        <div className="space-y-4">
          {filteredItems.map(item => (
            <FAAItemCard
              key={item.id}
              item={item}
              onEdit={handleEdit}
              onDelete={handleDelete}
            />
          ))}
        </div>
      )}

      {/* Modals */}
      {editingItem && (
        <FAAEditModal
          item={editingItem}
          onClose={() => setEditingItem(null)}
          onSave={handleSaveEdit}
        />
      )}
      {showAddModal && (
        <FAAAddModal
          sessionId={sessionId}
          onClose={() => setShowAddModal(false)}
          onSave={handleAdd}
        />
      )}
    </div>
  );
}

export default FAATab;


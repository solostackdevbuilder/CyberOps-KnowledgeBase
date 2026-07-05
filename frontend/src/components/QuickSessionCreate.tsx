import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { X, Plus, Loader2 } from 'lucide-react';
import { createSession, getOperations } from '../modules/red_team/services/api';
import type { Operation } from '../modules/red_team/types';

interface QuickSessionCreateProps {
  isOpen: boolean;
  onClose: () => void;
  defaultOperationId?: string;
}

export default function QuickSessionCreate({
  isOpen,
  onClose,
  defaultOperationId,
}: QuickSessionCreateProps) {
  const navigate = useNavigate();
  const [operations, setOperations] = useState<Operation[]>([]);
  const [loading, setLoading] = useState(false);
  const [loadingOps, setLoadingOps] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [formData, setFormData] = useState({
    title: '',
    operation_id: defaultOperationId || '',
    terminal_content: '',
    tags: '',
    operator_name: localStorage.getItem('lastOperatorName') || '',
  });

  useEffect(() => {
    if (isOpen) {
      loadOperations();
    }
  }, [isOpen]);

  useEffect(() => {
    if (defaultOperationId && operations.length > 0) {
      setFormData((prev) => ({ ...prev, operation_id: defaultOperationId }));
    } else if (operations.length > 0 && !formData.operation_id) {
      // Set to last used operation or first operation
      const lastOpId = localStorage.getItem('lastOperationId');
      if (lastOpId && operations.find((op) => op.id === lastOpId)) {
        setFormData((prev) => ({ ...prev, operation_id: lastOpId }));
      } else {
        setFormData((prev) => ({ ...prev, operation_id: operations[0].id }));
      }
    }
  }, [operations, defaultOperationId]);

  const loadOperations = async () => {
    try {
      setLoadingOps(true);
      const data = await getOperations();
      setOperations(data);
      if (data.length === 0) {
        setError('No operations available. Please create an operation first.');
      }
    } catch (err: any) {
      setError(err.response?.data?.detail || err.message || 'Failed to load operations');
    } finally {
      setLoadingOps(false);
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!formData.title.trim()) {
      setError('Title is required');
      return;
    }
    if (!formData.operation_id) {
      setError('Please select an operation');
      return;
    }

    try {
      setLoading(true);
      setError(null);

      const tags = formData.tags
        .split(',')
        .map((t) => t.trim())
        .filter((t) => t.length > 0);

      await createSession({
        title: formData.title,
        operation_id: formData.operation_id,
        terminal_content: formData.terminal_content,
        tags,
        operator_name: formData.operator_name || 'Unknown',
      });

      // Save preferences
      localStorage.setItem('lastOperationId', formData.operation_id);
      if (formData.operator_name) {
        localStorage.setItem('lastOperatorName', formData.operator_name);
      }

      onClose();
      navigate('/');
    } catch (err: any) {
      setError(err.response?.data?.detail || err.message || 'Failed to create session');
    } finally {
      setLoading(false);
    }
  };

  const handleCreateAndAddMore = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!formData.title.trim()) {
      setError('Title is required');
      return;
    }
    if (!formData.operation_id) {
      setError('Please select an operation');
      return;
    }

    try {
      setLoading(true);
      setError(null);

      const tags = formData.tags
        .split(',')
        .map((t) => t.trim())
        .filter((t) => t.length > 0);

      await createSession({
        title: formData.title,
        operation_id: formData.operation_id,
        terminal_content: formData.terminal_content,
        tags,
        operator_name: formData.operator_name || 'Unknown',
      });

      // Save preferences
      localStorage.setItem('lastOperationId', formData.operation_id);
      if (formData.operator_name) {
        localStorage.setItem('lastOperatorName', formData.operator_name);
      }

      // Reset form but keep operation and operator
      setFormData((prev) => ({
        ...prev,
        title: '',
        terminal_content: '',
        tags: '',
      }));
      setError(null);
    } catch (err: any) {
      setError(err.response?.data?.detail || err.message || 'Failed to create session');
    } finally {
      setLoading(false);
    }
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      <div className="fixed inset-0 bg-black/50" onClick={onClose} />
      <div className="relative bg-gray-800 border border-gray-700 rounded-lg shadow-2xl w-full max-w-2xl mx-4 max-h-[90vh] overflow-y-auto">
        <div className="sticky top-0 bg-gray-800 border-b border-gray-700 px-6 py-4 flex items-center justify-between">
          <h2 className="text-xl font-semibold text-white">Quick Create Session</h2>
          <button
            onClick={onClose}
            className="p-1 hover:bg-gray-700 rounded transition-colors"
          >
            <X className="h-5 w-5 text-gray-400" />
          </button>
        </div>

        <form onSubmit={handleSubmit} className="p-6 space-y-4">
          {error && (
            <div className="p-3 bg-red-900/50 border border-red-700 rounded-md text-red-200 text-sm">
              {error}
            </div>
          )}

          <div>
            <label htmlFor="title" className="block text-sm font-medium text-gray-300 mb-1">
              Title <span className="text-red-400">*</span>
            </label>
            <input
              id="title"
              type="text"
              value={formData.title}
              onChange={(e) => setFormData({ ...formData, title: e.target.value })}
              required
              autoFocus
              className="w-full px-3 py-2 bg-gray-900 border border-gray-700 rounded-md text-white focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
              placeholder="Session title"
            />
          </div>

          <div>
            <label htmlFor="operation" className="block text-sm font-medium text-gray-300 mb-1">
              Operation <span className="text-red-400">*</span>
            </label>
            {loadingOps ? (
              <div className="flex items-center gap-2 text-gray-400">
                <Loader2 className="h-4 w-4 animate-spin" />
                <span>Loading operations...</span>
              </div>
            ) : (
              <select
                id="operation"
                value={formData.operation_id}
                onChange={(e) => setFormData({ ...formData, operation_id: e.target.value })}
                required
                className="w-full px-3 py-2 bg-gray-900 border border-gray-700 rounded-md text-white focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
              >
                <option value="">Select an operation</option>
                {operations.map((op) => (
                  <option key={op.id} value={op.id}>
                    {op.name}
                  </option>
                ))}
              </select>
            )}
          </div>

          <div>
            <label htmlFor="operator" className="block text-sm font-medium text-gray-300 mb-1">
              Operator
            </label>
            <input
              id="operator"
              type="text"
              value={formData.operator_name}
              onChange={(e) => setFormData({ ...formData, operator_name: e.target.value })}
              className="w-full px-3 py-2 bg-gray-900 border border-gray-700 rounded-md text-white focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
              placeholder="Operator name"
            />
          </div>

          <div>
            <label htmlFor="terminal" className="block text-sm font-medium text-gray-300 mb-1">
              Terminal Content
            </label>
            <textarea
              id="terminal"
              value={formData.terminal_content}
              onChange={(e) => setFormData({ ...formData, terminal_content: e.target.value })}
              rows={8}
              className="w-full px-3 py-2 bg-gray-900 border border-gray-700 rounded-md text-white font-mono text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
              placeholder="Paste terminal content here..."
            />
          </div>

          <div>
            <label htmlFor="tags" className="block text-sm font-medium text-gray-300 mb-1">
              Tags
            </label>
            <input
              id="tags"
              type="text"
              value={formData.tags}
              onChange={(e) => setFormData({ ...formData, tags: e.target.value })}
              className="w-full px-3 py-2 bg-gray-900 border border-gray-700 rounded-md text-white focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
              placeholder="tag1, tag2, tag3"
            />
            <p className="mt-1 text-xs text-gray-500">Separate tags with commas</p>
          </div>

          <div className="flex items-center justify-end gap-3 pt-4 border-t border-gray-700">
            <button
              type="button"
              onClick={onClose}
              className="px-4 py-2 text-gray-300 hover:text-white transition-colors"
            >
              Cancel
            </button>
            <button
              type="button"
              onClick={handleCreateAndAddMore}
              disabled={loading}
              className="px-4 py-2 bg-gray-700 hover:bg-gray-600 text-white rounded-md transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {loading ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <>
                  <Plus className="h-4 w-4 inline mr-1" />
                  Create & Add More
                </>
              )}
            </button>
            <button
              type="submit"
              disabled={loading}
              className="px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-md transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {loading ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                'Create Session'
              )}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}




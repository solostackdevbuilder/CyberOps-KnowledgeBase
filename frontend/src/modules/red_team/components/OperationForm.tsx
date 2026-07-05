import { useState, useEffect } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { Loader2, Save } from 'lucide-react';
import { createOperation, getOperation, updateOperation } from '../services/api';
import type { OperationCreate, OperationUpdate } from '../types';

function OperationForm() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const isEditMode = !!id;
  const [loading, setLoading] = useState(false);
  const [loadingOperation, setLoadingOperation] = useState(isEditMode);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState(false);

  const [formData, setFormData] = useState<OperationCreate>({
    name: '',
    description: '',
  });

  useEffect(() => {
    if (isEditMode && id) {
      loadOperation();
    }
  }, [id, isEditMode]);

  const loadOperation = async () => {
    try {
      setLoadingOperation(true);
      const operation = await getOperation(id!);
      setFormData({
        name: operation.name,
        description: operation.description || '',
      });
      setError(null);
    } catch (err: any) {
      setError(err.response?.data?.detail || err.message || 'Failed to load operation');
    } finally {
      setLoadingOperation(false);
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError(null);
    setSuccess(false);

    try {
      if (isEditMode && id) {
        const updateData: OperationUpdate = {
          name: formData.name,
          description: formData.description || undefined,
        };
        await updateOperation(id, updateData);
        setSuccess(true);
        setTimeout(() => {
          navigate(`/operations/${id}`);
        }, 1000);
      } else {
        await createOperation(formData);
        setSuccess(true);
        setTimeout(() => {
          navigate('/operations');
        }, 1000);
      }
    } catch (err: any) {
      setError(err.response?.data?.detail || err.message || `Failed to ${isEditMode ? 'update' : 'create'} operation`);
    } finally {
      setLoading(false);
    }
  };

  if (loadingOperation) {
    return (
      <div className="flex justify-center items-center min-h-[400px]">
        <Loader2 className="h-8 w-8 animate-spin text-blue-500" />
      </div>
    );
  }

  return (
    <div className="max-w-4xl mx-auto">
      <h1 className="text-3xl font-bold text-white mb-6">
        {isEditMode ? 'Edit Operation' : 'Create New Operation'}
      </h1>

      {error && (
        <div className="mb-4 p-4 bg-red-900/50 border border-red-700 rounded-md text-red-200">
          {error}
        </div>
      )}

      {success && (
        <div className="mb-4 p-4 bg-green-900/50 border border-green-700 rounded-md text-green-200">
          Operation {isEditMode ? 'updated' : 'created'} successfully! Redirecting...
        </div>
      )}

      <form onSubmit={handleSubmit} className="space-y-6">
        <div>
          <label htmlFor="name" className="block text-sm font-medium text-gray-300 mb-2">
            Operation Name *
          </label>
          <input
            type="text"
            id="name"
            required
            value={formData.name}
            onChange={(e) => setFormData({ ...formData, name: e.target.value })}
            className="w-full px-4 py-2 bg-gray-800 border border-gray-700 rounded-md text-white placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
            placeholder="e.g., Q4 2024 Penetration Test"
          />
        </div>

        <div>
          <label htmlFor="description" className="block text-sm font-medium text-gray-300 mb-2">
            Description
          </label>
          <textarea
            id="description"
            rows={6}
            value={formData.description}
            onChange={(e) => setFormData({ ...formData, description: e.target.value })}
            className="w-full px-4 py-2 bg-gray-800 border border-gray-700 rounded-md text-white placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent resize-y"
            placeholder="Optional description of the operation objectives, scope, etc."
          />
        </div>

        <div className="flex justify-end space-x-4">
          <button
            type="button"
            onClick={() => navigate('/operations')}
            className="px-6 py-2 bg-gray-700 hover:bg-gray-600 text-white rounded-md transition-colors"
          >
            Cancel
          </button>
          <button
            type="submit"
            disabled={loading}
            className="px-6 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-md transition-colors disabled:opacity-50 disabled:cursor-not-allowed flex items-center"
          >
            {loading ? (
              <>
                <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                {isEditMode ? 'Updating...' : 'Creating...'}
              </>
            ) : (
              <>
                <Save className="h-4 w-4 mr-2" />
                {isEditMode ? 'Update Operation' : 'Create Operation'}
              </>
            )}
          </button>
        </div>
      </form>
    </div>
  );
}

export default OperationForm;


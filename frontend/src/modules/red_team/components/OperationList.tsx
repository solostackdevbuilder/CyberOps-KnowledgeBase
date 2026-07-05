import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Plus, Calendar, Loader2, Eye, Edit, Trash2, Activity } from 'lucide-react';
import { getOperations, deleteOperation } from '../services/api';
import type { Operation } from '../types';

function OperationList() {
  const navigate = useNavigate();
  const [operations, setOperations] = useState<Operation[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [deletingId, setDeletingId] = useState<string | null>(null);

  useEffect(() => {
    loadOperations();
  }, []);

  const loadOperations = async () => {
    try {
      setLoading(true);
      const data = await getOperations();
      // Sort by created_at descending (most recent first)
      data.sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime());
      setOperations(data);
      setError(null);
    } catch (err: any) {
      setError(err.response?.data?.detail || err.message || 'Failed to load operations');
    } finally {
      setLoading(false);
    }
  };

  const handleDelete = async (id: string, name: string) => {
    if (!window.confirm(`Are you sure you want to delete operation "${name}"? This action cannot be undone.`)) {
      return;
    }

    try {
      setDeletingId(id);
      await deleteOperation(id);
      await loadOperations();
    } catch (err: any) {
      setError(err.response?.data?.detail || err.message || 'Failed to delete operation');
    } finally {
      setDeletingId(null);
    }
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

  return (
    <div>
      <div className="flex justify-between items-center mb-6">
        <h1 className="text-3xl font-bold text-white">Operations</h1>
        <button
          onClick={() => navigate('/operations/create')}
          className="px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-md transition-colors flex items-center"
        >
          <Plus className="h-4 w-4 mr-2" />
          Create New Operation
        </button>
      </div>

      {error && (
        <div className="mb-4 p-4 bg-red-900/50 border border-red-700 rounded-md text-red-200">
          {error}
        </div>
      )}

      {operations.length === 0 ? (
        <div className="text-center py-12">
          <Activity className="h-16 w-16 mx-auto text-gray-600 mb-4" />
          <p className="text-gray-400 text-lg mb-4">No operations yet</p>
          <button
            onClick={() => navigate('/operations/create')}
            className="px-6 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-md transition-colors"
          >
            Create Your First Operation
          </button>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          {operations.map((operation) => (
            <div
              key={operation.id}
              className="bg-gray-800 border border-gray-700 rounded-lg p-6 hover:border-blue-500 transition-colors"
            >
              <div className="flex justify-between items-start mb-3">
                <h2
                  onClick={() => navigate(`/operations/${operation.id}`)}
                  className="text-xl font-semibold text-white cursor-pointer hover:text-blue-400 transition-colors flex-1"
                >
                  {operation.name}
                </h2>
                <span
                  className={`px-2 py-1 rounded text-xs border ${getStatusColor(operation.status)}`}
                >
                  {operation.status}
                </span>
              </div>

              {operation.description && (
                <p className="text-gray-400 text-sm mb-4 line-clamp-2">
                  {operation.description}
                </p>
              )}

              <div className="mb-4">
                <div className="flex items-center text-gray-500 text-xs mb-2">
                  <Calendar className="h-3 w-3 mr-1" />
                  {formatDate(operation.created_at)}
                </div>
                <div className="text-gray-500 text-xs">
                  {operation.session_ids.length} session{operation.session_ids.length !== 1 ? 's' : ''}
                </div>
              </div>

              <div className="flex space-x-2 pt-4 border-t border-gray-700">
                <button
                  onClick={() => navigate(`/operations/${operation.id}`)}
                  className="flex-1 px-3 py-2 bg-blue-600/20 hover:bg-blue-600/30 text-blue-400 rounded-md transition-colors text-sm flex items-center justify-center"
                  title="View Details"
                >
                  <Eye className="h-3 w-3 mr-1" />
                  View
                </button>
                <button
                  onClick={() => navigate(`/operations/${operation.id}/edit`)}
                  className="px-3 py-2 bg-gray-700 hover:bg-gray-600 text-white rounded-md transition-colors text-sm flex items-center"
                  title="Edit Operation"
                >
                  <Edit className="h-3 w-3" />
                </button>
                <button
                  onClick={() => handleDelete(operation.id, operation.name)}
                  disabled={deletingId === operation.id}
                  className="px-3 py-2 bg-red-600/20 hover:bg-red-600/30 text-red-400 rounded-md transition-colors text-sm flex items-center disabled:opacity-50 disabled:cursor-not-allowed"
                  title="Delete Operation"
                >
                  {deletingId === operation.id ? (
                    <Loader2 className="h-3 w-3 animate-spin" />
                  ) : (
                    <Trash2 className="h-3 w-3" />
                  )}
                </button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

export default OperationList;


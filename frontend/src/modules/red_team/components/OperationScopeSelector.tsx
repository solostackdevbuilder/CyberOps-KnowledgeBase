import { Folder, FolderOpen, Globe } from 'lucide-react';
import type { OperationSummary } from '../types';

interface Props {
  operations: OperationSummary[];
  selectedOperation: string;
  onChange: (operationId: string) => void;
  totalSessions?: number;
  loading?: boolean;
}

// Generate consistent color for operation based on ID hash
const getOperationColor = (operationId: string): string => {
  const colors = [
    'bg-blue-600',
    'bg-green-600',
    'bg-purple-600',
    'bg-orange-600',
    'bg-pink-600',
    'bg-yellow-600',
    'bg-cyan-600',
    'bg-indigo-600',
  ];
  const hash = operationId
    .split('')
    .reduce((acc, char) => acc + char.charCodeAt(0), 0);
  return colors[hash % colors.length];
};

function OperationScopeSelector({
  operations,
  selectedOperation,
  onChange,
  totalSessions = 0,
  loading = false,
}: Props) {
  // Calculate total sessions if not provided
  const calculatedTotal =
    totalSessions ||
    operations.reduce((sum, op) => sum + op.session_count, 0);

  return (
    <div className="h-full flex flex-col">
      <div className="mb-4 pb-3 border-b border-gray-700/50">
        <h3 className="text-sm font-semibold text-gray-300 flex items-center gap-2">
          <Folder className="h-4 w-4" />
          Operation Scope
        </h3>
        <p className="text-xs text-gray-500 mt-1.5">
          Select which operations to search
        </p>
      </div>

      <div className="flex-1 overflow-y-auto pr-2">
        <div className="space-y-2.5">
          {/* All Operations Option */}
          <label
            className={`flex items-start p-3.5 rounded-lg cursor-pointer transition-all duration-200 ${
              selectedOperation === 'all'
                ? 'bg-gradient-to-br from-blue-600/20 to-blue-500/10 border-2 border-blue-500/50 shadow-lg shadow-blue-500/10'
                : 'bg-gray-800/50 border border-gray-700/50 hover:bg-gray-800 hover:border-gray-600 hover:shadow-md'
            }`}
          >
            <input
              type="radio"
              name="operation-scope"
              value="all"
              checked={selectedOperation === 'all'}
              onChange={(e) => onChange(e.target.value)}
              disabled={loading}
              className="mt-0.5 mr-3 h-4 w-4 text-blue-600 focus:ring-2 focus:ring-blue-500 focus:ring-offset-0 border-gray-600 bg-gray-900 cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed"
            />
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2 mb-1.5">
                <Globe className={`h-4 w-4 flex-shrink-0 ${
                  selectedOperation === 'all' ? 'text-blue-400' : 'text-gray-400'
                }`} />
                <span
                  className={`text-sm font-semibold ${
                    selectedOperation === 'all' ? 'text-white' : 'text-gray-300'
                  }`}
                >
                  All Operations
                </span>
              </div>
              <div className="flex items-center gap-2">
                <span className={`px-2 py-0.5 rounded-md text-xs font-medium ${
                  selectedOperation === 'all'
                    ? 'bg-blue-500/20 text-blue-300 border border-blue-500/30'
                    : 'bg-gray-700/50 text-gray-400 border border-gray-600/50'
                }`}>
                  {calculatedTotal} session{calculatedTotal !== 1 ? 's' : ''}
                </span>
              </div>
            </div>
          </label>

          {/* Individual Operations */}
          {operations.map((op) => {
            const isSelected = selectedOperation === op.id;
            const badgeColor = getOperationColor(op.id);
            
            return (
              <label
                key={op.id}
                className={`flex items-start p-3.5 rounded-lg cursor-pointer transition-all duration-200 ${
                  isSelected
                    ? 'bg-gradient-to-br from-blue-600/20 to-blue-500/10 border-2 border-blue-500/50 shadow-lg shadow-blue-500/10'
                    : 'bg-gray-800/50 border border-gray-700/50 hover:bg-gray-800 hover:border-gray-600 hover:shadow-md'
                }`}
              >
                <input
                  type="radio"
                  name="operation-scope"
                  value={op.id}
                  checked={isSelected}
                  onChange={(e) => onChange(e.target.value)}
                  disabled={loading}
                  className="mt-0.5 mr-3 h-4 w-4 text-blue-600 focus:ring-2 focus:ring-blue-500 focus:ring-offset-0 border-gray-600 bg-gray-900 cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed"
                />
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 mb-1.5">
                    <FolderOpen className={`h-4 w-4 flex-shrink-0 ${
                      isSelected ? 'text-blue-400' : 'text-gray-400'
                    }`} />
                    <span
                      className={`text-sm font-semibold truncate ${
                        isSelected ? 'text-white' : 'text-gray-300'
                      }`}
                      title={op.name}
                    >
                      {op.name}
                    </span>
                  </div>
                  <div className="flex items-center gap-2">
                    <span className={`px-2 py-0.5 rounded-md text-xs font-semibold text-white shadow-sm ${badgeColor}`}>
                      {op.name.substring(0, 2).toUpperCase()}
                    </span>
                    <span className={`px-2 py-0.5 rounded-md text-xs font-medium ${
                      isSelected
                        ? 'bg-blue-500/20 text-blue-300 border border-blue-500/30'
                        : 'bg-gray-700/50 text-gray-400 border border-gray-600/50'
                    }`}>
                      {op.session_count} session{op.session_count !== 1 ? 's' : ''}
                    </span>
                  </div>
                </div>
              </label>
            );
          })}
        </div>

        {operations.length === 0 && !loading && (
          <div className="mt-4 p-3.5 bg-yellow-900/30 border-l-4 border-yellow-500/50 rounded-r-lg shadow-md">
            <p className="text-sm text-yellow-200">
              No operations found. Create an operation first.
            </p>
          </div>
        )}

        {loading && (
          <div className="mt-4 p-3.5 bg-gray-800/50 border border-gray-700/50 rounded-lg">
            <p className="text-sm text-gray-400">Loading operations...</p>
          </div>
        )}
      </div>
    </div>
  );
}

export default OperationScopeSelector;


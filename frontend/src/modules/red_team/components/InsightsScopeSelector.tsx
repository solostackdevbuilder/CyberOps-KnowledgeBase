import { useState, useEffect } from 'react';
import { Folder, FolderOpen, Globe } from 'lucide-react';
import type { OperationSummary } from '../types';

interface Props {
  operations: OperationSummary[];
  selectedOperations: string[];
  onChange: (operationIds: string[]) => void;
  totalSessions?: number;
  loading?: boolean;
}

function InsightsScopeSelector({
  operations,
  selectedOperations,
  onChange,
  totalSessions = 0,
  loading = false,
}: Props) {
  const [selectAll, setSelectAll] = useState(false);

  // Calculate total sessions if not provided
  const calculatedTotal =
    totalSessions ||
    operations.reduce((sum, op) => sum + op.session_count, 0);

  // Update selectAll when selectedOperations changes
  useEffect(() => {
    if (operations.length === 0) {
      setSelectAll(false);
      return;
    }
    setSelectAll(selectedOperations.length === operations.length);
  }, [selectedOperations, operations.length]);

  const handleSelectAll = (checked: boolean) => {
    if (checked && operations.length > 0) {
      onChange(operations.map((op) => op.id));
    } else {
      onChange([]);
    }
  };

  const handleOperationToggle = (operationId: string, checked: boolean) => {
    if (checked) {
      onChange([...selectedOperations, operationId]);
    } else {
      onChange(selectedOperations.filter((id) => id !== operationId));
    }
  };

  return (
    <div className="h-full flex flex-col">
      <div className="mb-4 pb-3 border-b border-gray-700">
        <h3 className="text-sm font-medium text-gray-300 flex items-center">
          <Folder className="h-4 w-4 mr-2" />
          Operation Scope
        </h3>
        <p className="text-xs text-gray-500 mt-1">
          Select operations to analyze (multi-select)
        </p>
      </div>

      <div className="flex-1 overflow-y-auto pr-2">
        <div className="space-y-2">
          {/* All Operations Option */}
          <label
            className={`flex items-start p-3 rounded-md cursor-pointer transition-colors ${
              selectAll && operations.length > 0
                ? 'bg-blue-600/20 border border-blue-500/50'
                : 'bg-gray-800/50 border border-gray-700 hover:bg-gray-800 hover:border-gray-600'
            } border`}
          >
            <input
              type="checkbox"
              checked={selectAll}
              onChange={(e) => handleSelectAll(e.target.checked)}
              disabled={loading || operations.length === 0}
              className="mt-0.5 mr-3 h-4 w-4 text-blue-600 focus:ring-2 focus:ring-blue-500 focus:ring-offset-0 border-gray-600 bg-gray-900 cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed rounded"
            />
            <div className="flex-1 min-w-0">
              <div className="flex items-center">
                <Globe className="h-4 w-4 text-gray-400 mr-2 flex-shrink-0" />
                <span
                  className={`text-sm font-medium ${
                    selectAll && operations.length > 0 ? 'text-white' : 'text-gray-300'
                  }`}
                >
                  All Operations
                </span>
              </div>
              <p className="text-xs text-gray-500 mt-1">
                {calculatedTotal} session{calculatedTotal !== 1 ? 's' : ''}
              </p>
            </div>
          </label>

          {/* Individual Operations */}
          {operations.map((op) => {
            const isSelected = selectedOperations.includes(op.id);
            return (
              <label
                key={op.id}
                className={`flex items-start p-3 rounded-md cursor-pointer transition-colors ${
                  isSelected
                    ? 'bg-blue-600/20 border border-blue-500/50'
                    : 'bg-gray-800/50 border border-gray-700 hover:bg-gray-800 hover:border-gray-600'
                } border`}
              >
                <input
                  type="checkbox"
                  checked={isSelected}
                  onChange={(e) => handleOperationToggle(op.id, e.target.checked)}
                  disabled={loading}
                  className="mt-0.5 mr-3 h-4 w-4 text-blue-600 focus:ring-2 focus:ring-blue-500 focus:ring-offset-0 border-gray-600 bg-gray-900 cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed rounded"
                />
                <div className="flex-1 min-w-0">
                  <div className="flex items-center">
                    <FolderOpen className="h-4 w-4 text-gray-400 mr-2 flex-shrink-0" />
                    <span
                      className={`text-sm font-medium truncate ${
                        isSelected ? 'text-white' : 'text-gray-300'
                      }`}
                      title={op.name}
                    >
                      {op.name}
                    </span>
                  </div>
                  <p className="text-xs text-gray-500 mt-1">
                    {op.session_count} session{op.session_count !== 1 ? 's' : ''}
                  </p>
                </div>
              </label>
            );
          })}
        </div>

        {operations.length === 0 && !loading && (
          <div className="mt-4 p-3 bg-yellow-900/30 border border-yellow-700/50 rounded-md">
            <p className="text-sm text-yellow-200">
              No operations found. Create an operation first.
            </p>
          </div>
        )}

        {loading && (
          <div className="mt-4 p-3 bg-gray-800/50 border border-gray-700 rounded-md">
            <p className="text-sm text-gray-400">Loading operations...</p>
          </div>
        )}
      </div>
    </div>
  );
}

export default InsightsScopeSelector;


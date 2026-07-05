import { Loader2, Check, AlertCircle } from 'lucide-react';
import type { MigrationResult } from '../types/settings';

interface MigrationProgressProps {
  loading: boolean;
  result: MigrationResult | null;
  error: string | null;
}

export default function MigrationProgress({ loading, result, error }: MigrationProgressProps) {
  if (loading) {
    return (
      <div className="bg-gray-800 border border-gray-700 rounded-lg p-4">
        <div className="flex items-center text-blue-400 mb-2">
          <Loader2 className="h-5 w-5 mr-2 animate-spin" />
          <span className="font-medium">Migrating data...</span>
        </div>
        <div className="w-full bg-gray-700 rounded-full h-2 mt-3">
          <div className="bg-blue-600 h-2 rounded-full animate-pulse" style={{ width: '60%' }}></div>
        </div>
        <p className="text-sm text-gray-400 mt-2">This may take a few moments</p>
      </div>
    );
  }

  if (error) {
    return (
      <div className="bg-red-900/20 border border-red-700 rounded-lg p-4">
        <div className="flex items-start text-red-400">
          <AlertCircle className="h-5 w-5 mr-2 mt-0.5 flex-shrink-0" />
          <div>
            <p className="font-medium">Migration failed</p>
            <p className="text-sm text-red-300 mt-1">{error}</p>
          </div>
        </div>
      </div>
    );
  }

  if (result) {
    const hasErrors = result.errors.length > 0;
    return (
      <div className={`bg-gray-800 border ${hasErrors ? 'border-yellow-700' : 'border-green-700'} rounded-lg p-4`}>
        <div className="flex items-start">
          {hasErrors ? (
            <AlertCircle className="h-5 w-5 mr-2 mt-0.5 text-yellow-400 flex-shrink-0" />
          ) : (
            <Check className="h-5 w-5 mr-2 mt-0.5 text-green-400 flex-shrink-0" />
          )}
          <div className="flex-1">
            <p className={`font-medium ${hasErrors ? 'text-yellow-400' : 'text-green-400'}`}>
              Migration {hasErrors ? 'completed with warnings' : 'completed successfully'}
            </p>
            <div className="mt-2 text-sm text-gray-300 space-y-1">
              <p>Operations migrated: {result.operations_migrated}</p>
              <p>Sessions migrated: {result.sessions_migrated}</p>
              {hasErrors && (
                <div className="mt-2">
                  <p className="text-yellow-400 font-medium mb-1">Errors:</p>
                  <ul className="list-disc list-inside space-y-1 text-yellow-300">
                    {result.errors.map((err, idx) => (
                      <li key={idx} className="text-xs">{err}</li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          </div>
        </div>
      </div>
    );
  }

  return null;
}


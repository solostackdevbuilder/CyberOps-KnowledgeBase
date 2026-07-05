import { Check, X, Loader2 } from 'lucide-react';
import type { ConnectionTestResult } from '../types/settings';

interface ConnectionStatusProps {
  result: ConnectionTestResult | null;
  loading: boolean;
}

export default function ConnectionStatus({ result, loading }: ConnectionStatusProps) {
  if (loading) {
    return (
      <div className="flex items-center text-blue-400">
        <Loader2 className="h-4 w-4 mr-2 animate-spin" />
        <span className="text-sm">Testing connection...</span>
      </div>
    );
  }

  if (!result) {
    return null;
  }

  if (result.success) {
    return (
      <div className="flex items-center text-green-400">
        <Check className="h-4 w-4 mr-2" />
        <span className="text-sm">{result.message || 'Connected successfully'}</span>
      </div>
    );
  }

  return (
    <div className="flex items-start text-red-400">
      <X className="h-4 w-4 mr-2 mt-0.5 flex-shrink-0" />
      <span className="text-sm">{result.message || 'Connection failed'}</span>
    </div>
  );
}


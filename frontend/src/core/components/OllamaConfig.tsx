import { useState } from 'react';
import { RefreshCw, Loader2, AlertCircle } from 'lucide-react';
import type { LLMConfig } from '../types/settings';
import { getOllamaModels } from '../services/api';

interface OllamaConfigProps {
  config: LLMConfig;
  onChange: (config: LLMConfig) => void;
}

export default function OllamaConfig({ config, onChange }: OllamaConfigProps) {
  const [fetchingModels, setFetchingModels] = useState(false);
  const [availableModels, setAvailableModels] = useState<string[]>([]);
  const [fetchError, setFetchError] = useState<string | null>(null);

  const handleFetchModels = async () => {
    if (!config.endpoint) {
      setFetchError('Please enter an endpoint first');
      return;
    }

    setFetchingModels(true);
    setFetchError(null);
    try {
      const models = await getOllamaModels(config.endpoint);
      setAvailableModels(models);
      if (models.length > 0 && !config.model_name) {
        onChange({ ...config, model_name: models[0] });
      }
    } catch (err: any) {
      setFetchError(err.response?.data?.detail || err.message || 'Failed to fetch models');
      setAvailableModels([]);
    } finally {
      setFetchingModels(false);
    }
  };

  return (
    <div className="space-y-4">
      <div>
        <label className="block text-sm font-medium text-gray-300 mb-2">
          Ollama Endpoint <span className="text-red-400">*</span>
        </label>
        <input
          type="text"
          value={config.endpoint || ''}
          onChange={(e) => onChange({ ...config, endpoint: e.target.value })}
          placeholder="http://localhost:11434"
          className="w-full px-4 py-2 bg-gray-900 border border-gray-700 rounded-md text-white placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
        />
        <p className="text-xs text-gray-500 mt-1">
          Ollama can be running on a remote server
        </p>
      </div>
      <div>
        <div className="flex items-center justify-between mb-2">
          <label className="block text-sm font-medium text-gray-300">
            Model
          </label>
          <button
            type="button"
            onClick={handleFetchModels}
            disabled={fetchingModels || !config.endpoint}
            className="text-sm px-3 py-1 bg-gray-700 hover:bg-gray-600 text-white rounded-md transition-colors disabled:opacity-50 disabled:cursor-not-allowed flex items-center"
          >
            {fetchingModels ? (
              <>
                <Loader2 className="h-3 w-3 mr-1 animate-spin" />
                Fetching...
              </>
            ) : (
              <>
                <RefreshCw className="h-3 w-3 mr-1" />
                Fetch Available Models
              </>
            )}
          </button>
        </div>
        {availableModels.length > 0 ? (
          <select
            value={config.model_name || ''}
            onChange={(e) => onChange({ ...config, model_name: e.target.value })}
            className="w-full px-4 py-2 bg-gray-900 border border-gray-700 rounded-md text-white focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
          >
            <option value="">Select a model</option>
            {availableModels.map((model) => (
              <option key={model} value={model}>
                {model}
              </option>
            ))}
          </select>
        ) : (
          <input
            type="text"
            value={config.model_name || ''}
            onChange={(e) => onChange({ ...config, model_name: e.target.value })}
            placeholder="llama2, mistral, etc."
            className="w-full px-4 py-2 bg-gray-900 border border-gray-700 rounded-md text-white placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
          />
        )}
        {fetchError && (
          <div className="mt-2 flex items-start text-red-400 text-xs">
            <AlertCircle className="h-3 w-3 mr-1 mt-0.5 flex-shrink-0" />
            <span>{fetchError}</span>
          </div>
        )}
      </div>
    </div>
  );
}


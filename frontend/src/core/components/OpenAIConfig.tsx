import { ExternalLink } from 'lucide-react';
import type { LLMConfig } from '../types/settings';

interface OpenAIConfigProps {
  config: LLMConfig;
  onChange: (config: LLMConfig) => void;
}

const OPENAI_MODELS = [
  { value: 'gpt-4-turbo-preview', label: 'GPT-4 Turbo' },
  { value: 'gpt-4', label: 'GPT-4' },
  { value: 'gpt-3.5-turbo', label: 'GPT-3.5 Turbo' },
];

export default function OpenAIConfig({ config, onChange }: OpenAIConfigProps) {
  return (
    <div className="space-y-4">
      <div>
        <label className="block text-sm font-medium text-gray-300 mb-2">
          OpenAI API Key <span className="text-red-400">*</span>
        </label>
        <input
          type="password"
          value={config.api_key || ''}
          onChange={(e) => onChange({ ...config, api_key: e.target.value })}
          placeholder="sk-..."
          className="w-full px-4 py-2 bg-gray-900 border border-gray-700 rounded-md text-white placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
        />
        <p className="text-xs text-gray-500 mt-1">
          <a
            href="https://platform.openai.com/api-keys"
            target="_blank"
            rel="noopener noreferrer"
            className="text-blue-400 hover:text-blue-300 inline-flex items-center"
          >
            Get your API key <ExternalLink className="h-3 w-3 ml-1" />
          </a>
        </p>
      </div>
      <div>
        <label className="block text-sm font-medium text-gray-300 mb-2">
          Model
        </label>
        <select
          value={config.model_name || 'gpt-4-turbo-preview'}
          onChange={(e) => onChange({ ...config, model_name: e.target.value })}
          className="w-full px-4 py-2 bg-gray-900 border border-gray-700 rounded-md text-white focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
        >
          {OPENAI_MODELS.map((model) => (
            <option key={model.value} value={model.value}>
              {model.label}
            </option>
          ))}
        </select>
      </div>
      {config.endpoint && (
        <div>
          <label className="block text-sm font-medium text-gray-300 mb-2">
            Custom Endpoint (Optional)
          </label>
          <input
            type="text"
            value={config.endpoint || ''}
            onChange={(e) => onChange({ ...config, endpoint: e.target.value })}
            placeholder="https://api.openai.com/v1"
            className="w-full px-4 py-2 bg-gray-900 border border-gray-700 rounded-md text-white placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
          />
          <p className="text-xs text-gray-500 mt-1">
            For custom OpenAI-compatible endpoints
          </p>
        </div>
      )}
    </div>
  );
}


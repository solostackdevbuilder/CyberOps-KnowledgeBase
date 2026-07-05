import { ExternalLink } from 'lucide-react';
import type { LLMConfig } from '../types/settings';

interface ClaudeConfigProps {
  config: LLMConfig;
  onChange: (config: LLMConfig) => void;
}

const CLAUDE_MODELS = [
  { value: 'claude-3-5-sonnet-20241022', label: 'Claude 3.5 Sonnet (Latest)' },
  { value: 'claude-3-opus-20240229', label: 'Claude 3 Opus' },
  { value: 'claude-3-sonnet-20240229', label: 'Claude 3 Sonnet' },
  { value: 'claude-3-haiku-20240307', label: 'Claude 3 Haiku' },
];

export default function ClaudeConfig({ config, onChange }: ClaudeConfigProps) {
  return (
    <div className="space-y-4">
      <div>
        <label className="block text-sm font-medium text-gray-300 mb-2">
          Anthropic API Key <span className="text-red-400">*</span>
        </label>
        <input
          type="password"
          value={config.api_key || ''}
          onChange={(e) => onChange({ ...config, api_key: e.target.value })}
          placeholder="sk-ant-..."
          className="w-full px-4 py-2 bg-gray-900 border border-gray-700 rounded-md text-white placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
        />
        <p className="text-xs text-gray-500 mt-1">
          <a
            href="https://console.anthropic.com/"
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
          value={config.model_name || 'claude-3-5-sonnet-20241022'}
          onChange={(e) => onChange({ ...config, model_name: e.target.value })}
          className="w-full px-4 py-2 bg-gray-900 border border-gray-700 rounded-md text-white focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
        >
          {CLAUDE_MODELS.map((model) => (
            <option key={model.value} value={model.value}>
              {model.label}
            </option>
          ))}
        </select>
      </div>
    </div>
  );
}


import { useState } from 'react';
import { Zap, Loader2, CheckCircle2, XCircle, Info } from 'lucide-react';
import type { LLMProvider, LLMConfig, Settings } from '../types/settings';
import ClaudeConfig from './ClaudeConfig';
import OpenAIConfig from './OpenAIConfig';
import OllamaConfig from './OllamaConfig';
import ConnectionStatus from './ConnectionStatus';
import { testLLMConnection } from '../services/api';
import type { ConnectionTestResult } from '../types/settings';

interface LLMSettingsProps {
  settings: Settings;
  onChange: (settings: Settings) => void;
}

export default function LLMSettings({ settings, onChange }: LLMSettingsProps) {
  const [testing, setTesting] = useState(false);
  const [testResult, setTestResult] = useState<ConnectionTestResult | null>(null);

  const handleProviderChange = (provider: LLMProvider) => {
    const newConfig: LLMConfig = {
      provider,
      api_key: undefined,
      endpoint: provider === 'ollama' ? 'http://localhost:11434' : undefined,
      model_name: undefined,
    };

    onChange({
      ...settings,
      llm_provider: provider,
      llm_config: newConfig,
    });
    setTestResult(null);
  };

  const handleConfigChange = (config: LLMConfig) => {
    onChange({
      ...settings,
      llm_config: config,
    });
    setTestResult(null);
  };

  const handleTest = async () => {
    if (!settings.llm_config) {
      setTestResult({ success: false, message: 'LLM configuration is required' });
      return;
    }

    setTesting(true);
    setTestResult(null);
    try {
      const result = await testLLMConnection(settings.llm_config);
      setTestResult(result);
    } catch (err: any) {
      setTestResult({
        success: false,
        message: err.response?.data?.detail || err.message || 'Connection test failed',
      });
    } finally {
      setTesting(false);
    }
  };

  const renderConfigForm = () => {
    if (!settings.llm_config) {
      return null;
    }

    switch (settings.llm_provider) {
      case 'claude':
        return <ClaudeConfig config={settings.llm_config} onChange={handleConfigChange} />;
      case 'openai':
        return <OpenAIConfig config={settings.llm_config} onChange={handleConfigChange} />;
      case 'ollama':
        return <OllamaConfig config={settings.llm_config} onChange={handleConfigChange} />;
      default:
        return null;
    }
  };

  const getProviderDescription = (provider: LLMProvider) => {
    switch (provider) {
      case 'claude':
        return 'Anthropic\'s Claude models. Requires API key.';
      case 'openai':
        return 'OpenAI GPT models. Requires API key.';
      case 'ollama':
        return 'Self-hosted Ollama models. No API key required.';
      default:
        return '';
    }
  };

  const supportsVision = (provider: LLMProvider, modelName?: string): boolean => {
    if (!modelName) return false;
    const modelLower = modelName.toLowerCase();
    
    switch (provider) {
      case 'claude':
        // Claude Sonnet and Opus models support vision
        return modelLower.includes('sonnet') || modelLower.includes('opus');
      case 'openai':
        // GPT-4 Vision models support vision
        return modelLower.includes('vision') || modelLower.includes('gpt-4');
      case 'ollama':
        // Ollama vision models (llava, bakllava, etc.)
        return modelLower.includes('llava') || 
               modelLower.includes('vision') || 
               modelLower.includes('bakllava');
      default:
        return false;
    }
  };

  const getVisionSupportBadge = (provider: LLMProvider, modelName?: string) => {
    const supports = supportsVision(provider, modelName);
    return (
      <span
        className={`inline-flex items-center gap-1 px-2 py-0.5 text-xs rounded ${
          supports
            ? 'bg-green-900/50 text-green-300 border border-green-600'
            : 'bg-gray-700 text-gray-400 border border-gray-600'
        }`}
        title={supports 
          ? 'This model supports vision capabilities for screenshot text extraction'
          : 'This model does not support vision capabilities'}
      >
        {supports ? (
          <>
            <CheckCircle2 className="h-3 w-3" />
            Vision Supported
          </>
        ) : (
          <>
            <XCircle className="h-3 w-3" />
            No Vision Support
          </>
        )}
      </span>
    );
  };

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-xl font-semibold text-white mb-4">LLM Provider</h2>
        <p className="text-gray-400 mb-4">
          Choose which AI provider to use for querying your knowledge base.
        </p>

        <div className="mb-4 p-3 bg-blue-900/20 border border-blue-700 rounded-md">
          <div className="flex items-start gap-2">
            <Info className="h-4 w-4 text-blue-400 flex-shrink-0 mt-0.5" />
            <p className="text-sm text-blue-200">
              Vision support enables automatic text extraction from screenshots. Only certain models support this feature.
            </p>
          </div>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-6">
          <button
            type="button"
            onClick={() => handleProviderChange('claude')}
            className={`p-4 border-2 rounded-lg transition-colors text-left ${
              settings.llm_provider === 'claude'
                ? 'border-blue-500 bg-blue-500/10'
                : 'border-gray-700 bg-gray-800 hover:border-gray-600'
            }`}
          >
            <div className="flex items-center justify-between mb-2">
              <div className="flex items-center">
                <Zap className={`h-5 w-5 mr-2 ${settings.llm_provider === 'claude' ? 'text-blue-400' : 'text-gray-400'}`} />
                <span className={`font-medium ${settings.llm_provider === 'claude' ? 'text-white' : 'text-gray-300'}`}>
                  Claude
                </span>
              </div>
              {getVisionSupportBadge('claude', settings.llm_config?.model_name)}
            </div>
            <p className="text-sm text-gray-400">
              {getProviderDescription('claude')}
            </p>
          </button>

          <button
            type="button"
            onClick={() => handleProviderChange('openai')}
            className={`p-4 border-2 rounded-lg transition-colors text-left ${
              settings.llm_provider === 'openai'
                ? 'border-blue-500 bg-blue-500/10'
                : 'border-gray-700 bg-gray-800 hover:border-gray-600'
            }`}
          >
            <div className="flex items-center justify-between mb-2">
              <div className="flex items-center">
                <Zap className={`h-5 w-5 mr-2 ${settings.llm_provider === 'openai' ? 'text-blue-400' : 'text-gray-400'}`} />
                <span className={`font-medium ${settings.llm_provider === 'openai' ? 'text-white' : 'text-gray-300'}`}>
                  OpenAI
                </span>
              </div>
              {getVisionSupportBadge('openai', settings.llm_config?.model_name)}
            </div>
            <p className="text-sm text-gray-400">
              {getProviderDescription('openai')}
            </p>
            <p className="text-xs text-gray-500 mt-1">
              GPT-4 Vision models support vision. GPT-3.5 does not.
            </p>
          </button>

          <button
            type="button"
            onClick={() => handleProviderChange('ollama')}
            className={`p-4 border-2 rounded-lg transition-colors text-left ${
              settings.llm_provider === 'ollama'
                ? 'border-blue-500 bg-blue-500/10'
                : 'border-gray-700 bg-gray-800 hover:border-gray-600'
            }`}
          >
            <div className="flex items-center justify-between mb-2">
              <div className="flex items-center">
                <Zap className={`h-5 w-5 mr-2 ${settings.llm_provider === 'ollama' ? 'text-blue-400' : 'text-gray-400'}`} />
                <span className={`font-medium ${settings.llm_provider === 'ollama' ? 'text-white' : 'text-gray-300'}`}>
                  Ollama
                </span>
              </div>
              {getVisionSupportBadge('ollama', settings.llm_config?.model_name)}
            </div>
            <p className="text-sm text-gray-400">
              {getProviderDescription('ollama')}
            </p>
            <p className="text-xs text-gray-500 mt-1">
              LLaVA models support vision. Other models do not.
            </p>
          </button>
        </div>

        {settings.llm_config && (
          <div className="bg-gray-800 border border-gray-700 rounded-lg p-6">
            <h3 className="text-lg font-semibold text-white mb-4">
              {settings.llm_provider === 'claude' ? 'Claude' : settings.llm_provider === 'openai' ? 'OpenAI' : 'Ollama'} Configuration
            </h3>
            {renderConfigForm()}
            <div className="mt-6 flex items-center justify-between">
              <button
                type="button"
                onClick={handleTest}
                disabled={testing || !settings.llm_config}
                className="px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-md transition-colors disabled:opacity-50 disabled:cursor-not-allowed flex items-center"
              >
                {testing ? (
                  <>
                    <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                    Testing...
                  </>
                ) : (
                  'Test Connection'
                )}
              </button>
              <ConnectionStatus result={testResult} loading={testing} />
            </div>
          </div>
        )}
      </div>
    </div>
  );
}


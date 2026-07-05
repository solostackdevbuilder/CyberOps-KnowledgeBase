import { useState, useEffect } from 'react';
import { Settings as SettingsIcon, Save, RotateCcw, Loader2, Check, AlertCircle } from 'lucide-react';
import { getSettings, updateSettings } from '../services/api';
import type { Settings as SettingsType } from '../types/settings';
import StorageSettings from './StorageSettings';
import LLMSettings from './LLMSettings';
import WebhookSettings from './WebhookSettings';

export default function Settings() {
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState(false);
  const [settings, setSettings] = useState<SettingsType | null>(null);
  const [originalSettings, setOriginalSettings] = useState<SettingsType | null>(null);
  const [lastSaved, setLastSaved] = useState<Date | null>(null);

  useEffect(() => {
    loadSettings();
  }, []);

  const loadSettings = async () => {
    try {
      setLoading(true);
      setError(null);
      const data = await getSettings();
      setSettings(data);
      setOriginalSettings(JSON.parse(JSON.stringify(data))); // Deep copy
    } catch (err: any) {
      setError(err.response?.data?.detail || err.message || 'Failed to load settings');
    } finally {
      setLoading(false);
    }
  };

  const handleSave = async () => {
    if (!settings) return;

    // Validate settings
    if (settings.storage_backend !== 'json' && !settings.database_config) {
      setError('Database configuration is required for selected storage backend');
      return;
    }

    if (!settings.llm_config) {
      setError('LLM configuration is required');
      return;
    }

    if ((settings.llm_provider === 'claude' || settings.llm_provider === 'openai') && !settings.llm_config.api_key) {
      setError('API key is required for selected LLM provider');
      return;
    }

    if (settings.llm_provider === 'ollama' && !settings.llm_config.endpoint) {
      setError('Endpoint is required for Ollama');
      return;
    }

    setSaving(true);
    setError(null);
    setSuccess(false);

    try {
      const updated = await updateSettings(settings);
      setSettings(updated);
      setOriginalSettings(JSON.parse(JSON.stringify(updated)));
      setSuccess(true);
      setLastSaved(new Date());
      setTimeout(() => setSuccess(false), 3000);
    } catch (err: any) {
      setError(err.response?.data?.detail || err.message || 'Failed to save settings');
    } finally {
      setSaving(false);
    }
  };

  const handleReset = () => {
    if (!originalSettings) return;
    if (window.confirm('Are you sure you want to discard all unsaved changes?')) {
      setSettings(JSON.parse(JSON.stringify(originalSettings)));
      setError(null);
      setSuccess(false);
    }
  };

  const hasChanges = () => {
    if (!settings || !originalSettings) return false;
    return JSON.stringify(settings) !== JSON.stringify(originalSettings);
  };

  if (loading) {
    return (
      <div className="flex justify-center items-center min-h-[400px]">
        <Loader2 className="h-8 w-8 animate-spin text-blue-500" />
      </div>
    );
  }

  if (!settings) {
    return (
      <div className="bg-red-900/20 border border-red-700 rounded-lg p-6">
        <div className="flex items-start text-red-400">
          <AlertCircle className="h-6 w-6 mr-3 mt-0.5 flex-shrink-0" />
          <div>
            <p className="font-medium">Failed to load settings</p>
            <p className="text-sm text-red-300 mt-1">{error || 'Unknown error'}</p>
            <button
              onClick={loadSettings}
              className="mt-4 px-4 py-2 bg-red-600 hover:bg-red-700 text-white rounded-md transition-colors"
            >
              Retry
            </button>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="max-w-6xl mx-auto">
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-3xl font-bold text-white flex items-center">
          <SettingsIcon className="h-8 w-8 mr-3" />
          Settings
        </h1>
        <div className="flex items-center gap-4">
          {lastSaved && (
            <span className="text-sm text-gray-400">
              Last saved: {lastSaved.toLocaleTimeString()}
            </span>
          )}
          {hasChanges() && (
            <button
              onClick={handleReset}
              className="px-4 py-2 bg-gray-700 hover:bg-gray-600 text-white rounded-md transition-colors flex items-center"
            >
              <RotateCcw className="h-4 w-4 mr-2" />
              Reset
            </button>
          )}
          <button
            onClick={handleSave}
            disabled={saving || !hasChanges()}
            className="px-6 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-md transition-colors disabled:opacity-50 disabled:cursor-not-allowed flex items-center"
          >
            {saving ? (
              <>
                <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                Saving...
              </>
            ) : (
              <>
                <Save className="h-4 w-4 mr-2" />
                Save Settings
              </>
            )}
          </button>
        </div>
      </div>

      {error && (
        <div className="mb-6 p-4 bg-red-900/50 border border-red-700 rounded-md text-red-200">
          {error}
        </div>
      )}

      {success && (
        <div className="mb-6 p-4 bg-green-900/50 border border-green-700 rounded-md text-green-200 flex items-center">
          <Check className="h-5 w-5 mr-2" />
          Settings saved successfully
        </div>
      )}

      <div className="space-y-8">
        <div className="bg-gray-800 border border-gray-700 rounded-lg p-6">
          <StorageSettings settings={settings} onChange={setSettings} />
        </div>

        <div className="bg-gray-800 border border-gray-700 rounded-lg p-6">
          <LLMSettings settings={settings} onChange={setSettings} />
        </div>

        <div className="bg-gray-800 border border-gray-700 rounded-lg p-6">
          <WebhookSettings settings={settings} onChange={setSettings} />
        </div>
      </div>
    </div>
  );
}


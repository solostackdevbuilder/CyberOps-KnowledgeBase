import { useState } from 'react';
import { Webhook, Info, Copy, Check, Loader2, Send } from 'lucide-react';
import type { WebhookConfig, Settings } from '../types/settings';
import { testWebhook } from '../services/api';
import type { ConnectionTestResult } from '../types/settings';

interface WebhookSettingsProps {
  settings: Settings;
  onChange: (settings: Settings) => void;
}

export default function WebhookSettings({ settings, onChange }: WebhookSettingsProps) {
  const [copied, setCopied] = useState<string | null>(null);
  const [testing, setTesting] = useState(false);
  const [testResult, setTestResult] = useState<ConnectionTestResult | null>(null);

  const handleConfigChange = (updates: Partial<WebhookConfig>, preserveEmpty: boolean = false) => {
    // Get current webhook_config from settings, ensuring it exists
    const currentConfig = settings.webhook_config || {
      teams_webhook_url: undefined,
      slack_webhook_url: undefined,
      enabled: false,
    };
    
    // Apply updates - preserve empty strings while typing
    const newConfig: WebhookConfig = {
      teams_webhook_url: currentConfig.teams_webhook_url,
      slack_webhook_url: currentConfig.slack_webhook_url,
      enabled: currentConfig.enabled,
      ...updates,
    };
    
    // Only convert empty strings to undefined if preserveEmpty is false (i.e., on blur or save)
    if (!preserveEmpty) {
      if ('teams_webhook_url' in updates) {
        newConfig.teams_webhook_url = updates.teams_webhook_url === '' ? undefined : updates.teams_webhook_url;
      }
      if ('slack_webhook_url' in updates) {
        newConfig.slack_webhook_url = updates.slack_webhook_url === '' ? undefined : updates.slack_webhook_url;
      }
    }
    
    onChange({
      ...settings,
      webhook_config: newConfig,
    });
  };

  const handleCopy = (text: string, type: string) => {
    navigator.clipboard.writeText(text);
    setCopied(type);
    setTimeout(() => setCopied(null), 2000);
  };

  const getSampleTeamsWebhook = () => {
    return 'https://outlook.office.com/webhook/YOUR_WEBHOOK_ID@YOUR_TENANT_ID/IncomingWebhook/YOUR_KEY/YOUR_KEY';
  };

  const handleTestWebhook = async (service: 'teams' | 'slack' = 'teams') => {
    setTesting(true);
    setTestResult(null);
    try {
      const result = await testWebhook(service);
      setTestResult(result);
    } catch (err: any) {
      setTestResult({
        success: false,
        message: err.response?.data?.detail || err.message || 'Failed to test webhook',
      });
    } finally {
      setTesting(false);
    }
  };

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-xl font-semibold text-white mb-4 flex items-center">
          <Webhook className="h-6 w-6 mr-2" />
          Webhook Integrations
        </h2>
        <p className="text-gray-400 mb-4">
          Configure webhooks to receive notifications in Microsoft Teams or Slack when events occur in your knowledge base.
        </p>

        <div className="mb-4 p-3 bg-blue-900/20 border border-blue-700 rounded-md">
          <div className="flex items-start gap-2">
            <Info className="h-4 w-4 text-blue-400 flex-shrink-0 mt-0.5" />
            <div className="text-sm text-blue-200">
              <p className="mb-2">
                Webhooks allow external systems to receive real-time notifications about events in your knowledge base.
              </p>
              <p>
                To get a Teams webhook URL, go to your Teams channel → Connectors → Incoming Webhook → Configure.
              </p>
            </div>
          </div>
        </div>

        {/* Enable/Disable Toggle */}
        <div className="mb-6">
          <label className="flex items-center gap-3 cursor-pointer">
            <input
              type="checkbox"
              checked={settings.webhook_config?.enabled || false}
              onChange={(e) => handleConfigChange({ enabled: e.target.checked })}
              className="w-5 h-5 rounded border-gray-600 bg-gray-700 text-blue-600 focus:ring-blue-500 focus:ring-offset-gray-800"
            />
            <span className="text-white font-medium">Enable Webhook Notifications</span>
          </label>
          <p className="text-sm text-gray-400 mt-1 ml-8">
            When enabled, webhooks will be sent to configured URLs when events occur.
          </p>
        </div>

        {/* Teams Webhook */}
        <div className="bg-gray-800 border border-gray-700 rounded-lg p-6 mb-4">
          <h3 className="text-lg font-semibold text-white mb-4">Microsoft Teams</h3>
          
          <div className="mb-4">
            <label className="block text-sm font-medium text-gray-300 mb-2">
              Teams Webhook URL
            </label>
            <div className="flex gap-2">
              <input
                type="text"
                value={settings.webhook_config?.teams_webhook_url || ''}
                onChange={(e) => handleConfigChange({ teams_webhook_url: e.target.value }, true)}
                onBlur={(e) => {
                  // Trim and save on blur - convert empty to undefined
                  const trimmed = e.target.value.trim();
                  handleConfigChange({ teams_webhook_url: trimmed || undefined }, false);
                }}
                placeholder={getSampleTeamsWebhook()}
                className="flex-1 px-4 py-2 bg-gray-900 border border-gray-600 rounded-md text-white placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
              />
              <button
                type="button"
                onClick={() => handleCopy(getSampleTeamsWebhook(), 'teams-sample')}
                className="px-4 py-2 bg-gray-700 hover:bg-gray-600 text-white rounded-md transition-colors flex items-center gap-2"
                title="Copy sample webhook URL"
              >
                {copied === 'teams-sample' ? (
                  <>
                    <Check className="h-4 w-4" />
                    Copied
                  </>
                ) : (
                  <>
                    <Copy className="h-4 w-4" />
                    Sample
                  </>
                )}
              </button>
            </div>
            <p className="text-xs text-gray-500 mt-2">
              Sample URL format: {getSampleTeamsWebhook()}
            </p>
            <div className="mt-4 flex items-center gap-4">
              <button
                type="button"
                onClick={() => handleTestWebhook('teams')}
                disabled={testing || !settings.webhook_config?.teams_webhook_url || !settings.webhook_config?.enabled}
                className="px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-md transition-colors disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2"
              >
                {testing ? (
                  <>
                    <Loader2 className="h-4 w-4 animate-spin" />
                    Testing...
                  </>
                ) : (
                  <>
                    <Send className="h-4 w-4" />
                    Test Teams Webhook
                  </>
                )}
              </button>
              {testResult && (
                <div className={`flex items-center gap-2 text-sm ${testResult.success ? 'text-green-400' : 'text-red-400'}`}>
                  {testResult.success ? (
                    <>
                      <Check className="h-4 w-4" />
                      <span>{testResult.message}</span>
                    </>
                  ) : (
                    <>
                      <Info className="h-4 w-4" />
                      <span>{testResult.message}</span>
                    </>
                  )}
                </div>
              )}
            </div>
          </div>
        </div>

        {/* Slack Webhook */}
        <div className="bg-gray-800 border border-gray-700 rounded-lg p-6">
          <h3 className="text-lg font-semibold text-white mb-4">Slack</h3>
          
          <div className="mb-4">
            <label className="block text-sm font-medium text-gray-300 mb-2">
              Slack Webhook URL
            </label>
            <input
              type="text"
              value={settings.webhook_config?.slack_webhook_url || ''}
              onChange={(e) => handleConfigChange({ slack_webhook_url: e.target.value }, true)}
              onBlur={(e) => {
                // Trim and save on blur - convert empty to undefined
                const trimmed = e.target.value.trim();
                handleConfigChange({ slack_webhook_url: trimmed || undefined }, false);
              }}
              placeholder="https://hooks.slack.com/services/YOUR/WEBHOOK/URL"
              className="w-full px-4 py-2 bg-gray-900 border border-gray-600 rounded-md text-white placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
            />
            <p className="text-xs text-gray-500 mt-2">
              To get a Slack webhook URL, go to your Slack workspace → Apps → Incoming Webhooks → Add to Slack.
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}


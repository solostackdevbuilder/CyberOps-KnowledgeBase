import { useState } from 'react';
import { Database, Loader2 } from 'lucide-react';
import type { DatabaseConfig } from '../types/settings';
import ConnectionStatus from './ConnectionStatus';
import type { ConnectionTestResult } from '../types/settings';

interface DatabaseConfigProps {
  backend: 'mongodb' | 'postgresql';
  config: DatabaseConfig;
  onChange: (config: DatabaseConfig) => void;
  onTest: (config: DatabaseConfig) => Promise<ConnectionTestResult>;
}

export default function DatabaseConfigComponent({
  backend,
  config,
  onChange,
  onTest,
}: DatabaseConfigProps) {
  const [useConnectionString, setUseConnectionString] = useState(
    !!config.connection_string && !config.host
  );
  const [testing, setTesting] = useState(false);
  const [testResult, setTestResult] = useState<ConnectionTestResult | null>(null);

  const handleTest = async () => {
    setTesting(true);
    setTestResult(null);
    try {
      const result = await onTest(config);
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

  const updateConfig = (updates: Partial<DatabaseConfig>) => {
    onChange({ ...config, ...updates });
    setTestResult(null); // Clear test result when config changes
  };

  return (
    <div className="bg-gray-800 border border-gray-700 rounded-lg p-6">
      <div className="flex items-center mb-4">
        <Database className="h-5 w-5 mr-2 text-blue-400" />
        <h3 className="text-lg font-semibold text-white">
          {backend === 'mongodb' ? 'MongoDB' : 'PostgreSQL'} Configuration
        </h3>
      </div>

      {backend === 'mongodb' && (
        <div className="mb-4">
          <label className="flex items-center text-sm text-gray-300 mb-2">
            <input
              type="checkbox"
              checked={useConnectionString}
              onChange={(e) => {
                setUseConnectionString(e.target.checked);
                if (e.target.checked) {
                  updateConfig({ host: undefined, port: undefined, database_name: undefined, username: undefined, password: undefined });
                } else {
                  updateConfig({ connection_string: undefined });
                }
              }}
              className="mr-2 rounded border-gray-600 bg-gray-700 text-blue-600 focus:ring-blue-500"
            />
            Use connection string
          </label>
        </div>
      )}

      {useConnectionString && backend === 'mongodb' ? (
        <div className="mb-4">
          <label className="block text-sm font-medium text-gray-300 mb-2">
            Connection String
          </label>
          <input
            type="text"
            value={config.connection_string || ''}
            onChange={(e) => updateConfig({ connection_string: e.target.value })}
            placeholder="mongodb://username:password@host:port/database"
            className="w-full px-4 py-2 bg-gray-900 border border-gray-700 rounded-md text-white placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
          />
          <p className="text-xs text-gray-500 mt-1">
            Example: mongodb://user:pass@localhost:27017/mydb
          </p>
        </div>
      ) : (
        <div className="space-y-4">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium text-gray-300 mb-2">
                Host
              </label>
              <input
                type="text"
                value={config.host || ''}
                onChange={(e) => updateConfig({ host: e.target.value })}
                placeholder="localhost"
                className="w-full px-4 py-2 bg-gray-900 border border-gray-700 rounded-md text-white placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-300 mb-2">
                Port
              </label>
              <input
                type="number"
                value={config.port || ''}
                onChange={(e) => updateConfig({ port: e.target.value ? parseInt(e.target.value) : undefined })}
                placeholder={backend === 'mongodb' ? '27017' : '5432'}
                className="w-full px-4 py-2 bg-gray-900 border border-gray-700 rounded-md text-white placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
              />
            </div>
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-300 mb-2">
              Database Name
            </label>
            <input
              type="text"
              value={config.database_name || ''}
              onChange={(e) => updateConfig({ database_name: e.target.value })}
              placeholder="redteam_kb"
              className="w-full px-4 py-2 bg-gray-900 border border-gray-700 rounded-md text-white placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
            />
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium text-gray-300 mb-2">
                Username
              </label>
              <input
                type="text"
                value={config.username || ''}
                onChange={(e) => updateConfig({ username: e.target.value })}
                placeholder="username"
                className="w-full px-4 py-2 bg-gray-900 border border-gray-700 rounded-md text-white placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-300 mb-2">
                Password
              </label>
              <input
                type="password"
                value={config.password || ''}
                onChange={(e) => updateConfig({ password: e.target.value })}
                placeholder="password"
                className="w-full px-4 py-2 bg-gray-900 border border-gray-700 rounded-md text-white placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
              />
            </div>
          </div>
          {backend === 'postgresql' && (
            <div className="flex items-center">
              <input
                type="checkbox"
                id="use-ssl"
                className="mr-2 rounded border-gray-600 bg-gray-700 text-blue-600 focus:ring-blue-500"
              />
              <label htmlFor="use-ssl" className="text-sm text-gray-300">
                Use SSL
              </label>
            </div>
          )}
        </div>
      )}

      <div className="mt-6 flex items-center justify-between">
        <button
          type="button"
          onClick={handleTest}
          disabled={testing || (!config.connection_string && (!config.host || !config.database_name))}
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
  );
}


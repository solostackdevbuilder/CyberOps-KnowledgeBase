import { useState } from 'react';
import { Database, FileText, AlertCircle } from 'lucide-react';
import type { StorageBackend, DatabaseConfig, Settings } from '../types/settings';
import DatabaseConfigComponent from './DatabaseConfig';
import MigrationProgress from './MigrationProgress';
import { testDatabaseConnection, migrateData } from '../services/api';
import type { ConnectionTestResult, MigrationResult } from '../types/settings';

interface StorageSettingsProps {
  settings: Settings;
  onChange: (settings: Settings) => void;
}

export default function StorageSettings({ settings, onChange }: StorageSettingsProps) {
  const [migrating, setMigrating] = useState(false);
  const [migrationResult, setMigrationResult] = useState<MigrationResult | null>(null);
  const [migrationError, setMigrationError] = useState<string | null>(null);
  const [previousBackend, setPreviousBackend] = useState<StorageBackend>(settings.storage_backend);

  const handleBackendChange = (backend: StorageBackend) => {
    const newSettings: Settings = {
      ...settings,
      storage_backend: backend,
    };

    if (backend === 'json') {
      newSettings.database_config = undefined;
    } else if (!settings.database_config) {
      newSettings.database_config = {
        host: '',
        port: backend === 'mongodb' ? 27017 : 5432,
        database_name: '',
        username: '',
        password: '',
      };
    }

    setPreviousBackend(settings.storage_backend);
    onChange(newSettings);
    setMigrationResult(null);
    setMigrationError(null);
  };

  const handleDatabaseConfigChange = (config: DatabaseConfig) => {
    onChange({
      ...settings,
      database_config: config,
    });
  };

  const handleTestConnection = async (config: DatabaseConfig): Promise<ConnectionTestResult> => {
    return await testDatabaseConnection(config);
  };

  const handleMigrate = async () => {
    if (!settings.database_config) {
      setMigrationError('Database configuration is required');
      return;
    }

    if (
      !window.confirm(
        `This will migrate all operations and sessions from JSON storage to ${settings.storage_backend.toUpperCase()}. Continue?`
      )
    ) {
      return;
    }

    setMigrating(true);
    setMigrationError(null);
    setMigrationResult(null);

    try {
      const result = await migrateData(
        settings.storage_backend as 'mongodb' | 'postgresql',
        settings.database_config
      );
      setMigrationResult(result);
    } catch (err: any) {
      setMigrationError(err.response?.data?.detail || err.message || 'Migration failed');
    } finally {
      setMigrating(false);
    }
  };

  const showMigrationButton =
    previousBackend === 'json' &&
    (settings.storage_backend === 'mongodb' || settings.storage_backend === 'postgresql') &&
    settings.database_config &&
    settings.database_config.host &&
    settings.database_config.database_name;

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-xl font-semibold text-white mb-4">Storage Backend</h2>
        <p className="text-gray-400 mb-4">
          Choose where your data will be stored. Switching backends will change where data is stored.
        </p>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-6">
          <button
            type="button"
            onClick={() => handleBackendChange('json')}
            className={`p-4 border-2 rounded-lg transition-colors text-left ${
              settings.storage_backend === 'json'
                ? 'border-blue-500 bg-blue-500/10'
                : 'border-gray-700 bg-gray-800 hover:border-gray-600'
            }`}
          >
            <div className="flex items-center mb-2">
              <FileText className={`h-5 w-5 mr-2 ${settings.storage_backend === 'json' ? 'text-blue-400' : 'text-gray-400'}`} />
              <span className={`font-medium ${settings.storage_backend === 'json' ? 'text-white' : 'text-gray-300'}`}>
                JSON Files
              </span>
            </div>
            <p className="text-sm text-gray-400">
              Local file storage. Simple and requires no setup.
            </p>
          </button>

          <button
            type="button"
            onClick={() => handleBackendChange('mongodb')}
            className={`p-4 border-2 rounded-lg transition-colors text-left ${
              settings.storage_backend === 'mongodb'
                ? 'border-blue-500 bg-blue-500/10'
                : 'border-gray-700 bg-gray-800 hover:border-gray-600'
            }`}
          >
            <div className="flex items-center mb-2">
              <Database className={`h-5 w-5 mr-2 ${settings.storage_backend === 'mongodb' ? 'text-blue-400' : 'text-gray-400'}`} />
              <span className={`font-medium ${settings.storage_backend === 'mongodb' ? 'text-white' : 'text-gray-300'}`}>
                MongoDB
              </span>
            </div>
            <p className="text-sm text-gray-400">
              NoSQL database. Great for scalability.
            </p>
          </button>

          <button
            type="button"
            onClick={() => handleBackendChange('postgresql')}
            className={`p-4 border-2 rounded-lg transition-colors text-left ${
              settings.storage_backend === 'postgresql'
                ? 'border-blue-500 bg-blue-500/10'
                : 'border-gray-700 bg-gray-800 hover:border-gray-600'
            }`}
          >
            <div className="flex items-center mb-2">
              <Database className={`h-5 w-5 mr-2 ${settings.storage_backend === 'postgresql' ? 'text-blue-400' : 'text-gray-400'}`} />
              <span className={`font-medium ${settings.storage_backend === 'postgresql' ? 'text-white' : 'text-gray-300'}`}>
                PostgreSQL
              </span>
            </div>
            <p className="text-sm text-gray-400">
              Relational database. Robust and reliable.
            </p>
          </button>
        </div>

        {settings.storage_backend === 'json' && (
          <div className="bg-blue-900/20 border border-blue-700 rounded-lg p-4 flex items-start">
            <AlertCircle className="h-5 w-5 text-blue-400 mr-3 mt-0.5 flex-shrink-0" />
            <div>
              <p className="text-blue-300 font-medium">Using local file storage</p>
              <p className="text-sm text-blue-400/80 mt-1">
                Data is stored in JSON files in the backend data directory.
              </p>
            </div>
          </div>
        )}

        {(settings.storage_backend === 'mongodb' || settings.storage_backend === 'postgresql') && (
          <>
            <DatabaseConfigComponent
              backend={settings.storage_backend}
              config={settings.database_config || {}}
              onChange={handleDatabaseConfigChange}
              onTest={handleTestConnection}
            />

            {showMigrationButton && (
              <div className="mt-4">
                <button
                  type="button"
                  onClick={handleMigrate}
                  disabled={migrating}
                  className="px-6 py-2 bg-green-600 hover:bg-green-700 text-white rounded-md transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  Migrate Data from JSON
                </button>
                <MigrationProgress
                  loading={migrating}
                  result={migrationResult}
                  error={migrationError}
                />
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}


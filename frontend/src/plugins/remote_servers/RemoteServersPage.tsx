import { useState, useEffect } from 'react';
import {
  Server, Plus, Loader2, CheckCircle, XCircle, Wifi, WifiOff,
  Trash2, RefreshCw, Search, Shield, Terminal, Edit2, X,
  AlertTriangle, Eye, EyeOff, Key, ChevronDown, ChevronUp,
} from 'lucide-react';

// ============================================================================
// Types
// ============================================================================

interface ServerInfo {
  id: string;
  name: string;
  host: string;
  port: number;
  username: string;
  auth_method: string;
  tags: string[];
  notes: string | null;
  status: string;
  last_seen: string | null;
  installed_tools: string[];
  system_info: { uname?: string; hostname?: string; uptime?: string } | null;
  added_at: string;
}

interface TestResult {
  server_id: string;
  status: string;
  message: string;
  latency_ms: number | null;
  system_info: any;
}

interface ToolScanResult {
  server_id: string;
  tools_found: string[];
  tools_missing: string[];
  details: Record<string, string>;
}

// ============================================================================
// Add/Edit Server Modal
// ============================================================================

function ServerFormModal({
  server,
  onClose,
  onSave,
}: {
  server: ServerInfo | null;
  onClose: () => void;
  onSave: () => void;
}) {
  const isEdit = !!server;
  const [name, setName] = useState(server?.name || '');
  const [host, setHost] = useState(server?.host || '');
  const [port, setPort] = useState(server?.port || 22);
  const [username, setUsername] = useState(server?.username || '');
  const [authMethod, setAuthMethod] = useState(server?.auth_method || 'password');
  const [password, setPassword] = useState('');
  const [privateKey, setPrivateKey] = useState('');
  const [passphrase, setPassphrase] = useState('');
  const [tags, setTags] = useState(server?.tags?.join(', ') || '');
  const [notes, setNotes] = useState(server?.notes || '');
  const [showPassword, setShowPassword] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!name.trim() || !host.trim() || !username.trim()) {
      setError('Name, host, and username are required');
      return;
    }
    if (authMethod === 'password' && !password && !isEdit) {
      setError('Password is required');
      return;
    }
    if (authMethod === 'key' && !privateKey && !isEdit) {
      setError('Private key is required');
      return;
    }

    setSaving(true);
    setError(null);

    const body: any = {
      name: name.trim(),
      credentials: {
        host: host.trim(),
        port,
        username: username.trim(),
        auth_method: authMethod,
      },
      tags: tags.split(',').map(t => t.trim()).filter(Boolean),
      notes: notes.trim() || null,
    };

    if (authMethod === 'password' && password) {
      body.credentials.password = password;
    } else if (authMethod === 'key' && privateKey) {
      body.credentials.private_key = privateKey;
      if (passphrase) body.credentials.passphrase = passphrase;
    }

    try {
      const url = isEdit
        ? `/api/plugins/remote_servers/servers/${server.id}`
        : '/api/plugins/remote_servers/servers';
      const res = await fetch(url, {
        method: isEdit ? 'PUT' : 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });
      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        throw new Error(data.detail || `Failed (${res.status})`);
      }
      onSave();
    } catch (err: any) {
      setError(err.message || 'Failed to save server');
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50 p-4">
      <div className="bg-gray-800 border border-gray-700 rounded-xl w-full max-w-lg max-h-[90vh] overflow-y-auto">
        <div className="flex items-center justify-between p-5 border-b border-gray-700">
          <h2 className="text-lg font-semibold text-white flex items-center">
            <Server className="h-5 w-5 mr-2 text-cyan-400" />
            {isEdit ? 'Edit Server' : 'Add Remote Server'}
          </h2>
          <button onClick={onClose} className="text-gray-400 hover:text-white">
            <X className="h-5 w-5" />
          </button>
        </div>

        <form onSubmit={handleSubmit} className="p-5 space-y-4">
          {error && (
            <div className="p-3 bg-red-900/30 border border-red-800 rounded-lg text-sm text-red-300">
              {error}
            </div>
          )}

          {/* Name */}
          <div>
            <label className="block text-xs text-gray-400 mb-1">Server Name</label>
            <input
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="e.g., Cracking Rig 1"
              className="w-full bg-gray-900 border border-gray-600 rounded-lg px-3 py-2 text-sm text-white placeholder-gray-500 focus:outline-none focus:border-cyan-500"
            />
          </div>

          {/* Host + Port */}
          <div className="grid grid-cols-3 gap-3">
            <div className="col-span-2">
              <label className="block text-xs text-gray-400 mb-1">Host / IP</label>
              <input
                value={host}
                onChange={(e) => setHost(e.target.value)}
                placeholder="192.168.1.100"
                className="w-full bg-gray-900 border border-gray-600 rounded-lg px-3 py-2 text-sm text-white placeholder-gray-500 focus:outline-none focus:border-cyan-500"
              />
            </div>
            <div>
              <label className="block text-xs text-gray-400 mb-1">Port</label>
              <input
                type="number"
                value={port}
                onChange={(e) => setPort(parseInt(e.target.value) || 22)}
                className="w-full bg-gray-900 border border-gray-600 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-cyan-500"
              />
            </div>
          </div>

          {/* Username */}
          <div>
            <label className="block text-xs text-gray-400 mb-1">Username</label>
            <input
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              placeholder="root"
              className="w-full bg-gray-900 border border-gray-600 rounded-lg px-3 py-2 text-sm text-white placeholder-gray-500 focus:outline-none focus:border-cyan-500"
            />
          </div>

          {/* Auth Method */}
          <div>
            <label className="block text-xs text-gray-400 mb-1">Authentication</label>
            <div className="flex gap-2">
              <button
                type="button"
                onClick={() => setAuthMethod('password')}
                className={`flex-1 px-3 py-2 rounded-lg border text-sm transition-colors ${
                  authMethod === 'password'
                    ? 'bg-cyan-900/40 border-cyan-600 text-white'
                    : 'bg-gray-900 border-gray-700 text-gray-400 hover:border-gray-500'
                }`}
              >
                <Shield className="h-4 w-4 inline mr-1.5 -mt-0.5" />
                Password
              </button>
              <button
                type="button"
                onClick={() => setAuthMethod('key')}
                className={`flex-1 px-3 py-2 rounded-lg border text-sm transition-colors ${
                  authMethod === 'key'
                    ? 'bg-cyan-900/40 border-cyan-600 text-white'
                    : 'bg-gray-900 border-gray-700 text-gray-400 hover:border-gray-500'
                }`}
              >
                <Key className="h-4 w-4 inline mr-1.5 -mt-0.5" />
                SSH Key
              </button>
            </div>
          </div>

          {/* Password or Key */}
          {authMethod === 'password' ? (
            <div>
              <label className="block text-xs text-gray-400 mb-1">
                Password {isEdit && <span className="text-gray-600">(leave blank to keep current)</span>}
              </label>
              <div className="relative">
                <input
                  type={showPassword ? 'text' : 'password'}
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder={isEdit ? '********' : 'Enter password'}
                  className="w-full bg-gray-900 border border-gray-600 rounded-lg px-3 py-2 pr-10 text-sm text-white placeholder-gray-500 focus:outline-none focus:border-cyan-500"
                />
                <button
                  type="button"
                  onClick={() => setShowPassword(!showPassword)}
                  className="absolute right-2 top-1/2 -translate-y-1/2 text-gray-500 hover:text-gray-300"
                >
                  {showPassword ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                </button>
              </div>
            </div>
          ) : (
            <>
              <div>
                <label className="block text-xs text-gray-400 mb-1">
                  Private Key {isEdit && <span className="text-gray-600">(leave blank to keep current)</span>}
                </label>
                <textarea
                  value={privateKey}
                  onChange={(e) => setPrivateKey(e.target.value)}
                  placeholder="-----BEGIN OPENSSH PRIVATE KEY-----&#10;..."
                  rows={4}
                  className="w-full bg-gray-900 border border-gray-600 rounded-lg px-3 py-2 text-sm text-white font-mono placeholder-gray-500 focus:outline-none focus:border-cyan-500 resize-none"
                />
              </div>
              <div>
                <label className="block text-xs text-gray-400 mb-1">Key Passphrase (optional)</label>
                <input
                  type="password"
                  value={passphrase}
                  onChange={(e) => setPassphrase(e.target.value)}
                  placeholder="Leave empty if key has no passphrase"
                  className="w-full bg-gray-900 border border-gray-600 rounded-lg px-3 py-2 text-sm text-white placeholder-gray-500 focus:outline-none focus:border-cyan-500"
                />
              </div>
            </>
          )}

          {/* Tags */}
          <div>
            <label className="block text-xs text-gray-400 mb-1">Tags (comma-separated)</label>
            <input
              value={tags}
              onChange={(e) => setTags(e.target.value)}
              placeholder="gpu, cracking, kali"
              className="w-full bg-gray-900 border border-gray-600 rounded-lg px-3 py-2 text-sm text-white placeholder-gray-500 focus:outline-none focus:border-cyan-500"
            />
          </div>

          {/* Notes */}
          <div>
            <label className="block text-xs text-gray-400 mb-1">Notes (optional)</label>
            <textarea
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              placeholder="e.g., 4x RTX 4090 rig in the lab"
              rows={2}
              className="w-full bg-gray-900 border border-gray-600 rounded-lg px-3 py-2 text-sm text-white placeholder-gray-500 focus:outline-none focus:border-cyan-500 resize-none"
            />
          </div>

          {/* Actions */}
          <div className="flex justify-end gap-3 pt-2">
            <button
              type="button"
              onClick={onClose}
              className="px-4 py-2 bg-gray-700 hover:bg-gray-600 text-white text-sm rounded-lg transition-colors"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={saving}
              className="px-5 py-2 bg-cyan-600 hover:bg-cyan-700 disabled:bg-gray-700 disabled:text-gray-500 text-white text-sm font-medium rounded-lg transition-colors flex items-center gap-2"
            >
              {saving ? <Loader2 className="h-4 w-4 animate-spin" /> : <Plus className="h-4 w-4" />}
              {isEdit ? 'Save Changes' : 'Add Server'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

// ============================================================================
// Server Card
// ============================================================================

function ServerCard({
  server,
  onEdit,
  onDelete,
  onTest,
  onScan,
}: {
  server: ServerInfo;
  onEdit: () => void;
  onDelete: () => void;
  onTest: () => void;
  onScan: () => void;
}) {
  const [expanded, setExpanded] = useState(false);
  const [testing, setTesting] = useState(false);
  const [scanning, setScanning] = useState(false);
  const [testResult, setTestResult] = useState<TestResult | null>(null);
  const [scanResult, setScanResult] = useState<ToolScanResult | null>(null);
  const [deleting, setDeleting] = useState(false);

  const handleTest = async () => {
    setTesting(true);
    setTestResult(null);
    try {
      const res = await fetch(`/api/plugins/remote_servers/servers/${server.id}/test`, {
        method: 'POST',
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || 'Test failed');
      setTestResult(data);
      onTest(); // Refresh server list
    } catch (err: any) {
      setTestResult({
        server_id: server.id,
        status: 'error',
        message: err.message || 'Connection test failed',
        latency_ms: null,
        system_info: null,
      });
    } finally {
      setTesting(false);
    }
  };

  const handleScan = async () => {
    setScanning(true);
    setScanResult(null);
    try {
      const res = await fetch(`/api/plugins/remote_servers/servers/${server.id}/scan`, {
        method: 'POST',
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || 'Scan failed');
      setScanResult(data);
      onScan(); // Refresh server list
    } catch (err: any) {
      setScanResult({
        server_id: server.id,
        tools_found: [],
        tools_missing: [],
        details: { error: err.message || 'Scan failed' },
      });
    } finally {
      setScanning(false);
    }
  };

  const handleDelete = async () => {
    if (!confirm(`Delete server "${server.name}"? This cannot be undone.`)) return;
    setDeleting(true);
    try {
      await fetch(`/api/plugins/remote_servers/servers/${server.id}`, {
        method: 'DELETE',
      });
      onDelete();
    } catch { /* ok */ }
    setDeleting(false);
  };

  const StatusIcon = () => {
    switch (server.status) {
      case 'online':
        return <Wifi className="h-4 w-4 text-green-400" />;
      case 'offline':
        return <WifiOff className="h-4 w-4 text-red-400" />;
      case 'error':
        return <XCircle className="h-4 w-4 text-red-400" />;
      default:
        return <AlertTriangle className="h-4 w-4 text-gray-500" />;
    }
  };

  return (
    <div className="bg-gray-800 border border-gray-700 rounded-lg overflow-hidden">
      {/* Card Header */}
      <div className="p-4">
        <div className="flex items-start justify-between">
          <div className="flex items-start gap-3 flex-1">
            <div className={`w-11 h-11 rounded-xl flex items-center justify-center flex-shrink-0 ${
              server.status === 'online'
                ? 'bg-green-900/30 border border-green-800'
                : 'bg-gray-700/50 border border-gray-600'
            }`}>
              <Server className={`h-5 w-5 ${server.status === 'online' ? 'text-green-400' : 'text-gray-400'}`} />
            </div>
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2 flex-wrap">
                <h3 className="font-semibold text-white">{server.name}</h3>
                <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium border ${
                  server.status === 'online'
                    ? 'bg-green-900/40 text-green-400 border-green-800'
                    : server.status === 'offline' || server.status === 'error'
                    ? 'bg-red-900/40 text-red-400 border-red-800'
                    : 'bg-gray-800 text-gray-400 border-gray-700'
                }`}>
                  <StatusIcon />
                  {server.status === 'online' ? 'Online' : server.status === 'offline' ? 'Offline' : server.status === 'error' ? 'Error' : 'Unknown'}
                </span>
              </div>
              <p className="text-sm text-gray-400 mt-1 font-mono">
                {server.username}@{server.host}:{server.port}
              </p>
              {server.tags.length > 0 && (
                <div className="flex gap-1.5 mt-2 flex-wrap">
                  {server.tags.map((tag) => (
                    <span
                      key={tag}
                      className="px-2 py-0.5 text-xs bg-cyan-900/30 border border-cyan-800 text-cyan-400 rounded-md"
                    >
                      {tag}
                    </span>
                  ))}
                </div>
              )}
              {server.installed_tools.length > 0 && (
                <div className="flex gap-1 mt-2 flex-wrap">
                  {server.installed_tools.map((tool) => (
                    <span
                      key={tool}
                      className="px-1.5 py-0.5 text-[10px] bg-purple-900/30 border border-purple-800 text-purple-400 rounded"
                    >
                      {tool}
                    </span>
                  ))}
                </div>
              )}
            </div>
          </div>

          {/* Actions */}
          <div className="flex items-center gap-1.5 ml-3 flex-shrink-0">
            <button
              onClick={handleTest}
              disabled={testing}
              className="p-2 text-gray-400 hover:text-cyan-400 hover:bg-cyan-900/20 rounded-lg transition-colors"
              title="Test Connection"
            >
              {testing ? <Loader2 className="h-4 w-4 animate-spin" /> : <Wifi className="h-4 w-4" />}
            </button>
            <button
              onClick={handleScan}
              disabled={scanning}
              className="p-2 text-gray-400 hover:text-purple-400 hover:bg-purple-900/20 rounded-lg transition-colors"
              title="Scan Tools"
            >
              {scanning ? <Loader2 className="h-4 w-4 animate-spin" /> : <Search className="h-4 w-4" />}
            </button>
            <button
              onClick={onEdit}
              className="p-2 text-gray-400 hover:text-white hover:bg-gray-700 rounded-lg transition-colors"
              title="Edit"
            >
              <Edit2 className="h-4 w-4" />
            </button>
            <button
              onClick={handleDelete}
              disabled={deleting}
              className="p-2 text-gray-400 hover:text-red-400 hover:bg-red-900/20 rounded-lg transition-colors"
              title="Delete"
            >
              {deleting ? <Loader2 className="h-4 w-4 animate-spin" /> : <Trash2 className="h-4 w-4" />}
            </button>
            <button
              onClick={() => setExpanded(!expanded)}
              className="p-2 text-gray-400 hover:text-white hover:bg-gray-700 rounded-lg transition-colors"
            >
              {expanded ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
            </button>
          </div>
        </div>
      </div>

      {/* Test Result */}
      {testResult && (
        <div className={`mx-4 mb-3 p-3 rounded-lg border text-sm ${
          testResult.status === 'online'
            ? 'bg-green-900/20 border-green-800 text-green-300'
            : 'bg-red-900/20 border-red-800 text-red-300'
        }`}>
          <div className="flex items-center gap-2">
            {testResult.status === 'online' ? (
              <CheckCircle className="h-4 w-4 text-green-400" />
            ) : (
              <XCircle className="h-4 w-4 text-red-400" />
            )}
            <span>{testResult.message}</span>
          </div>
        </div>
      )}

      {/* Scan Result */}
      {scanResult && (
        <div className="mx-4 mb-3 p-3 rounded-lg border border-gray-700 bg-gray-900/50">
          {scanResult.details.error ? (
            <p className="text-sm text-red-300">{scanResult.details.error}</p>
          ) : (
            <>
              <p className="text-xs text-gray-400 mb-2">
                Found {scanResult.tools_found.length} tool(s), {scanResult.tools_missing.length} not installed
              </p>
              {scanResult.tools_found.length > 0 && (
                <div className="flex gap-1.5 flex-wrap mb-2">
                  {scanResult.tools_found.map((tool) => (
                    <span key={tool} className="px-2 py-0.5 text-xs bg-green-900/30 border border-green-800 text-green-400 rounded-md">
                      {tool}
                    </span>
                  ))}
                </div>
              )}
              {scanResult.tools_missing.length > 0 && (
                <div className="flex gap-1.5 flex-wrap">
                  {scanResult.tools_missing.map((tool) => (
                    <span key={tool} className="px-2 py-0.5 text-xs bg-gray-800 border border-gray-700 text-gray-500 rounded-md line-through">
                      {tool}
                    </span>
                  ))}
                </div>
              )}
            </>
          )}
        </div>
      )}

      {/* Expanded Details */}
      {expanded && (
        <div className="border-t border-gray-700 p-4 space-y-3 bg-gray-850">
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            <div className="bg-gray-900/60 border border-gray-700 rounded-lg p-3">
              <p className="text-[10px] text-gray-500 uppercase tracking-wider">Auth</p>
              <p className="text-sm text-white mt-1.5 flex items-center">
                {server.auth_method === 'key' ? (
                  <><Key className="h-3.5 w-3.5 mr-1.5 text-cyan-400" /> SSH Key</>
                ) : (
                  <><Shield className="h-3.5 w-3.5 mr-1.5 text-cyan-400" /> Password</>
                )}
              </p>
            </div>
            <div className="bg-gray-900/60 border border-gray-700 rounded-lg p-3">
              <p className="text-[10px] text-gray-500 uppercase tracking-wider">Tools</p>
              <p className="text-sm text-white mt-1.5">{server.installed_tools.length} found</p>
            </div>
            <div className="bg-gray-900/60 border border-gray-700 rounded-lg p-3">
              <p className="text-[10px] text-gray-500 uppercase tracking-wider">Last Seen</p>
              <p className="text-sm text-white mt-1.5">
                {server.last_seen ? new Date(server.last_seen).toLocaleString() : 'Never'}
              </p>
            </div>
            <div className="bg-gray-900/60 border border-gray-700 rounded-lg p-3">
              <p className="text-[10px] text-gray-500 uppercase tracking-wider">Added</p>
              <p className="text-sm text-white mt-1.5">
                {server.added_at ? new Date(server.added_at).toLocaleDateString() : '-'}
              </p>
            </div>
          </div>

          {server.system_info && (
            <div className="bg-gray-900/60 border border-gray-700 rounded-lg p-3">
              <p className="text-[10px] text-gray-500 uppercase tracking-wider mb-2">System Info</p>
              <div className="font-mono text-xs text-gray-300 space-y-1">
                {server.system_info.uname && <p>{server.system_info.uname}</p>}
                {server.system_info.uptime && <p className="text-gray-500">{server.system_info.uptime}</p>}
              </div>
            </div>
          )}

          {server.notes && (
            <div className="bg-gray-900/60 border border-gray-700 rounded-lg p-3">
              <p className="text-[10px] text-gray-500 uppercase tracking-wider mb-1">Notes</p>
              <p className="text-sm text-gray-300">{server.notes}</p>
            </div>
          )}

          {/* Quick Exec */}
          <QuickExec serverId={server.id} />
        </div>
      )}
    </div>
  );
}

// ============================================================================
// Quick Exec (run a command on a server)
// ============================================================================

function QuickExec({ serverId }: { serverId: string }) {
  const [command, setCommand] = useState('');
  const [running, setRunning] = useState(false);
  const [output, setOutput] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const handleExec = async () => {
    if (!command.trim()) return;
    setRunning(true);
    setOutput(null);
    setError(null);
    try {
      const res = await fetch(
        `/api/plugins/remote_servers/servers/${serverId}/exec?command=${encodeURIComponent(command)}`,
        { method: 'POST' },
      );
      const data = await res.json();
      if (data.status === 'completed') {
        setOutput(data.output || '(no output)');
      } else {
        setError(data.error || 'Command failed');
      }
    } catch (err: any) {
      setError(err.message || 'Execution failed');
    } finally {
      setRunning(false);
    }
  };

  return (
    <div className="bg-gray-900/60 border border-gray-700 rounded-lg p-3">
      <p className="text-[10px] text-gray-500 uppercase tracking-wider mb-2">
        <Terminal className="h-3 w-3 inline mr-1 -mt-0.5" />
        Quick Execute
      </p>
      <div className="flex gap-2">
        <input
          value={command}
          onChange={(e) => setCommand(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && handleExec()}
          placeholder="e.g., whoami, hashcat --version"
          className="flex-1 bg-gray-800 border border-gray-600 rounded px-3 py-1.5 text-sm text-white font-mono placeholder-gray-500 focus:outline-none focus:border-cyan-500"
        />
        <button
          onClick={handleExec}
          disabled={running || !command.trim()}
          className="px-3 py-1.5 bg-cyan-600 hover:bg-cyan-700 disabled:bg-gray-700 disabled:text-gray-500 text-white text-sm rounded transition-colors"
        >
          {running ? <Loader2 className="h-4 w-4 animate-spin" /> : 'Run'}
        </button>
      </div>
      {output !== null && (
        <pre className="mt-2 bg-gray-800 rounded p-2 text-xs text-green-400 font-mono overflow-x-auto max-h-32 overflow-y-auto">
          {output}
        </pre>
      )}
      {error !== null && (
        <pre className="mt-2 bg-red-950 rounded p-2 text-xs text-red-300 font-mono overflow-x-auto max-h-32 overflow-y-auto">
          {error}
        </pre>
      )}
    </div>
  );
}

// ============================================================================
// Main Page
// ============================================================================

export default function RemoteServersPage() {
  const [servers, setServers] = useState<ServerInfo[]>([]);
  const [loading, setLoading] = useState(true);
  const [showForm, setShowForm] = useState(false);
  const [editingServer, setEditingServer] = useState<ServerInfo | null>(null);
  const [health, setHealth] = useState<any>(null);
  const [searchQuery, setSearchQuery] = useState('');

  const loadServers = async () => {
    try {
      const res = await fetch('/api/plugins/remote_servers/servers');
      if (res.ok) {
        const data = await res.json();
        setServers(data);
      }
    } catch { /* ok */ }
    setLoading(false);
  };

  useEffect(() => {
    loadServers();
    fetch('/api/plugins/remote_servers/health')
      .then(r => r.json())
      .then(setHealth)
      .catch(() => {});
  }, []);

  const handleFormSave = () => {
    setShowForm(false);
    setEditingServer(null);
    loadServers();
  };

  const handleFormClose = () => {
    setShowForm(false);
    setEditingServer(null);
  };

  const filtered = servers.filter((s) => {
    if (!searchQuery) return true;
    const q = searchQuery.toLowerCase();
    return (
      s.name.toLowerCase().includes(q) ||
      s.host.toLowerCase().includes(q) ||
      s.tags.some(t => t.toLowerCase().includes(q)) ||
      s.installed_tools.some(t => t.toLowerCase().includes(q))
    );
  });

  const onlineCount = servers.filter(s => s.status === 'online').length;

  return (
    <div className="max-w-5xl mx-auto">
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 bg-cyan-900/50 border border-cyan-700 rounded-xl flex items-center justify-center">
            <Server className="h-5 w-5 text-cyan-400" />
          </div>
          <div>
            <h1 className="text-2xl font-bold text-white">Remote Servers</h1>
            <p className="text-sm text-gray-400">
              {servers.length} server{servers.length !== 1 ? 's' : ''} registered
              {onlineCount > 0 && <span className="text-green-400"> &middot; {onlineCount} online</span>}
              {health?.ssh_backend && (
                <span className="text-gray-600"> &middot; SSH via {health.ssh_backend}</span>
              )}
            </p>
          </div>
        </div>
        <div className="flex items-center gap-3">
          <button
            onClick={loadServers}
            className="p-2 text-gray-400 hover:text-white hover:bg-gray-700 rounded-lg transition-colors"
            title="Refresh"
          >
            <RefreshCw className="h-4 w-4" />
          </button>
          <button
            onClick={() => { setEditingServer(null); setShowForm(true); }}
            className="px-4 py-2 bg-cyan-600 hover:bg-cyan-700 text-white text-sm font-medium rounded-lg transition-colors flex items-center gap-2"
          >
            <Plus className="h-4 w-4" />
            Add Server
          </button>
        </div>
      </div>

      {/* Search */}
      {servers.length > 0 && (
        <div className="mb-5 relative">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-gray-500" />
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="Search by name, IP, tag, or tool..."
            className="w-full pl-9 pr-4 py-2 bg-gray-900 border border-gray-700 rounded-lg text-sm text-white placeholder-gray-500 focus:outline-none focus:border-cyan-500"
          />
        </div>
      )}

      {/* Server List */}
      {loading ? (
        <div className="flex justify-center items-center min-h-[200px]">
          <Loader2 className="h-6 w-6 animate-spin text-cyan-500" />
          <span className="ml-2 text-gray-400">Loading servers...</span>
        </div>
      ) : filtered.length === 0 ? (
        <div className="text-center py-16">
          <Server className="h-12 w-12 text-gray-600 mx-auto mb-4" />
          {servers.length === 0 ? (
            <>
              <h3 className="text-lg font-medium text-gray-300 mb-2">No servers registered</h3>
              <p className="text-sm text-gray-500 mb-6 max-w-md mx-auto">
                Add remote servers with SSH credentials so CyberOps can offload tool execution
                (hashcat, nmap, etc.) to machines with the right hardware and tools installed.
              </p>
              <button
                onClick={() => setShowForm(true)}
                className="px-5 py-2.5 bg-cyan-600 hover:bg-cyan-700 text-white text-sm font-medium rounded-lg transition-colors inline-flex items-center gap-2"
              >
                <Plus className="h-4 w-4" />
                Add Your First Server
              </button>
            </>
          ) : (
            <p className="text-gray-500">No servers match your search</p>
          )}
        </div>
      ) : (
        <div className="space-y-3">
          {filtered.map((server) => (
            <ServerCard
              key={server.id}
              server={server}
              onEdit={() => { setEditingServer(server); setShowForm(true); }}
              onDelete={loadServers}
              onTest={loadServers}
              onScan={loadServers}
            />
          ))}
        </div>
      )}

      {/* Add/Edit Modal */}
      {showForm && (
        <ServerFormModal
          server={editingServer}
          onClose={handleFormClose}
          onSave={handleFormSave}
        />
      )}
    </div>
  );
}

import { useEffect, useState } from 'react';
import { Chrome, Copy, Download, RefreshCw, CheckCircle2, AlertCircle, Loader2 } from 'lucide-react';

interface Health {
  status: string;
  plugin: string;
  token_configured: boolean;
  last_heartbeat: string | null;
  captures_total: number;
}

const API_BASE = '/api/plugins/browser_extension';

export default function BrowserExtensionPage() {
  const [health, setHealth] = useState<Health | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [newToken, setNewToken] = useState<string | null>(null);
  const [rotating, setRotating] = useState(false);
  const [copied, setCopied] = useState(false);

  async function loadHealth() {
    try {
      setLoading(true);
      const res = await fetch(`${API_BASE}/health`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      setHealth(await res.json());
      setError(null);
    } catch (e: any) {
      setError(e.message || 'Failed to load plugin status');
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadHealth();
  }, []);

  async function rotateToken() {
    if (
      health?.token_configured &&
      !window.confirm('Rotating will invalidate the current token. Any extension using it will stop working until you paste the new token. Continue?')
    ) {
      return;
    }
    try {
      setRotating(true);
      const res = await fetch(`${API_BASE}/token/rotate`, { method: 'POST' });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const body = await res.json();
      setNewToken(body.token);
      setCopied(false);
      await loadHealth();
    } catch (e: any) {
      setError(e.message || 'Failed to rotate token');
    } finally {
      setRotating(false);
    }
  }

  async function copyToken() {
    if (!newToken) return;
    await navigator.clipboard.writeText(newToken);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-3">
        <Chrome className="h-7 w-7 text-[#00d4ff]" />
        <div>
          <h1 className="text-2xl font-semibold text-white">Browser Extension</h1>
          <p className="text-sm text-gray-400">One-click screenshot capture from any page into the active session.</p>
        </div>
      </div>

      {error && (
        <div className="flex items-start gap-2 p-3 bg-[#2a1414] border border-red-900 rounded text-red-300 text-sm">
          <AlertCircle className="h-4 w-4 mt-0.5 flex-shrink-0" />
          <span>{error}</span>
        </div>
      )}

      {/* Install card */}
      <section className="bg-[#161b22] border border-[#30363d] rounded-lg p-5">
        <h2 className="text-lg font-semibold text-white mb-3">Install</h2>
        <ol className="list-decimal list-inside space-y-2 text-sm text-gray-300">
          <li>
            <a
              href={`${API_BASE}/download`}
              className="inline-flex items-center gap-1.5 text-[#00d4ff] hover:underline"
            >
              <Download className="h-4 w-4" />
              Download the extension
            </a>{' '}
            and unzip it.
          </li>
          <li>
            Open <code className="px-1.5 py-0.5 bg-[#0d1117] rounded text-xs">chrome://extensions</code>.
          </li>
          <li>Toggle <b>Developer mode</b> on (top-right).</li>
          <li>Click <b>Load unpacked</b> and select the unzipped folder.</li>
          <li>Open the extension's <b>Options</b>: paste the pairing token from below, set backend URL, save.</li>
          <li>
            Use <kbd className="px-1.5 py-0.5 bg-[#0d1117] border border-[#30363d] rounded text-xs font-mono">Alt+S</kbd> on any page to capture into the last-used session.
          </li>
        </ol>
      </section>

      {/* Pairing card */}
      <section className="bg-[#161b22] border border-[#30363d] rounded-lg p-5">
        <h2 className="text-lg font-semibold text-white mb-3">Pairing token</h2>
        <p className="text-sm text-gray-400 mb-3">
          The extension sends this token with every request so only paired browsers can upload captures.
        </p>

        {newToken ? (
          <div className="space-y-3">
            <div className="p-3 bg-[#0d1117] border border-[#30363d] rounded">
              <div className="text-xs text-yellow-400 mb-1.5">Copy this now - it will not be shown again.</div>
              <code className="text-xs text-[#00d4ff] break-all">{newToken}</code>
            </div>
            <div className="flex gap-2">
              <button
                onClick={copyToken}
                className="inline-flex items-center gap-1.5 px-3 py-1.5 bg-[#0a66c2] hover:bg-[#0957a8] text-white text-sm font-semibold rounded"
              >
                {copied ? <CheckCircle2 className="h-4 w-4" /> : <Copy className="h-4 w-4" />}
                {copied ? 'Copied' : 'Copy'}
              </button>
              <button
                onClick={() => setNewToken(null)}
                className="px-3 py-1.5 text-sm text-gray-300 hover:text-white"
              >
                I've copied it, hide
              </button>
            </div>
          </div>
        ) : (
          <button
            onClick={rotateToken}
            disabled={rotating}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 bg-[#0a66c2] hover:bg-[#0957a8] disabled:bg-[#555] text-white text-sm font-semibold rounded"
          >
            {rotating ? <Loader2 className="h-4 w-4 animate-spin" /> : <RefreshCw className="h-4 w-4" />}
            {health?.token_configured ? 'Rotate token' : 'Generate token'}
          </button>
        )}
      </section>

      {/* Status card */}
      <section className="bg-[#161b22] border border-[#30363d] rounded-lg p-5">
        <div className="flex items-center justify-between mb-3">
          <h2 className="text-lg font-semibold text-white">Status</h2>
          <button
            onClick={loadHealth}
            disabled={loading}
            className="text-gray-400 hover:text-[#00d4ff] disabled:opacity-50"
            title="Refresh"
          >
            <RefreshCw className={`h-4 w-4 ${loading ? 'animate-spin' : ''}`} />
          </button>
        </div>
        {health ? (
          <dl className="grid grid-cols-2 gap-y-2 text-sm">
            <dt className="text-gray-400">Token configured</dt>
            <dd className="text-white">{health.token_configured ? 'Yes' : 'No'}</dd>
            <dt className="text-gray-400">Last heartbeat</dt>
            <dd className="text-white">{health.last_heartbeat || 'Never'}</dd>
            <dt className="text-gray-400">Captures received</dt>
            <dd className="text-white">{health.captures_total}</dd>
          </dl>
        ) : (
          <div className="text-sm text-gray-400">{loading ? 'Loading…' : 'No data'}</div>
        )}
      </section>
    </div>
  );
}

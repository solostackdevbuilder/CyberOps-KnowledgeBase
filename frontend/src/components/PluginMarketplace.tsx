import { useState, useEffect } from 'react';
import {
  Package, CheckCircle, Loader2, ExternalLink,
  ChevronDown, Activity, Key, Shield, Terminal,
  Cpu, Download, Play, AlertTriangle, Search, Wifi, WifiOff, Server, Chrome,
} from 'lucide-react';

interface PluginManifest {
  id: string;
  name: string;
  type: string;
  description: string;
  pages: { path: string; name: string; icon: string }[];
}

interface PluginHealth {
  status: string;
  plugin: string;
  execution_mode?: string;
  hashcat_available?: boolean;
  agent_reachable?: boolean;
}

interface PluginDetail {
  manifest: PluginManifest;
  health: PluginHealth | null;
  hashTypes?: Record<string, { name: string; code: string; example: string }>;
  attackModes?: Record<string, { name: string; description: string }>;
  inputSchema?: any;
}

type PluginStatus = 'ready' | 'needs_setup' | 'not_installed';

const PLUGIN_ICONS: Record<string, typeof Key> = {
  hashcat: Key,
  nmap: Activity,
  john: Key,
  auth: Shield,
  remote_servers: Server,
  browser_extension: Chrome,
  default: Package,
};

// Catalog of known plugins - installed ones come from API, the rest show as "available"
const PLUGIN_CATALOG = [
  {
    id: 'hashcat',
    name: 'Hashcat Password Cracker',
    description: 'GPU-accelerated password cracking with 300+ hash types. Supports dictionary, brute-force, rule-based, and combinator attacks.',
    type: 'tool',
    author: 'CyberOps',
    category: 'Password Cracking',
    version: '1.0.0',
  },
  {
    id: 'john',
    name: 'John the Ripper',
    description: 'Classic password cracker supporting hundreds of hash and cipher types. Great for quick cracks and custom rules.',
    type: 'tool',
    author: 'CyberOps',
    category: 'Password Cracking',
    version: 'Coming Soon',
  },
  {
    id: 'nmap',
    name: 'Nmap Scanner',
    description: 'Network discovery and security auditing. Port scanning, service detection, OS fingerprinting, and NSE scripts.',
    type: 'tool',
    author: 'CyberOps',
    category: 'Reconnaissance',
    version: 'Coming Soon',
  },
  {
    id: 'remote_servers',
    name: 'Remote Servers',
    description: 'Manage SSH connections to remote tool servers. Register servers with credentials, test connectivity, and discover installed tools so plugins can offload work remotely.',
    type: 'hybrid',
    author: 'CyberOps',
    category: 'Infrastructure',
    version: '1.0.0',
  },
  {
    id: 'browser_extension',
    name: 'Browser Extension',
    description: 'Companion Chrome extension for one-click screenshot capture from any page into the active session, with URL and title attached as source metadata.',
    type: 'hybrid',
    author: 'CyberOps',
    category: 'Capture',
    version: '1.0.0',
  },
  {
    id: 'auth_enterprise',
    name: 'Enterprise Auth (SSO)',
    description: 'JWT authentication with SSO support for Okta, Azure AD, and SAML. User management and RBAC.',
    type: 'ui',
    author: 'CyberOps',
    category: 'Enterprise',
    version: 'Coming Soon',
  },
];

function getPluginStatus(plugin: PluginDetail): PluginStatus {
  if (!plugin.health) return 'needs_setup';
  if (plugin.health.status === 'ok') {
    // For tool plugins, check if the binary is available
    if (plugin.health.hashcat_available === false && plugin.health.execution_mode === 'local') {
      return 'needs_setup';
    }
    return 'ready';
  }
  return 'needs_setup';
}

function StatusBadge({ status }: { status: PluginStatus }) {
  switch (status) {
    case 'ready':
      return (
        <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-medium bg-green-900/40 text-green-400 border border-green-800">
          <CheckCircle className="h-3 w-3" /> Ready
        </span>
      );
    case 'needs_setup':
      return (
        <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-medium bg-yellow-900/40 text-yellow-400 border border-yellow-800">
          <AlertTriangle className="h-3 w-3" /> Needs Setup
        </span>
      );
    case 'not_installed':
      return (
        <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-medium bg-gray-800 text-gray-400 border border-gray-700">
          <Download className="h-3 w-3" /> Available
        </span>
      );
  }
}

function ActionButton({ status, pluginId, onOpen }: { status: PluginStatus; pluginId: string; onOpen: (id: string) => void }) {
  const navigate = () => {
    window.location.href = `/plugins/${pluginId}`;
  };

  switch (status) {
    case 'ready':
      return (
        <div className="flex items-center gap-2">
          <button
            onClick={(e) => { e.stopPropagation(); navigate(); }}
            className="px-4 py-2 bg-green-600 hover:bg-green-700 text-white text-sm font-medium rounded-lg transition-colors flex items-center gap-1.5"
          >
            <Play className="h-4 w-4" /> Open
          </button>
          <button
            onClick={(e) => { e.stopPropagation(); onOpen(pluginId); }}
            className="px-3 py-2 bg-gray-700 hover:bg-gray-600 text-gray-300 text-sm rounded-lg transition-colors"
            title="Details"
          >
            <ChevronDown className="h-4 w-4" />
          </button>
        </div>
      );
    case 'needs_setup':
      return (
        <div className="flex items-center gap-2">
          <button
            onClick={(e) => { e.stopPropagation(); navigate(); }}
            className="px-4 py-2 bg-yellow-600 hover:bg-yellow-700 text-white text-sm font-medium rounded-lg transition-colors flex items-center gap-1.5"
          >
            <Play className="h-4 w-4" /> Open
          </button>
          <button
            onClick={(e) => { e.stopPropagation(); onOpen(pluginId); }}
            className="px-3 py-2 bg-gray-700 hover:bg-gray-600 text-gray-300 text-sm rounded-lg transition-colors"
            title="Details"
          >
            <ChevronDown className="h-4 w-4" />
          </button>
        </div>
      );
    case 'not_installed':
      return (
        <button
          disabled
          className="px-4 py-2 bg-gray-700 text-gray-400 text-sm font-medium rounded-lg cursor-not-allowed flex items-center gap-1.5"
        >
          <Download className="h-4 w-4" /> Install
        </button>
      );
  }
}

export default function PluginMarketplace() {
  const [installedPlugins, setInstalledPlugins] = useState<PluginDetail[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [expandedPlugin, setExpandedPlugin] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState('');
  const [filterCategory, setFilterCategory] = useState<string>('all');

  useEffect(() => {
    loadPlugins();
  }, []);

  const loadPlugins = async () => {
    try {
      setLoading(true);
      setError(null);

      const manifestRes = await fetch('/api/platform/manifest');
      if (!manifestRes.ok) throw new Error('Failed to fetch platform manifest');
      const manifest = await manifestRes.json();
      const pluginManifests: PluginManifest[] = manifest.plugins || [];

      const details: PluginDetail[] = [];
      for (const pm of pluginManifests) {
        const detail: PluginDetail = { manifest: pm, health: null };

        try {
          const healthRes = await fetch(`/api/plugins/${pm.id}/health`);
          if (healthRes.ok) detail.health = await healthRes.json();
        } catch { /* ok */ }

        if (pm.type === 'tool' || pm.type === 'hybrid') {
          try {
            const [htRes, amRes, schemaRes] = await Promise.all([
              fetch(`/api/plugins/${pm.id}/hash-types`).catch(() => null),
              fetch(`/api/plugins/${pm.id}/attack-modes`).catch(() => null),
              fetch(`/api/plugins/${pm.id}/input-schema`).catch(() => null),
            ]);
            if (htRes?.ok) detail.hashTypes = (await htRes.json()).hash_types;
            if (amRes?.ok) detail.attackModes = (await amRes.json()).attack_modes;
            if (schemaRes?.ok) detail.inputSchema = await schemaRes.json();
          } catch { /* optional */ }
        }

        details.push(detail);
      }

      setInstalledPlugins(details);
    } catch (err: any) {
      setError(err.message || 'Failed to load plugins');
    } finally {
      setLoading(false);
    }
  };

  const handleOpen = (pluginId: string) => {
    setExpandedPlugin(expandedPlugin === pluginId ? null : pluginId);
  };

  // Build full list: installed plugins + catalog items not yet installed
  const allPlugins = [
    ...PLUGIN_CATALOG.map(cat => {
      const installed = installedPlugins.find(p => p.manifest.id === cat.id);
      return {
        ...cat,
        installed: !!installed,
        detail: installed || null,
        status: installed ? getPluginStatus(installed) : 'not_installed' as PluginStatus,
      };
    }),
  ];

  // Filter
  const categories = ['all', ...new Set(PLUGIN_CATALOG.map(p => p.category))];
  const filtered = allPlugins.filter(p => {
    if (filterCategory !== 'all' && p.category !== filterCategory) return false;
    if (searchQuery) {
      const q = searchQuery.toLowerCase();
      return p.name.toLowerCase().includes(q) || p.description.toLowerCase().includes(q) || p.id.includes(q);
    }
    return true;
  });

  // Sort: installed first, then by name
  filtered.sort((a, b) => {
    if (a.installed && !b.installed) return -1;
    if (!a.installed && b.installed) return 1;
    return a.name.localeCompare(b.name);
  });

  if (loading) {
    return (
      <div className="flex justify-center items-center min-h-[200px]">
        <Loader2 className="h-6 w-6 animate-spin text-blue-500" />
        <span className="ml-2 text-gray-400">Loading marketplace...</span>
      </div>
    );
  }

  return (
    <div>
      {/* Header */}
      <div className="flex items-center justify-between mb-5">
        <div>
          <h2 className="text-xl font-semibold text-white flex items-center">
            <Package className="h-5 w-5 mr-2 text-purple-400" />
            Plugin Marketplace
          </h2>
          <p className="text-sm text-gray-400 mt-1">
            {installedPlugins.length} installed &middot; {PLUGIN_CATALOG.length - installedPlugins.length} available
          </p>
        </div>
      </div>

      {error && (
        <div className="mb-4 bg-red-900/20 border border-red-700 rounded-lg p-3 text-sm text-red-300">
          {error}
        </div>
      )}

      {/* Search + Category Filter */}
      <div className="flex gap-3 mb-5">
        <div className="flex-1 relative">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-gray-500" />
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="Search plugins..."
            className="w-full pl-9 pr-4 py-2 bg-gray-900 border border-gray-700 rounded-lg text-sm text-white placeholder-gray-500 focus:outline-none focus:border-purple-500"
          />
        </div>
        <div className="flex gap-1.5">
          {categories.map(cat => (
            <button
              key={cat}
              onClick={() => setFilterCategory(cat)}
              className={`px-3 py-2 text-xs rounded-lg border transition-colors capitalize ${
                filterCategory === cat
                  ? 'bg-purple-600 border-purple-500 text-white'
                  : 'bg-gray-800 border-gray-700 text-gray-400 hover:bg-gray-700'
              }`}
            >
              {cat}
            </button>
          ))}
        </div>
      </div>

      {/* Plugin Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {filtered.map((plugin) => {
          const IconComponent = PLUGIN_ICONS[plugin.id] || PLUGIN_ICONS.default;
          const isExpanded = expandedPlugin === plugin.id;
          const detail = plugin.detail;
          const comingSoon = plugin.version === 'Coming Soon';

          return (
            <div
              key={plugin.id}
              className={`bg-gray-800 border rounded-lg overflow-hidden transition-colors ${
                plugin.installed ? 'border-gray-600' : 'border-gray-700 opacity-80'
              } ${isExpanded ? 'lg:col-span-2' : ''}`}
            >
              {/* Card Header */}
              <div className="p-4">
                <div className="flex items-start justify-between">
                  <div className="flex items-start gap-3 flex-1">
                    <div className={`w-12 h-12 rounded-xl flex items-center justify-center flex-shrink-0 ${
                      plugin.installed ? 'bg-purple-900/50 border border-purple-700' : 'bg-gray-700/50 border border-gray-600'
                    }`}>
                      <IconComponent className={`h-6 w-6 ${plugin.installed ? 'text-purple-400' : 'text-gray-400'}`} />
                    </div>
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2 flex-wrap">
                        <h3 className="font-semibold text-white">{plugin.name}</h3>
                        <StatusBadge status={plugin.status} />
                      </div>
                      <p className="text-sm text-gray-400 mt-1 leading-relaxed">{plugin.description}</p>
                      <div className="flex items-center gap-3 mt-2">
                        <span className="text-xs text-gray-500">{plugin.author}</span>
                        <span className="text-xs text-gray-600">&middot;</span>
                        <span className="text-xs text-gray-500 capitalize">{plugin.type} plugin</span>
                        <span className="text-xs text-gray-600">&middot;</span>
                        <span className={`text-xs ${comingSoon ? 'text-yellow-500' : 'text-gray-500'}`}>
                          {plugin.version}
                        </span>
                      </div>
                    </div>
                  </div>
                  <div className="ml-3 flex-shrink-0">
                    {comingSoon ? (
                      <span className="px-3 py-2 bg-gray-700 text-gray-500 text-sm font-medium rounded-lg inline-block">
                        Coming Soon
                      </span>
                    ) : (
                      <ActionButton status={plugin.status} pluginId={plugin.id} onOpen={handleOpen} />
                    )}
                  </div>
                </div>
              </div>

              {/* Expanded Detail Panel */}
              {isExpanded && detail && (
                <div className="border-t border-gray-700 p-4 space-y-5 bg-gray-850">
                  {/* Status Overview */}
                  <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                    <div className="bg-gray-900/60 border border-gray-700 rounded-lg p-3">
                      <p className="text-[10px] text-gray-500 uppercase tracking-wider">Mode</p>
                      <p className="text-sm text-white mt-1.5 flex items-center">
                        {detail.health?.execution_mode === 'local' ? (
                          <><Terminal className="h-3.5 w-3.5 mr-1.5 text-blue-400" /> Local CLI</>
                        ) : detail.health?.execution_mode === 'remote' ? (
                          <><Cpu className="h-3.5 w-3.5 mr-1.5 text-cyan-400" /> Remote Agent</>
                        ) : (
                          'Unknown'
                        )}
                      </p>
                    </div>
                    <div className="bg-gray-900/60 border border-gray-700 rounded-lg p-3">
                      <p className="text-[10px] text-gray-500 uppercase tracking-wider">Binary</p>
                      <p className="text-sm mt-1.5">
                        {detail.health?.hashcat_available === true ? (
                          <span className="text-green-400 flex items-center"><CheckCircle className="h-3.5 w-3.5 mr-1.5" /> Installed</span>
                        ) : detail.health?.hashcat_available === false ? (
                          <span className="text-yellow-400 flex items-center"><AlertTriangle className="h-3.5 w-3.5 mr-1.5" /> Not Found</span>
                        ) : (
                          <span className="text-gray-500">N/A</span>
                        )}
                      </p>
                    </div>
                    <div className="bg-gray-900/60 border border-gray-700 rounded-lg p-3">
                      <p className="text-[10px] text-gray-500 uppercase tracking-wider">Status</p>
                      <p className="text-sm mt-1.5">
                        {(() => {
                          const h = detail.health;
                          if (!h) return <span className="text-gray-400 flex items-center"><WifiOff className="h-3.5 w-3.5 mr-1.5" /> Unknown</span>;
                          // Remote mode: check agent reachability
                          if (h.execution_mode === 'remote') {
                            return h.agent_reachable
                              ? <span className="text-green-400 flex items-center"><Wifi className="h-3.5 w-3.5 mr-1.5" /> Agent Connected</span>
                              : <span className="text-red-400 flex items-center"><WifiOff className="h-3.5 w-3.5 mr-1.5" /> Agent Unreachable</span>;
                          }
                          // Local mode: check binary
                          if (h.hashcat_available === true) {
                            return <span className="text-green-400 flex items-center"><CheckCircle className="h-3.5 w-3.5 mr-1.5" /> Ready</span>;
                          }
                          if (h.hashcat_available === false) {
                            return <span className="text-yellow-400 flex items-center"><AlertTriangle className="h-3.5 w-3.5 mr-1.5" /> Binary Missing</span>;
                          }
                          return <span className="text-green-400 flex items-center"><CheckCircle className="h-3.5 w-3.5 mr-1.5" /> Loaded</span>;
                        })()}
                      </p>
                    </div>
                    <div className="bg-gray-900/60 border border-gray-700 rounded-lg p-3">
                      <p className="text-[10px] text-gray-500 uppercase tracking-wider">Category</p>
                      <p className="text-sm text-white mt-1.5">{plugin.category}</p>
                    </div>
                  </div>

                  {/* Setup Instructions (if needs setup) */}
                  {plugin.status === 'needs_setup' && detail.health?.execution_mode === 'local' && (
                    <div className="bg-yellow-900/20 border border-yellow-800 rounded-lg p-4">
                      <h4 className="text-sm font-medium text-yellow-400 flex items-center mb-2">
                        <AlertTriangle className="h-4 w-4 mr-2" /> Setup Required
                      </h4>
                      <p className="text-sm text-yellow-200/80 mb-3">
                        The <code className="bg-yellow-900/40 px-1.5 py-0.5 rounded text-yellow-300">{plugin.id}</code> binary
                        was not found on this machine. You have two options:
                      </p>
                      <div className="space-y-2 text-sm text-yellow-200/70">
                        <div className="flex items-start gap-2">
                          <span className="text-yellow-500 font-bold mt-0.5">1.</span>
                          <div>
                            <span className="text-yellow-300 font-medium">Install locally:</span>{' '}
                            Download {plugin.id} and ensure it's in your system PATH
                          </div>
                        </div>
                        <div className="flex items-start gap-2">
                          <span className="text-yellow-500 font-bold mt-0.5">2.</span>
                          <div>
                            <span className="text-yellow-300 font-medium">Use remote mode:</span>{' '}
                            Deploy the CyberOps agent on a cracking rig and configure the agent URL in plugin settings
                          </div>
                        </div>
                      </div>
                    </div>
                  )}

                  {/* Hash Types */}
                  {detail.hashTypes && (
                    <div>
                      <h4 className="text-sm font-medium text-gray-300 mb-2">
                        Supported Hash Types ({Object.keys(detail.hashTypes).length})
                      </h4>
                      <div className="flex flex-wrap gap-1.5">
                        {Object.entries(detail.hashTypes).map(([key, ht]) => (
                          <span
                            key={key}
                            className="px-2 py-1 text-xs bg-gray-900 border border-gray-700 rounded-md text-gray-300 hover:border-purple-600 transition-colors cursor-default"
                            title={`Mode: ${ht.code}${ht.example ? `\nExample: ${ht.example}` : ''}`}
                          >
                            {ht.name}
                          </span>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* Attack Modes */}
                  {detail.attackModes && (
                    <div>
                      <h4 className="text-sm font-medium text-gray-300 mb-2">Attack Modes</h4>
                      <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
                        {Object.entries(detail.attackModes).map(([key, am]) => (
                          <div key={key} className="bg-gray-900/60 border border-gray-700 rounded-lg p-3">
                            <p className="text-sm text-white font-medium">{am.name}</p>
                            <p className="text-xs text-gray-400 mt-0.5">{am.description}</p>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* CLI Quick Start */}
                  <div>
                    <h4 className="text-sm font-medium text-gray-300 mb-2">Quick Start (CLI)</h4>
                    <div className="bg-gray-900 border border-gray-700 rounded-lg p-3 font-mono text-xs space-y-2 overflow-x-auto">
                      <div>
                        <span className="text-gray-500"># Crack an MD5 hash</span>
                        <div className="text-green-400 mt-0.5">
                          curl -X POST http://localhost:18000/api/plugins/{plugin.id}/crack \
                        </div>
                        <div className="text-green-400 pl-4">
                          -H "Content-Type: application/json" \
                        </div>
                        <div className="text-green-400 pl-4">
                          -d '{`{"hash_value": "5f4dcc3b...", "hash_type": "md5"}`}'
                        </div>
                      </div>
                      <div className="border-t border-gray-800 pt-2">
                        <span className="text-gray-500"># Check job status</span>
                        <div className="text-cyan-400 mt-0.5">
                          curl http://localhost:18000/api/plugins/{plugin.id}/jobs/{'<job_id>'}
                        </div>
                      </div>
                      <div className="border-t border-gray-800 pt-2">
                        <span className="text-gray-500"># List recent jobs</span>
                        <div className="text-cyan-400 mt-0.5">
                          curl http://localhost:18000/api/plugins/{plugin.id}/jobs
                        </div>
                      </div>
                    </div>
                  </div>

                  {/* Footer Links */}
                  <div className="flex items-center justify-between pt-2 border-t border-gray-700">
                    <div className="flex gap-4">
                      <a
                        href={`http://localhost:18000/docs#/${plugin.id}`}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="text-sm text-blue-400 hover:text-blue-300 flex items-center"
                      >
                        API Docs <ExternalLink className="h-3 w-3 ml-1" />
                      </a>
                    </div>
                    <button
                      onClick={() => setExpandedPlugin(null)}
                      className="text-sm text-gray-500 hover:text-gray-400"
                    >
                      Collapse
                    </button>
                  </div>
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}

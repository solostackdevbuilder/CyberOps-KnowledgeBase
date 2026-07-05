import { useState, useEffect, useCallback } from 'react';
import {
  Key, Play, Loader2, AlertTriangle, CheckCircle, XCircle,
  Terminal, Copy, Check, RefreshCw, Trash2, Clock, Hash,
  Settings2, ChevronDown, ChevronUp, Server,
} from 'lucide-react';

// ============================================================================
// Hash auto-detection
// ============================================================================

interface HashTypeInfo {
  id: string;
  name: string;
  code: string;
  regex: RegExp;
  example: string;
}

const HASH_PATTERNS: HashTypeInfo[] = [
  { id: 'bcrypt', name: 'bcrypt', code: '3200', regex: /^\$2[aby]?\$\d{1,2}\$.{53}$/, example: '$2a$05$...' },
  { id: 'sha512crypt', name: 'sha512crypt (Unix)', code: '1800', regex: /^\$6\$[^$]+\$[a-zA-Z0-9./]{86}$/, example: '$6$rounds$...' },
  { id: 'md5crypt', name: 'md5crypt (Unix)', code: '500', regex: /^\$1\$[^$]+\$[a-zA-Z0-9./]{22}$/, example: '$1$salt$...' },
  { id: 'kerberos_tgs', name: 'Kerberoasting TGS-REP', code: '13100', regex: /^\$krb5tgs\$/, example: '$krb5tgs$23$...' },
  { id: 'kerberos_asrep', name: 'AS-REP Roasting', code: '18200', regex: /^\$krb5asrep\$/, example: '$krb5asrep$23$...' },
  { id: 'netntlmv2', name: 'NetNTLMv2', code: '5600', regex: /^[a-fA-F0-9]{32}:[a-fA-F0-9]{32,}$/, example: 'user::domain:...' },
  { id: 'sha512', name: 'SHA-512', code: '1700', regex: /^[a-fA-F0-9]{128}$/, example: '128 hex chars' },
  { id: 'sha256', name: 'SHA-256', code: '1400', regex: /^[a-fA-F0-9]{64}$/, example: '64 hex chars' },
  { id: 'sha1', name: 'SHA-1', code: '100', regex: /^[a-fA-F0-9]{40}$/, example: '40 hex chars' },
  { id: 'md5', name: 'MD5', code: '0', regex: /^[a-fA-F0-9]{32}$/, example: '32 hex chars (also NTLM)' },
  { id: 'ntlm', name: 'NTLM', code: '1000', regex: /^[a-fA-F0-9]{32}$/, example: '32 hex chars' },
];

function detectHashType(hash: string): { detected: HashTypeInfo | null; candidates: HashTypeInfo[] } {
  const trimmed = hash.trim();
  if (!trimmed) return { detected: null, candidates: [] };

  const candidates = HASH_PATTERNS.filter(p => p.regex.test(trimmed));

  if (candidates.length === 1) return { detected: candidates[0], candidates };
  if (candidates.length > 1) return { detected: candidates[0], candidates };
  return { detected: null, candidates: [] };
}

// ============================================================================
// Types
// ============================================================================

interface CrackedPassword {
  hash: string;
  password: string;
}

interface CrackJob {
  job_id: string;
  hash_value: string;
  hash_type: string;
  attack_mode: string;
  status: string;
  submitted_at?: string;
  cracked_passwords?: CrackedPassword[];
  result?: {
    status: string;
    output?: string;
    error?: string;
    return_code?: number;
  };
  message?: string;
}

// ============================================================================
// Component
// ============================================================================

export default function HashcatPage() {
  // Input state
  const [hashInput, setHashInput] = useState('');
  const [detectedType, setDetectedType] = useState<HashTypeInfo | null>(null);
  const [candidates, setCandidates] = useState<HashTypeInfo[]>([]);
  const [selectedType, setSelectedType] = useState<string>('auto');
  const [attackMode, setAttackMode] = useState<string>('dictionary');
  const [wordlist, setWordlist] = useState('rockyou.txt');
  const [mask, setMask] = useState('?a?a?a?a?a?a?a?a');
  const [showAdvanced, setShowAdvanced] = useState(false);

  // Job state
  const [submitting, setSubmitting] = useState(false);
  const [currentJob, setCurrentJob] = useState<CrackJob | null>(null);
  const [jobHistory, setJobHistory] = useState<CrackJob[]>([]);
  const [loadingHistory, setLoadingHistory] = useState(true);

  // Plugin health
  const [health, setHealth] = useState<any>(null);
  const [copied, setCopied] = useState(false);

  // Settings
  const [autoDetectSessions, setAutoDetectSessions] = useState(false);
  const [execTarget, _setExecTarget] = useState<string>(() => localStorage.getItem('hashcat_exec_target') || 'local');
  const setExecTarget = (val: string) => { _setExecTarget(val); localStorage.setItem('hashcat_exec_target', val); };
  const [remoteServers, setRemoteServers] = useState<{ id: string; name: string; host: string; status: string }[]>([]);
  const [loadingServers, setLoadingServers] = useState(false);

  // Load plugin health, job history, and remote servers on mount
  useEffect(() => {
    fetch('/api/plugins/hashcat/health').then(r => r.json()).then(setHealth).catch(() => {});
    loadJobHistory();
    loadRemoteServers();
  }, []);

  const loadRemoteServers = async () => {
    setLoadingServers(true);
    try {
      // Get all servers, then check which ones have hashcat
      const [allRes, hashcatRes] = await Promise.all([
        fetch('/api/plugins/remote_servers/servers').catch(() => null),
        fetch('/api/plugins/remote_servers/discover/hashcat').catch(() => null),
      ]);
      const allServers = allRes?.ok ? await allRes.json() : [];
      const hashcatData = hashcatRes?.ok ? await hashcatRes.json() : { servers: [] };
      const hashcatIds = new Set(hashcatData.servers.map((s: any) => s.id));

      // Show all servers but mark which ones have hashcat
      setRemoteServers(
        allServers.map((s: any) => ({
          id: s.id,
          name: s.name,
          host: s.host,
          status: s.status,
          hasHashcat: hashcatIds.has(s.id),
        }))
      );
    } catch { /* ok */ }
    setLoadingServers(false);
  };

  // Auto-detect hash type as user types
  useEffect(() => {
    const { detected, candidates: cands } = detectHashType(hashInput);
    setDetectedType(detected);
    setCandidates(cands);
    if (detected && selectedType === 'auto') {
      // Don't override manual selection
    }
  }, [hashInput]);

  const loadJobHistory = async () => {
    setLoadingHistory(true);
    try {
      const res = await fetch('/api/plugins/hashcat/jobs?limit=20');
      if (res.ok) {
        const data = await res.json();
        setJobHistory(data.jobs || []);
      }
    } catch { /* ok */ }
    setLoadingHistory(false);
  };

  // Build the command that would be executed
  const buildCommand = useCallback(() => {
    const hash = hashInput.trim();
    if (!hash) return '';

    const effectiveType = selectedType !== 'auto' ? selectedType : detectedType?.id || 'auto';
    const typeCode = HASH_PATTERNS.find(p => p.id === effectiveType)?.code;

    let cmd = 'hashcat';
    if (typeCode) cmd += ` -m ${typeCode}`;

    if (attackMode === 'brute_force') {
      cmd += ` -a 3`;
    } else if (attackMode === 'combinator') {
      cmd += ` -a 1`;
    } else {
      cmd += ` -a 0`;
    }

    cmd += ` "${hash.length > 40 ? hash.substring(0, 37) + '...' : hash}"`;

    if (attackMode === 'brute_force') {
      cmd += ` "${mask}"`;
    } else {
      cmd += ` ${wordlist}`;
    }

    return cmd;
  }, [hashInput, selectedType, detectedType, attackMode, wordlist, mask]);

  const handleCrack = async () => {
    const hash = hashInput.trim();
    if (!hash) return;

    setSubmitting(true);
    setCurrentJob(null);

    try {
      const effectiveType = selectedType !== 'auto' ? selectedType : detectedType?.id || 'auto';

      const res = await fetch('/api/plugins/hashcat/crack', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          hash_value: hash,
          hash_type: effectiveType,
          attack_mode: attackMode,
          wordlist: attackMode !== 'brute_force' ? wordlist : undefined,
          mask: attackMode === 'brute_force' ? mask : undefined,
          server_id: execTarget !== 'local' ? execTarget : undefined,
        }),
      });

      const data = await res.json();
      setCurrentJob(data);
      loadJobHistory();
    } catch (err: any) {
      setCurrentJob({
        job_id: '',
        hash_value: hash,
        hash_type: selectedType,
        attack_mode: attackMode,
        status: 'failed',
        message: err.message || 'Request failed',
      });
    } finally {
      setSubmitting(false);
    }
  };

  const copyCommand = () => {
    navigator.clipboard.writeText(buildCommand());
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div className="max-w-5xl mx-auto">
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 bg-purple-900/50 border border-purple-700 rounded-xl flex items-center justify-center">
            <Key className="h-5 w-5 text-purple-400" />
          </div>
          <div>
            <h1 className="text-2xl font-bold text-white">Hashcat</h1>
            <p className="text-sm text-gray-400">Password cracking tool</p>
          </div>
        </div>
        <div className="flex items-center gap-3">
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Left: Crack Form */}
        <div className="lg:col-span-2 space-y-4">
          {/* Hash Input */}
          <div className="bg-gray-800 border border-gray-700 rounded-lg p-5">
            <label className="block text-sm font-medium text-gray-300 mb-2">
              <Hash className="h-4 w-4 inline mr-1.5 -mt-0.5" />
              Paste Hash
            </label>
            <textarea
              value={hashInput}
              onChange={(e) => setHashInput(e.target.value)}
              placeholder="e.g. 5f4dcc3b5aa765d61d8327deb882cf99"
              rows={3}
              className="w-full bg-gray-900 border border-gray-600 rounded-lg p-3 text-sm text-white font-mono placeholder-gray-500 focus:outline-none focus:border-purple-500 resize-none"
            />

            {/* Auto-detection result */}
            {hashInput.trim() && (
              <div className="mt-3 flex items-center gap-2 flex-wrap">
                {detectedType ? (
                  <>
                    <span className="text-sm text-green-400 flex items-center">
                      <CheckCircle className="h-3.5 w-3.5 mr-1" />
                      Detected: <span className="font-medium ml-1">{detectedType.name}</span>
                      <span className="text-gray-500 ml-1">(mode {detectedType.code})</span>
                    </span>
                    {candidates.length > 1 && (
                      <span className="text-xs text-gray-500">
                        &middot; also matches: {candidates.slice(1).map(c => c.name).join(', ')}
                      </span>
                    )}
                  </>
                ) : (
                  <span className="text-sm text-yellow-400 flex items-center">
                    <AlertTriangle className="h-3.5 w-3.5 mr-1" />
                    Could not auto-detect hash type - please select manually
                  </span>
                )}
              </div>
            )}

            {/* Hash type override */}
            <div className="mt-3 flex items-center gap-3">
              <label className="text-xs text-gray-400">Type:</label>
              <select
                value={selectedType}
                onChange={(e) => setSelectedType(e.target.value)}
                className="bg-gray-900 border border-gray-600 rounded px-2 py-1 text-sm text-white focus:outline-none focus:border-purple-500"
              >
                <option value="auto">Auto-detect{detectedType ? ` (${detectedType.name})` : ''}</option>
                <optgroup label="Common">
                  <option value="md5">MD5</option>
                  <option value="sha1">SHA-1</option>
                  <option value="sha256">SHA-256</option>
                  <option value="ntlm">NTLM</option>
                  <option value="bcrypt">bcrypt</option>
                </optgroup>
                <optgroup label="Active Directory">
                  <option value="kerberos_tgs">Kerberoasting TGS-REP</option>
                  <option value="kerberos_asrep">AS-REP Roasting</option>
                  <option value="netntlmv2">NetNTLMv2</option>
                </optgroup>
                <optgroup label="Unix">
                  <option value="sha512crypt">sha512crypt</option>
                  <option value="md5crypt">md5crypt</option>
                </optgroup>
                <optgroup label="Database">
                  <option value="mysql">MySQL 4.1/5</option>
                  <option value="mssql">MSSQL 2012+</option>
                </optgroup>
              </select>
            </div>
          </div>

          {/* Attack Mode */}
          <div className="bg-gray-800 border border-gray-700 rounded-lg p-5">
            <label className="block text-sm font-medium text-gray-300 mb-3">Attack Mode</label>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
              {[
                { id: 'dictionary', name: 'Dictionary', desc: 'Wordlist', icon: '📖', default: true },
                { id: 'combinator', name: 'Combinator', desc: 'Two wordlists', icon: '🔗', default: true },
                { id: 'rule_based', name: 'Rule-based', desc: 'Wordlist + rules', icon: '📐' },
                { id: 'brute_force', name: 'Brute Force', desc: 'Mask pattern', icon: '💪' },
              ].map((mode) => (
                <button
                  key={mode.id}
                  onClick={() => setAttackMode(mode.id)}
                  className={`p-3 rounded-lg border text-left transition-all ${
                    attackMode === mode.id
                      ? 'bg-purple-900/40 border-purple-600 text-white'
                      : 'bg-gray-900/50 border-gray-700 text-gray-400 hover:border-gray-500'
                  }`}
                >
                  <div className="text-lg mb-1">{mode.icon}</div>
                  <div className="text-sm font-medium">{mode.name}</div>
                  <div className="text-xs text-gray-500 mt-0.5">{mode.desc}</div>
                  {mode.default && (
                    <span className="text-[10px] text-purple-400 mt-1 inline-block">Recommended</span>
                  )}
                </button>
              ))}
            </div>

            {/* Attack-specific options */}
            <div className="mt-4">
              {attackMode !== 'brute_force' && (
                <div>
                  <label className="text-xs text-gray-400 block mb-1">Wordlist</label>
                  <select
                    value={wordlist}
                    onChange={(e) => setWordlist(e.target.value)}
                    className="w-full bg-gray-900 border border-gray-600 rounded px-3 py-2 text-sm text-white focus:outline-none focus:border-purple-500"
                  >
                    <option value="rockyou.txt">rockyou.txt - Classic password list (14M passwords)</option>
                    <option value="top1000.txt">top1000.txt - Top 1000 most common passwords</option>
                    <option value="richardlist.txt">richardlist.txt - Custom curated list</option>
                  </select>
                </div>
              )}
              {attackMode === 'brute_force' && (
                <div>
                  <label className="text-xs text-gray-400 block mb-1">
                    Mask Pattern
                    <span className="text-gray-600 ml-2">?l=lower ?u=upper ?d=digit ?s=special ?a=all</span>
                  </label>
                  <input
                    value={mask}
                    onChange={(e) => setMask(e.target.value)}
                    className="w-full bg-gray-900 border border-gray-600 rounded px-3 py-2 text-sm text-white font-mono focus:outline-none focus:border-purple-500"
                    placeholder="?a?a?a?a?a?a?a?a"
                  />
                </div>
              )}
            </div>
          </div>

          {/* Command Preview */}
          {hashInput.trim() && (
            <div className="bg-gray-800 border border-gray-700 rounded-lg p-5">
              <div className="flex items-center justify-between mb-2">
                <label className="text-sm font-medium text-gray-300 flex items-center">
                  <Terminal className="h-4 w-4 mr-1.5" />
                  Command Preview
                </label>
                <button
                  onClick={copyCommand}
                  className="text-xs text-gray-400 hover:text-white flex items-center gap-1 transition-colors"
                >
                  {copied ? <><Check className="h-3 w-3" /> Copied</> : <><Copy className="h-3 w-3" /> Copy</>}
                </button>
              </div>
              <div className="bg-gray-900 border border-gray-700 rounded-lg p-3 font-mono text-sm text-green-400 overflow-x-auto">
                {buildCommand()}
              </div>
              <p className="text-xs text-gray-500 mt-2">
                This command will be executed. You can copy and modify it, or click Crack to run it directly.
              </p>
            </div>
          )}

          {/* Crack Button */}
          <button
            onClick={handleCrack}
            disabled={!hashInput.trim() || submitting}
            className="w-full py-3 bg-purple-600 hover:bg-purple-700 disabled:bg-gray-700 disabled:text-gray-500 text-white font-medium rounded-lg transition-colors flex items-center justify-center gap-2"
          >
            {submitting ? (
              <><Loader2 className="h-5 w-5 animate-spin" /> Cracking...</>
            ) : (
              <><Play className="h-5 w-5" /> Crack Hash</>
            )}
          </button>

          {/* Current Job Result */}
          {currentJob && (
            <div className={`border rounded-lg p-5 ${
              currentJob.status === 'cracked'
                ? 'bg-green-900/20 border-green-800'
                : currentJob.status === 'exhausted'
                ? 'bg-yellow-900/20 border-yellow-800'
                : currentJob.status === 'failed' || currentJob.status === 'timeout'
                ? 'bg-red-900/20 border-red-800'
                : 'bg-blue-900/20 border-blue-800'
            }`}>
              <div className="flex items-center gap-2 mb-3">
                {currentJob.status === 'cracked' && <CheckCircle className="h-5 w-5 text-green-400" />}
                {currentJob.status === 'completed' && <CheckCircle className="h-5 w-5 text-green-400" />}
                {currentJob.status === 'exhausted' && <XCircle className="h-5 w-5 text-yellow-400" />}
                {currentJob.status === 'failed' && <XCircle className="h-5 w-5 text-red-400" />}
                {currentJob.status === 'timeout' && <Clock className="h-5 w-5 text-yellow-400" />}
                {currentJob.status === 'submitted' && <Loader2 className="h-5 w-5 text-blue-400 animate-spin" />}
                <span className="font-medium text-white capitalize">{currentJob.status}</span>
                {currentJob.job_id && (
                  <span className="text-xs text-gray-500 font-mono">{currentJob.job_id.substring(0, 8)}...</span>
                )}
              </div>

              {/* Cracked passwords - prominent display */}
              {currentJob.cracked_passwords && currentJob.cracked_passwords.length > 0 && (
                <div className="mb-3 space-y-2">
                  {currentJob.cracked_passwords.map((cp, i) => (
                    <div key={i} className="bg-green-900/30 border border-green-700 rounded-lg p-4">
                      <p className="text-sm text-green-300">
                        Password for <span className="font-mono text-green-400">{cp.hash.length > 24 ? cp.hash.substring(0, 24) + '...' : cp.hash}</span> is
                      </p>
                      <p className="font-mono text-2xl font-bold text-green-400 mt-1">{cp.password}</p>
                    </div>
                  ))}
                </div>
              )}

              <p className="text-sm text-gray-300">{currentJob.message}</p>
              {currentJob.result?.output && (
                <details className="mt-3">
                  <summary className="text-xs text-gray-500 cursor-pointer hover:text-gray-300">Raw hashcat output</summary>
                  <pre className="mt-2 bg-gray-900 rounded p-3 text-xs text-gray-300 overflow-x-auto max-h-48 overflow-y-auto font-mono">
                    {currentJob.result.output}
                  </pre>
                </details>
              )}
              {currentJob.result?.error && (
                <pre className="mt-3 bg-red-950 rounded p-3 text-xs text-red-300 overflow-x-auto max-h-48 overflow-y-auto font-mono">
                  {currentJob.result.error}
                </pre>
              )}
            </div>
          )}
        </div>

        {/* Right Sidebar */}
        <div className="space-y-4">
          {/* Session Auto-Detect Toggle */}
          <div className="bg-gray-800 border border-gray-700 rounded-lg p-4">
            <div className="flex items-start gap-3">
              <div className="flex-1 min-w-0">
                <h3 className="text-sm font-medium text-white">Auto-detect in Sessions</h3>
                <p className="text-xs text-gray-400 mt-1">
                  Scan session terminal content for hashes and queue them for cracking
                </p>
              </div>
              <button
                onClick={() => setAutoDetectSessions(!autoDetectSessions)}
                className={`relative inline-flex h-6 w-11 flex-shrink-0 items-center rounded-full transition-colors mt-0.5 ${
                  autoDetectSessions ? 'bg-purple-600' : 'bg-gray-600'
                }`}
              >
                <span className={`inline-block h-4 w-4 transform rounded-full bg-white transition-transform ${
                  autoDetectSessions ? 'translate-x-6' : 'translate-x-1'
                }`} />
              </button>
            </div>
            {autoDetectSessions && (
              <div className="mt-3 p-2 bg-purple-900/20 border border-purple-800 rounded text-xs text-purple-300">
                Auto-detection will scan new session content for password hashes (NTLM, MD5, SHA, bcrypt, Kerberos tickets) and add them to the crack queue.
              </div>
            )}
          </div>

          {/* Execution Target */}
          <div className="bg-gray-800 border border-gray-700 rounded-lg p-4">
            <button
              onClick={() => setShowAdvanced(!showAdvanced)}
              className="flex items-center justify-between w-full text-sm font-medium text-gray-300"
            >
              <span className="flex items-center">
                <Settings2 className="h-4 w-4 mr-1.5" /> Execution Target
              </span>
              {showAdvanced ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
            </button>
            {showAdvanced && (
              <div className="mt-3 space-y-2 text-sm">
                {/* Local option */}
                <button
                  onClick={() => setExecTarget('local')}
                  className={`w-full p-3 rounded-lg border text-left transition-all ${
                    execTarget === 'local'
                      ? 'bg-purple-900/40 border-purple-600'
                      : 'bg-gray-900/50 border-gray-700 hover:border-gray-500'
                  }`}
                >
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <Terminal className="h-4 w-4 text-blue-400" />
                      <span className="text-white font-medium">Local Machine</span>
                    </div>
                    {health?.hashcat_available ? (
                      <span className="text-[10px] px-1.5 py-0.5 rounded bg-green-900/40 text-green-400">Ready</span>
                    ) : (
                      <span className="text-[10px] px-1.5 py-0.5 rounded bg-yellow-900/40 text-yellow-400">Not Found</span>
                    )}
                  </div>
                  <p className="text-xs text-gray-500 mt-1 ml-6">Run hashcat on this machine</p>
                </button>

                {/* Remote servers */}
                {loadingServers ? (
                  <div className="flex items-center justify-center py-3 text-gray-500 text-xs">
                    <Loader2 className="h-3 w-3 animate-spin mr-1.5" /> Loading servers...
                  </div>
                ) : remoteServers.length > 0 ? (
                  remoteServers.map((srv: any) => (
                    <button
                      key={srv.id}
                      onClick={() => setExecTarget(srv.id)}
                      className={`w-full p-3 rounded-lg border text-left transition-all ${
                        execTarget === srv.id
                          ? 'bg-purple-900/40 border-purple-600'
                          : 'bg-gray-900/50 border-gray-700 hover:border-gray-500'
                      }`}
                    >
                      <div className="flex items-center justify-between">
                        <div className="flex items-center gap-2">
                          <Server className="h-4 w-4 text-cyan-400" />
                          <span className="text-white font-medium">{srv.name}</span>
                        </div>
                        <div className="flex items-center gap-1.5">
                          {srv.hasHashcat && (
                            <span className="text-[10px] px-1.5 py-0.5 rounded bg-purple-900/40 text-purple-400">hashcat</span>
                          )}
                          <span className={`text-[10px] px-1.5 py-0.5 rounded ${
                            srv.status === 'online'
                              ? 'bg-green-900/40 text-green-400'
                              : 'bg-gray-700 text-gray-500'
                          }`}>
                            {srv.status === 'online' ? 'Online' : srv.status}
                          </span>
                        </div>
                      </div>
                      <p className="text-xs text-gray-500 mt-1 ml-6 font-mono">{srv.host}</p>
                    </button>
                  ))
                ) : (
                  <div className="text-center py-3 border border-dashed border-gray-700 rounded-lg">
                    <p className="text-xs text-gray-500">No remote servers registered</p>
                    <a
                      href="/plugins/remote_servers"
                      className="text-xs text-cyan-400 hover:text-cyan-300 mt-1 inline-block"
                    >
                      Add servers &rarr;
                    </a>
                  </div>
                )}

                <button
                  onClick={loadRemoteServers}
                  className="w-full text-xs text-gray-500 hover:text-gray-300 py-1 flex items-center justify-center gap-1"
                >
                  <RefreshCw className="h-3 w-3" /> Refresh servers
                </button>
              </div>
            )}
          </div>

          {/* Job History */}
          <div className="bg-gray-800 border border-gray-700 rounded-lg p-4">
            <div className="flex items-center justify-between mb-3">
              <h3 className="text-sm font-medium text-gray-300 flex items-center">
                <Clock className="h-4 w-4 mr-1.5" /> Recent Jobs
              </h3>
              <div className="flex items-center gap-1.5">
                {jobHistory.length > 0 && (
                  <button
                    onClick={async () => {
                      await fetch('/api/plugins/hashcat/jobs', { method: 'DELETE' });
                      loadJobHistory();
                    }}
                    className="text-gray-500 hover:text-red-400 transition-colors"
                    title="Clear all jobs"
                  >
                    <Trash2 className="h-3.5 w-3.5" />
                  </button>
                )}
                <button onClick={loadJobHistory} className="text-gray-500 hover:text-gray-300">
                  <RefreshCw className="h-3.5 w-3.5" />
                </button>
              </div>
            </div>
            {loadingHistory ? (
              <div className="text-center py-4">
                <Loader2 className="h-4 w-4 animate-spin text-gray-500 mx-auto" />
              </div>
            ) : jobHistory.length === 0 ? (
              <p className="text-xs text-gray-500 text-center py-4">No jobs yet</p>
            ) : (
              <div className="space-y-2 max-h-80 overflow-y-auto">
                {jobHistory.map((job) => (
                  <div
                    key={job.job_id}
                    className={`bg-gray-900/60 border rounded-md p-2.5 ${
                      job.status === 'cracked' ? 'border-green-800' :
                      job.status === 'exhausted' ? 'border-yellow-800' :
                      job.status === 'failed' ? 'border-red-800' :
                      'border-gray-700'
                    }`}
                  >
                    <div className="flex items-center justify-between">
                      <span className="text-xs font-mono text-gray-300 truncate max-w-[140px]">
                        {job.hash_value}
                      </span>
                      <span className={`text-[10px] font-medium px-1.5 py-0.5 rounded ${
                        job.status === 'cracked' ? 'bg-green-900/40 text-green-400' :
                        job.status === 'exhausted' ? 'bg-yellow-900/40 text-yellow-400' :
                        job.status === 'failed' ? 'bg-red-900/40 text-red-400' :
                        job.status === 'completed' ? 'bg-green-900/40 text-green-400' :
                        'bg-gray-700 text-gray-400'
                      }`}>
                        {job.status}
                      </span>
                    </div>
                    {job.cracked_passwords && job.cracked_passwords.length > 0 && (
                      <div className="mt-1.5">
                        {job.cracked_passwords.map((cp, i) => (
                          <div key={i} className="text-xs font-mono text-green-400 flex items-center gap-1">
                            <span className="text-green-600">&rarr;</span> {cp.password}
                          </div>
                        ))}
                      </div>
                    )}
                    <div className="flex items-center gap-2 mt-1 text-[10px] text-gray-500">
                      <span>{job.hash_type}</span>
                      <span>&middot;</span>
                      <span>{job.submitted_at ? new Date(job.submitted_at).toLocaleTimeString() : ''}</span>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

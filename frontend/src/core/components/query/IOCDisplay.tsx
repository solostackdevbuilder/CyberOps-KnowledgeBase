import { useState } from 'react';
import { Copy, Check, Hash, Globe, Server } from 'lucide-react';

interface IOCDisplayProps {
  iocs: {
    ips?: string[];
    domains?: string[];
    hashes?: string[];
  };
}

// Regex patterns for IOC detection
const IP_PATTERN = /(?:\d{1,3}\.){3}\d{1,3}/g;
const DOMAIN_PATTERN = /(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,}/gi;
const HASH_PATTERN = /\b[a-f0-9]{32}\b|\b[a-f0-9]{40}\b|\b[a-f0-9]{64}\b/gi;

// Extract IOCs from text
const extractIOCs = (text: string) => {
  const ips = Array.from(new Set(text.match(IP_PATTERN) || []));
  const domains = Array.from(new Set(text.match(DOMAIN_PATTERN) || []));
  const hashes = Array.from(new Set(text.match(HASH_PATTERN) || []));
  return { ips, domains, hashes };
};

interface IOCItemProps {
  value: string;
  type: 'ip' | 'domain' | 'hash';
}

function IOCItem({ value, type }: IOCItemProps) {
  const [copied, setCopied] = useState(false);

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(value);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch (err) {
      console.error('Failed to copy:', err);
    }
  };

  const iconConfig = {
    ip: { icon: Server, color: 'text-blue-400', bg: 'bg-blue-500/10', border: 'border-blue-500/30' },
    domain: { icon: Globe, color: 'text-green-400', bg: 'bg-green-500/10', border: 'border-green-500/30' },
    hash: { icon: Hash, color: 'text-purple-400', bg: 'bg-purple-500/10', border: 'border-purple-500/30' },
  };

  const config = iconConfig[type];
  const Icon = config.icon;

  return (
    <div
      className={`flex items-center gap-2 px-3 py-2 ${config.bg} ${config.border} border rounded-lg group hover:shadow-md transition-all`}
    >
      <Icon className={`h-4 w-4 ${config.color} flex-shrink-0`} />
      <code className="flex-1 text-sm font-mono text-gray-200 break-all">{value}</code>
      <button
        onClick={handleCopy}
        className="p-1.5 hover:bg-gray-700/50 rounded transition-colors flex-shrink-0"
        title="Copy to clipboard"
      >
        {copied ? (
          <Check className="h-4 w-4 text-green-400" />
        ) : (
          <Copy className="h-4 w-4 text-gray-400 group-hover:text-gray-300" />
        )}
      </button>
    </div>
  );
}

export default function IOCDisplay({ iocs }: IOCDisplayProps) {
  const { ips = [], domains = [], hashes = [] } = iocs;
  const hasIOCs = ips.length > 0 || domains.length > 0 || hashes.length > 0;

  if (!hasIOCs) return null;

  return (
    <div className="mt-6 pt-6 border-t border-gray-700/50">
      <h3 className="text-sm font-semibold text-gray-300 mb-4 flex items-center gap-2">
        <Hash className="h-4 w-4" />
        Indicators of Compromise (IOCs)
      </h3>
      
      <div className="space-y-4">
        {ips.length > 0 && (
          <div>
            <h4 className="text-xs font-medium text-gray-400 mb-2 flex items-center gap-1.5">
              <Server className="h-3.5 w-3.5" />
              IP Addresses ({ips.length})
            </h4>
            <div className="grid grid-cols-1 gap-2">
              {ips.map((ip, idx) => (
                <IOCItem key={idx} value={ip} type="ip" />
              ))}
            </div>
          </div>
        )}

        {domains.length > 0 && (
          <div>
            <h4 className="text-xs font-medium text-gray-400 mb-2 flex items-center gap-1.5">
              <Globe className="h-3.5 w-3.5" />
              Domains ({domains.length})
            </h4>
            <div className="grid grid-cols-1 gap-2">
              {domains.map((domain, idx) => (
                <IOCItem key={idx} value={domain} type="domain" />
              ))}
            </div>
          </div>
        )}

        {hashes.length > 0 && (
          <div>
            <h4 className="text-xs font-medium text-gray-400 mb-2 flex items-center gap-1.5">
              <Hash className="h-3.5 w-3.5" />
              Hashes ({hashes.length})
            </h4>
            <div className="grid grid-cols-1 gap-2">
              {hashes.map((hash, idx) => (
                <IOCItem key={idx} value={hash} type="hash" />
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

// Helper function to extract IOCs from answer text
export { extractIOCs };






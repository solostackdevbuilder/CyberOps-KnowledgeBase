import { useState } from 'react';
import { Edit, Trash2, ChevronDown, ChevronUp, Code, Image as ImageIcon, FileEdit, AlertTriangle, CheckCircle2, XCircle } from 'lucide-react';
import type { FAAItem } from '../types';

interface FAAItemCardProps {
  item: FAAItem;
  onEdit: (item: FAAItem) => void;
  onDelete: (itemId: string) => void;
}

function FAAItemCard({ item, onEdit, onDelete }: FAAItemCardProps) {
  const [expanded, setExpanded] = useState(false);

  const getBorderColor = () => {
    if (item.classification === 'finding') {
      switch (item.severity) {
        case 'critical':
          return 'border-l-4 border-red-600';
        case 'high':
          return 'border-l-4 border-orange-600';
        case 'medium':
          return 'border-l-4 border-yellow-600';
        case 'low':
          return 'border-l-4 border-blue-600';
        default:
          return 'border-l-4 border-gray-600';
      }
    }
    return 'border-l-4 border-gray-500';
  };

  const getSeverityColor = (severity?: string) => {
    switch (severity) {
      case 'critical':
        return 'bg-red-900/50 text-red-300 border-red-600';
      case 'high':
        return 'bg-orange-900/50 text-orange-300 border-orange-600';
      case 'medium':
        return 'bg-yellow-900/50 text-yellow-300 border-yellow-600';
      case 'low':
        return 'bg-blue-900/50 text-blue-300 border-blue-600';
      default:
        return 'bg-gray-700 text-gray-300 border-gray-600';
    }
  };

  const getConfidenceBadge = () => {
    if (item.confidence_score > 0.8) {
      return (
        <span className="px-2 py-0.5 text-xs bg-green-900/50 text-green-300 rounded border border-green-600 flex items-center gap-1">
          <CheckCircle2 className="h-3 w-3" />
          High confidence
        </span>
      );
    } else if (item.confidence_score >= 0.5) {
      return (
        <span className="px-2 py-0.5 text-xs bg-yellow-900/50 text-yellow-300 rounded border border-yellow-600 flex items-center gap-1">
          <AlertTriangle className="h-3 w-3" />
          Review recommended
        </span>
      );
    } else {
      return (
        <span className="px-2 py-0.5 text-xs bg-red-900/50 text-red-300 rounded border border-red-600 flex items-center gap-1">
          <XCircle className="h-3 w-3" />
          Low confidence
        </span>
      );
    }
  };

  const getSourceIcon = () => {
    switch (item.source) {
      case 'terminal':
        return <Code className="h-4 w-4" />;
      case 'screenshot':
        return <ImageIcon className="h-4 w-4" />;
      case 'manual':
        return <FileEdit className="h-4 w-4" />;
      default:
        return null;
    }
  };

  const formatDate = (dateString: string) => {
    const date = new Date(dateString);
    return date.toLocaleDateString('en-US', {
      year: 'numeric',
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    });
  };

  return (
    <div className={`bg-gray-800 border border-gray-700 rounded-lg ${getBorderColor()}`}>
      <div className="p-4">
        <div className="flex items-start justify-between mb-2">
          <div className="flex-1">
            <div className="flex items-center gap-2 mb-2">
              <span
                className={`px-2 py-1 text-xs font-semibold rounded ${
                  item.classification === 'finding'
                    ? 'bg-red-900/50 text-red-300 border border-red-600'
                    : 'bg-gray-700 text-gray-300 border border-gray-600'
                }`}
              >
                {item.classification === 'finding' ? '⚠️ FINDING' : '⚡ ACTION'}
              </span>
              {item.severity && (
                <span className={`px-2 py-1 text-xs rounded border ${getSeverityColor(item.severity)}`}>
                  {item.severity.toUpperCase()}
                </span>
              )}
              {item.mitre_technique && (
                <span className="px-2 py-1 text-xs bg-purple-900/50 text-purple-300 rounded border border-purple-600">
                  {item.mitre_technique}
                </span>
              )}
              {item.detection_strategy_ids && item.detection_strategy_ids.length > 0 && (
                <span className="px-2 py-1 text-xs bg-blue-900/50 text-blue-300 rounded border border-blue-600" title={`${item.detection_strategy_ids.length} detection strateg${item.detection_strategy_ids.length > 1 ? 'ies' : 'y'}`}>
                  🛡️ {item.detection_strategy_ids.length} DET{item.detection_strategy_ids.length > 1 ? 's' : ''}
                </span>
              )}
              {getConfidenceBadge()}
            </div>
            <h3 className="text-white font-medium mb-1">{item.content}</h3>
            {item.mitre_tactic && (
              <p className="text-sm text-gray-400 mb-2">Tactic: {item.mitre_tactic}</p>
            )}
          </div>
          <div className="flex items-center gap-2">
            <div className="flex items-center gap-1 text-gray-400 text-xs" title={item.source}>
              {getSourceIcon()}
            </div>
            <button
              onClick={() => onEdit(item)}
              className="p-1 text-gray-400 hover:text-blue-400 transition-colors"
              title="Edit"
            >
              <Edit className="h-4 w-4" />
            </button>
            <button
              onClick={() => onDelete(item.id)}
              className="p-1 text-gray-400 hover:text-red-400 transition-colors"
              title="Delete"
            >
              <Trash2 className="h-4 w-4" />
            </button>
          </div>
        </div>

        {item.output && (
          <div className="mb-2">
            <button
              onClick={() => setExpanded(!expanded)}
              className="flex items-center gap-1 text-sm text-blue-400 hover:text-blue-300 transition-colors"
            >
              {expanded ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
              {expanded ? 'Hide' : 'Show'} Output
            </button>
            {expanded && (
              <div className="mt-2 p-3 bg-gray-900 border border-gray-700 rounded text-sm font-mono text-gray-300 whitespace-pre-wrap max-h-64 overflow-y-auto">
                {item.output}
              </div>
            )}
          </div>
        )}

        <div className="flex items-center justify-between text-xs text-gray-500 mt-2">
          <span>{formatDate(item.timestamp)}</span>
          {item.manually_corrected && (
            <span className="text-blue-400">Manually corrected</span>
          )}
        </div>

        {item.detection_strategy_ids && item.detection_strategy_ids.length > 0 && (
          <div className="mt-2 p-2 bg-blue-900/20 border border-blue-700/50 rounded text-sm">
            <span className="font-medium text-blue-300">Detection Strategies: </span>
            <div className="flex flex-wrap gap-1 mt-1">
              {item.detection_strategy_ids.map((strategyId) => (
                <a
                  key={strategyId}
                  href={`https://attack.mitre.org/detectionstrategies/${strategyId}`}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="px-2 py-0.5 bg-blue-900/50 text-blue-300 rounded border border-blue-600 hover:bg-blue-800/50 transition-colors text-xs"
                >
                  {strategyId}
                </a>
              ))}
            </div>
          </div>
        )}

        {item.notes && (
          <div className="mt-2 p-2 bg-gray-900/50 border border-gray-700 rounded text-sm text-gray-300">
            <span className="font-medium">Notes: </span>
            {item.notes}
          </div>
        )}
      </div>
    </div>
  );
}

export default FAAItemCard;




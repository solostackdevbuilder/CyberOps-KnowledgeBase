import { useNavigate } from 'react-router-dom';
import { FileText, Clock } from 'lucide-react';
import type { SessionSource } from '../types';

interface Props {
  source: SessionSource;
  showOperationName: boolean;
}

// Generate consistent color for operation based on ID hash
const getOperationColor = (operationId: string): string => {
  const colors = [
    'bg-blue-600',
    'bg-green-600',
    'bg-purple-600',
    'bg-orange-600',
    'bg-pink-600',
    'bg-yellow-600',
  ];
  const hash = operationId
    .split('')
    .reduce((acc, char) => acc + char.charCodeAt(0), 0);
  return colors[hash % colors.length];
};

// Format timestamp to relative time or date
const formatTime = (timestamp: string): string => {
  try {
    const date = new Date(timestamp);
    const now = new Date();
    const diffMs = now.getTime() - date.getTime();
    const diffMins = Math.floor(diffMs / 60000);
    const diffHours = Math.floor(diffMs / 3600000);
    const diffDays = Math.floor(diffMs / 86400000);

    if (diffMins < 1) return 'just now';
    if (diffMins < 60) return `${diffMins}m ago`;
    if (diffHours < 24) return `${diffHours}h ago`;
    if (diffDays < 7) return `${diffDays}d ago`;

    // Format as date if older than a week
    return date.toLocaleDateString('en-US', {
      month: 'short',
      day: 'numeric',
      year: date.getFullYear() !== now.getFullYear() ? 'numeric' : undefined,
    });
  } catch {
    return timestamp;
  }
};

function SourceItem({ source, showOperationName }: Props) {
  const navigate = useNavigate();

  const handleClick = () => {
    navigate(`/session/${source.session_id}`);
  };

  return (
    <button
      onClick={handleClick}
      className="w-full text-left p-3 bg-gray-900/50 hover:bg-gray-900 border border-gray-700 rounded-md transition-colors group"
    >
      <div className="flex items-start justify-between gap-3">
        <div className="flex-1 min-w-0">
          {showOperationName && source.operation_name ? (
            <div className="flex items-center gap-2 mb-1.5">
              <span
                className={`px-2 py-0.5 rounded text-xs font-medium text-white ${getOperationColor(
                  source.operation_id
                )}`}
              >
                {source.operation_name}
              </span>
              <span className="text-sm font-medium text-gray-300 group-hover:text-white truncate">
                {source.session_title}
              </span>
            </div>
          ) : (
            <div className="flex items-center gap-2 mb-1.5">
              <FileText className="h-4 w-4 text-gray-400 flex-shrink-0" />
              <span className="text-sm font-medium text-gray-300 group-hover:text-white truncate">
                {source.session_title}
              </span>
            </div>
          )}
          <div className="flex items-center gap-1.5 text-xs text-gray-500">
            <Clock className="h-3 w-3" />
            <span>{formatTime(source.timestamp)}</span>
          </div>
        </div>
      </div>
    </button>
  );
}

export default SourceItem;


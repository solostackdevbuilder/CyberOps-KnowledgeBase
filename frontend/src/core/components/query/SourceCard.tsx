import { useNavigate } from 'react-router-dom';
import { FileText, Clock, ChevronRight } from 'lucide-react';

interface SourceCardProps {
  id: string;
  title: string;
  timestamp: string;
  campaignName?: string;
  operationName?: string;
  navigateTo: string;
  showCampaignName?: boolean;
  showOperationName?: boolean;
}

// Generate consistent color for campaign/operation based on ID hash
const getColor = (id: string): string => {
  const colors = [
    'bg-blue-600',
    'bg-green-600',
    'bg-purple-600',
    'bg-orange-600',
    'bg-pink-600',
    'bg-yellow-600',
    'bg-cyan-600',
    'bg-indigo-600',
  ];
  const hash = id.split('').reduce((acc, char) => acc + char.charCodeAt(0), 0);
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

export default function SourceCard({
  id,
  title,
  timestamp,
  campaignName,
  operationName,
  navigateTo,
  showCampaignName = false,
  showOperationName = false,
}: SourceCardProps) {
  const navigate = useNavigate();

  const handleClick = () => {
    navigate(navigateTo);
  };

  const badgeName = campaignName || operationName;
  const showBadge = (showCampaignName && campaignName) || (showOperationName && operationName);

  return (
    <button
      onClick={handleClick}
      className="group w-full text-left bg-gradient-to-br from-gray-800/50 to-gray-900/50 hover:from-gray-800 hover:to-gray-900 border border-gray-700/50 hover:border-blue-500/50 rounded-lg p-4 transition-all duration-200 shadow-md hover:shadow-xl hover:shadow-blue-500/10"
    >
      <div className="flex items-start justify-between gap-3">
        <div className="flex-1 min-w-0">
          {showBadge && badgeName && (
            <div className="flex items-center gap-2 mb-2">
              <span
                className={`px-2.5 py-1 rounded-md text-xs font-semibold text-white shadow-sm ${getColor(
                  id
                )}`}
              >
                {badgeName}
              </span>
            </div>
          )}
          
          <div className="flex items-start gap-2 mb-2">
            <FileText className="h-4 w-4 text-gray-400 group-hover:text-blue-400 flex-shrink-0 mt-0.5 transition-colors" />
            <span className="text-sm font-medium text-gray-300 group-hover:text-white truncate transition-colors">
              {title}
            </span>
          </div>
          
          <div className="flex items-center gap-1.5 text-xs text-gray-500 group-hover:text-gray-400 transition-colors">
            <Clock className="h-3 w-3" />
            <span>{formatTime(timestamp)}</span>
          </div>
        </div>
        
        <ChevronRight className="h-5 w-5 text-gray-600 group-hover:text-blue-400 flex-shrink-0 transition-colors" />
      </div>
    </button>
  );
}


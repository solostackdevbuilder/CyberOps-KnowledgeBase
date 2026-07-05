import { useState } from 'react';
import { ChevronDown, ChevronUp } from 'lucide-react';

interface InsightCardProps {
  icon: React.ReactNode;
  title: string;
  summary: React.ReactNode;
  details?: React.ReactNode;
  iconColor?: string;
  className?: string;
}

function InsightCard({
  icon,
  title,
  summary,
  details,
  iconColor = 'text-blue-400',
  className = '',
}: InsightCardProps) {
  const [isExpanded, setIsExpanded] = useState(false);

  return (
    <div
      className={`bg-gray-800 border border-gray-700 rounded-lg p-6 hover:border-gray-600 transition-all duration-300 ${className}`}
    >
      <div className="flex items-start justify-between mb-4">
        <div className="flex items-center gap-3">
          <div className={`p-2 bg-gray-700/50 rounded-lg ${iconColor}`}>{icon}</div>
          <h3 className="text-lg font-semibold text-white">{title}</h3>
        </div>
        {details && (
          <button
            onClick={() => setIsExpanded(!isExpanded)}
            className="text-gray-400 hover:text-white transition-colors p-1"
            aria-label={isExpanded ? 'Collapse details' : 'Expand details'}
          >
            {isExpanded ? (
              <ChevronUp className="h-5 w-5" />
            ) : (
              <ChevronDown className="h-5 w-5" />
            )}
          </button>
        )}
      </div>

      <div className="text-gray-300">{summary}</div>

      {details && (
        <div
          className={`overflow-hidden transition-all duration-300 ease-in-out ${
            isExpanded ? 'max-h-[2000px] mt-4' : 'max-h-0'
          }`}
        >
          <div className="pt-4 border-t border-gray-700">{details}</div>
        </div>
      )}
    </div>
  );
}

export default InsightCard;


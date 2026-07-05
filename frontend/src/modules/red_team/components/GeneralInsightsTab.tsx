import { useState } from 'react';
import { ChevronDown, ChevronUp, Wrench, Target, AlertTriangle, Users, Calendar } from 'lucide-react';
import type { GeneralInsights } from '../types/insights';

interface GeneralInsightsTabProps {
  insights: GeneralInsights;
}

function CollapsibleSection({
  title,
  icon,
  children,
  defaultExpanded = false,
}: {
  title: string;
  icon: React.ReactNode;
  children: React.ReactNode;
  defaultExpanded?: boolean;
}) {
  const [isExpanded, setIsExpanded] = useState(defaultExpanded);

  return (
    <div className="bg-gray-800 border border-gray-700 rounded-lg p-4 mb-4">
      <button
        onClick={() => setIsExpanded(!isExpanded)}
        className="w-full flex items-center justify-between text-left"
      >
        <div className="flex items-center gap-2">
          {icon}
          <h4 className="text-md font-semibold text-white">{title}</h4>
        </div>
        {isExpanded ? (
          <ChevronUp className="h-5 w-5 text-gray-400" />
        ) : (
          <ChevronDown className="h-5 w-5 text-gray-400" />
        )}
      </button>
      {isExpanded && <div className="mt-4">{children}</div>}
    </div>
  );
}

function GeneralInsightsTab({ insights }: GeneralInsightsTabProps) {
  return (
    <div className="space-y-6">
      {/* Top 10 Tools Used */}
      <CollapsibleSection
        title="Top 10 Tools Used"
        icon={<Wrench className="h-5 w-5 text-purple-400" />}
        defaultExpanded={true}
      >
        <div className="space-y-2">
          {insights.top_tools.length > 0 ? (
            insights.top_tools.map((tool, index) => (
              <div
                key={tool.name}
                className="flex items-center justify-between p-3 bg-gray-900/50 rounded-md hover:bg-gray-900 transition-colors"
              >
                <div className="flex items-center gap-3">
                  <span className="text-sm font-medium text-gray-400 w-6">
                    #{index + 1}
                  </span>
                  <span className="text-gray-300 font-medium">{tool.name}</span>
                </div>
                <span className="text-blue-400 font-semibold">{tool.count}</span>
              </div>
            ))
          ) : (
            <p className="text-gray-500 text-sm">No tools data available</p>
          )}
        </div>
      </CollapsibleSection>

      {/* Targets Discovered */}
      <CollapsibleSection
        title="Targets Discovered"
        icon={<Target className="h-5 w-5 text-green-400" />}
        defaultExpanded={true}
      >
        <div className="flex flex-wrap gap-2">
          {insights.targets_list.length > 0 ? (
            insights.targets_list.map((target) => (
              <span
                key={target}
                className="px-3 py-1.5 bg-green-600/20 border border-green-500/50 rounded-md text-green-300 text-sm font-medium"
              >
                {target}
              </span>
            ))
          ) : (
            <p className="text-gray-500 text-sm">No targets discovered</p>
          )}
        </div>
      </CollapsibleSection>

      {/* Findings Summary */}
      <CollapsibleSection
        title="Findings Summary"
        icon={<AlertTriangle className="h-5 w-5 text-yellow-400" />}
        defaultExpanded={true}
      >
        <div className="space-y-2">
          {insights.findings_summary.length > 0 ? (
            insights.findings_summary.map((finding, index) => (
              <div
                key={index}
                className="flex items-center justify-between p-3 bg-gray-900/50 rounded-md hover:bg-gray-900 transition-colors"
              >
                <span className="text-gray-300 flex-1">{finding.finding}</span>
                <span className="text-yellow-400 font-semibold ml-4">
                  {finding.count}
                </span>
              </div>
            ))
          ) : (
            <p className="text-gray-500 text-sm">No findings available</p>
          )}
        </div>
      </CollapsibleSection>

      {/* Operators Involved */}
      <CollapsibleSection
        title="Operators Involved"
        icon={<Users className="h-5 w-5 text-blue-400" />}
      >
        <div className="flex flex-wrap gap-2">
          {insights.operators.length > 0 ? (
            insights.operators.map((operator) => (
              <span
                key={operator}
                className="px-3 py-1.5 bg-blue-600/20 border border-blue-500/50 rounded-md text-blue-300 text-sm font-medium"
              >
                {operator}
              </span>
            ))
          ) : (
            <p className="text-gray-500 text-sm">No operators listed</p>
          )}
        </div>
      </CollapsibleSection>

      {/* Activity Timeline */}
      <CollapsibleSection
        title="Activity Timeline"
        icon={<Calendar className="h-5 w-5 text-purple-400" />}
      >
        <div className="space-y-3">
          {insights.timeline_data.length > 0 ? (
            insights.timeline_data.map((entry, index) => (
              <div
                key={index}
                className="flex items-center justify-between p-3 bg-gray-900/50 rounded-md"
              >
                <span className="text-gray-300">{entry.date}</span>
                <div className="flex items-center gap-2">
                  <div className="w-32 h-2 bg-gray-700 rounded-full overflow-hidden">
                    <div
                      className="h-full bg-purple-500 rounded-full transition-all"
                      style={{
                        width: `${
                          (entry.session_count /
                            Math.max(
                              ...insights.timeline_data.map((e) => e.session_count)
                            )) *
                          100
                        }%`,
                      }}
                    />
                  </div>
                  <span className="text-purple-400 font-semibold min-w-[3rem] text-right">
                    {entry.session_count}
                  </span>
                </div>
              </div>
            ))
          ) : (
            <p className="text-gray-500 text-sm">No timeline data available</p>
          )}
        </div>
      </CollapsibleSection>
    </div>
  );
}

export default GeneralInsightsTab;


import { CheckCircle, AlertTriangle, Rocket, Shield, ExternalLink } from 'lucide-react';
import type { ExpertAnalysis } from '../types/insights';
import InsightCard from './InsightCard';
import KillChainProgress from './KillChainProgress';
import { useNavigate } from 'react-router-dom';

interface ExpertAnalysisTabProps {
  analysis: ExpertAnalysis;
}

function ExpertAnalysisTab({ analysis }: ExpertAnalysisTabProps) {
  const navigate = useNavigate();

  const getPriorityColor = (priority: 'High' | 'Medium' | 'Low') => {
    switch (priority) {
      case 'High':
        return 'bg-red-600/20 border-red-500/50 text-red-300';
      case 'Medium':
        return 'bg-yellow-600/20 border-yellow-500/50 text-yellow-300';
      case 'Low':
        return 'bg-blue-600/20 border-blue-500/50 text-blue-300';
    }
  };

  const handleSessionClick = (sessionId: string) => {
    navigate(`/session/${sessionId}`);
  };

  return (
    <div className="space-y-6">
      {/* Kill Chain Progress */}
      <KillChainProgress
        killChainProgress={analysis.kill_chain_progress}
        currentPhase={analysis.current_phase}
      />

      {/* Four Main Cards Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        {/* Progress Summary */}
        <InsightCard
          icon={<CheckCircle className="h-6 w-6" />}
          title="Progress Summary"
          iconColor="text-green-400"
          summary={
            <p className="text-gray-300 leading-relaxed">{analysis.progress_summary}</p>
          }
        />

        {/* Gaps Identified */}
        <InsightCard
          icon={<AlertTriangle className="h-6 w-6" />}
          title="Gaps Identified"
          iconColor="text-yellow-400"
          summary={
            <div className="space-y-2">
              {analysis.gaps_identified.length > 0 ? (
                <ul className="list-disc list-inside text-gray-300 space-y-1">
                  {analysis.gaps_identified.slice(0, 3).map((gap, index) => (
                    <li key={index}>{gap}</li>
                  ))}
                  {analysis.gaps_identified.length > 3 && (
                    <li className="text-gray-500 text-sm">
                      +{analysis.gaps_identified.length - 3} more
                    </li>
                  )}
                </ul>
              ) : (
                <p className="text-gray-500">No gaps identified</p>
              )}
            </div>
          }
          details={
            analysis.gaps_identified.length > 0 ? (
              <ul className="list-disc list-inside text-gray-300 space-y-2">
                {analysis.gaps_identified.map((gap, index) => (
                  <li key={index}>{gap}</li>
                ))}
              </ul>
            ) : null
          }
        />

        {/* Next Steps */}
        <InsightCard
          icon={<Rocket className="h-6 w-6" />}
          title="Next Steps"
          iconColor="text-purple-400"
          summary={
            <div className="space-y-2">
              {analysis.next_steps.length > 0 ? (
                <ol className="list-decimal list-inside text-gray-300 space-y-2">
                  {analysis.next_steps.slice(0, 3).map((step, index) => (
                    <li key={index}>
                      <span className="font-medium">{step.step}</span>
                      <span
                        className={`ml-2 px-2 py-0.5 rounded text-xs ${getPriorityColor(
                          step.priority
                        )}`}
                      >
                        {step.priority}
                      </span>
                    </li>
                  ))}
                  {analysis.next_steps.length > 3 && (
                    <li className="text-gray-500 text-sm">
                      +{analysis.next_steps.length - 3} more steps
                    </li>
                  )}
                </ol>
              ) : (
                <p className="text-gray-500">No next steps defined</p>
              )}
            </div>
          }
          details={
            analysis.next_steps.length > 0 ? (
              <div className="space-y-4">
                {analysis.next_steps.map((step, index) => (
                  <div
                    key={index}
                    className="p-3 bg-gray-900/50 rounded-md border border-gray-700"
                  >
                    <div className="flex items-center justify-between mb-2">
                      <span className="text-white font-medium">
                        {index + 1}. {step.step}
                      </span>
                      <span
                        className={`px-2 py-0.5 rounded text-xs font-medium ${getPriorityColor(
                          step.priority
                        )}`}
                      >
                        {step.priority}
                      </span>
                    </div>
                    <p className="text-sm text-gray-400 mt-2">{step.reasoning}</p>
                  </div>
                ))}
              </div>
            ) : null
          }
        />

        {/* Risk Assessment */}
        <InsightCard
          icon={<Shield className="h-6 w-6" />}
          title="Risk Assessment"
          iconColor="text-red-400"
          summary={
            <p className="text-gray-300 leading-relaxed">{analysis.risk_assessment}</p>
          }
        />
      </div>

      {/* Detection Risk Assessment */}
      {analysis.detection_risk_assessment && (
        <div className="bg-blue-900/20 border border-blue-700/50 rounded-lg p-6">
          <h3 className="text-lg font-semibold text-white mb-4 flex items-center">
            <Shield className="h-5 w-5 mr-2 text-blue-400" />
            Detection Risk Assessment
          </h3>
          <p className="text-gray-300 leading-relaxed mb-4">{analysis.detection_risk_assessment}</p>
          
          {analysis.recommended_detection_strategies && analysis.recommended_detection_strategies.length > 0 && (
            <div className="mt-4">
              <h4 className="text-sm font-semibold text-blue-300 mb-2">Recommended Detection Strategies:</h4>
              <div className="flex flex-wrap gap-2">
                {analysis.recommended_detection_strategies.map((strategyId) => (
                  <a
                    key={strategyId}
                    href={`https://attack.mitre.org/detectionstrategies/${strategyId}`}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="px-3 py-1.5 bg-blue-600/20 border border-blue-500/50 rounded-md text-blue-300 text-sm font-medium hover:bg-blue-600/30 transition-colors flex items-center gap-1"
                  >
                    {strategyId}
                    <ExternalLink className="h-3 w-3" />
                  </a>
                ))}
              </div>
            </div>
          )}

          {analysis.detection_coverage_gaps && analysis.detection_coverage_gaps.length > 0 && (
            <div className="mt-4">
              <h4 className="text-sm font-semibold text-yellow-300 mb-2">Coverage Gaps (No Detection Strategies):</h4>
              <div className="flex flex-wrap gap-2">
                {analysis.detection_coverage_gaps.map((techniqueId) => (
                  <span
                    key={techniqueId}
                    className="px-3 py-1.5 bg-yellow-600/20 border border-yellow-500/50 rounded-md text-yellow-300 text-sm font-medium"
                  >
                    {techniqueId}
                  </span>
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      {/* Recommendations */}
      {analysis.recommendations.length > 0 && (
        <div className="bg-gray-800 border border-gray-700 rounded-lg p-6">
          <h3 className="text-lg font-semibold text-white mb-4 flex items-center">
            <Rocket className="h-5 w-5 mr-2 text-purple-400" />
            Recommendations
          </h3>
          <ul className="space-y-2">
            {analysis.recommendations.map((rec, index) => (
              <li
                key={index}
                className="flex items-start gap-3 p-3 bg-gray-900/50 rounded-md hover:bg-gray-900 transition-colors"
              >
                <span className="text-purple-400 font-bold mt-0.5">{index + 1}.</span>
                <span className="text-gray-300 flex-1">{rec}</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* Evidence Sessions */}
      {analysis.evidence_sessions.length > 0 && (
        <div className="bg-gray-800 border border-gray-700 rounded-lg p-6">
          <h3 className="text-lg font-semibold text-white mb-4 flex items-center">
            <ExternalLink className="h-5 w-5 mr-2 text-blue-400" />
            Evidence Sessions
          </h3>
          <div className="flex flex-wrap gap-2">
            {analysis.evidence_sessions.map((sessionId) => (
              <button
                key={sessionId}
                onClick={() => handleSessionClick(sessionId)}
                className="px-3 py-1.5 bg-blue-600/20 border border-blue-500/50 rounded-md text-blue-300 text-sm font-medium hover:bg-blue-600/30 transition-colors flex items-center gap-1"
              >
                {sessionId}
                <ExternalLink className="h-3 w-3" />
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

export default ExpertAnalysisTab;


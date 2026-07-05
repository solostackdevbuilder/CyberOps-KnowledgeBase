import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Target, CheckCircle2, Circle, ArrowRight, Loader2 } from 'lucide-react';
import { getKillChainTimeline } from '../services/api';

interface KillChainVisualizationProps {
  operationId: string;
}

const KILL_CHAIN_PHASES = [
  'Reconnaissance',
  'Initial Access',
  'Execution',
  'Privilege Escalation',
  'Persistence',
  'Defense Evasion',
  'Credential Access',
  'Discovery',
  'Lateral Movement',
  'Collection',
  'Exfiltration',
  'Impact',
];

function KillChainVisualization({ operationId }: KillChainVisualizationProps) {
  const navigate = useNavigate();
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    loadKillChainData();
  }, [operationId]);

  const loadKillChainData = async () => {
    try {
      setLoading(true);
      setError(null);
      const result = await getKillChainTimeline(operationId);
      setData(result);
    } catch (err: any) {
      setError(err.response?.data?.detail || err.message || 'Failed to load kill chain data');
    } finally {
      setLoading(false);
    }
  };

  const getPhaseStatus = (phase: string) => {
    if (!data?.phases) return 'not_started';
    return data.phases[phase]?.status || 'not_started';
  };

  const getPhaseColor = (status: string) => {
    switch (status) {
      case 'completed':
      case 'current':
        return 'bg-green-500/20 border-green-500 text-green-400';
      case 'next':
        return 'bg-yellow-500/20 border-yellow-500 text-yellow-400';
      case 'not_started':
      default:
        return 'bg-gray-700/50 border-gray-600 text-gray-500';
    }
  };

  const getPhaseIcon = (status: string) => {
    switch (status) {
      case 'completed':
        return <CheckCircle2 className="h-5 w-5" />;
      case 'current':
        return <Circle className="h-5 w-5 fill-current" />;
      case 'next':
        return <Circle className="h-5 w-5" />;
      default:
        return <Circle className="h-5 w-5 opacity-50" />;
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center py-12">
        <Loader2 className="h-8 w-8 animate-spin text-blue-500" />
        <span className="ml-3 text-gray-400">Loading kill chain data...</span>
      </div>
    );
  }

  if (error) {
    return (
      <div className="bg-red-900/20 border border-red-500 rounded-lg p-4">
        <p className="text-red-400">{error}</p>
      </div>
    );
  }

  if (!data) {
    return (
      <div className="bg-gray-800 rounded-lg p-8 text-center">
        <Target className="h-12 w-12 text-gray-600 mx-auto mb-4" />
        <p className="text-gray-400">No kill chain data available</p>
      </div>
    );
  }

  return (
    <div className="bg-gray-800 rounded-lg p-6">
      <div className="mb-6">
        <h2 className="text-xl font-semibold text-white mb-2">Kill Chain Progress</h2>
        <p className="text-gray-400 text-sm">{data.operation_name}</p>
      </div>

      {/* Kill Chain Phases */}
      <div className="space-y-3">
        {KILL_CHAIN_PHASES.map((phase, index) => {
          const status = getPhaseStatus(phase);
          const isLast = index === KILL_CHAIN_PHASES.length - 1;

          return (
            <div key={phase} className="flex items-center gap-4">
              {/* Phase Card */}
              <div
                className={`${getPhaseColor(status)} border rounded-lg p-4 flex-1 flex items-center justify-between`}
              >
                <div className="flex items-center gap-3">
                  {getPhaseIcon(status)}
                  <div>
                    <div className="font-semibold">{phase}</div>
                    <div className="text-xs mt-1 opacity-75 capitalize">
                      {status.replace('_', ' ')}
                    </div>
                  </div>
                </div>
                {status === 'current' && (
                  <span className="text-xs bg-green-500/20 px-2 py-1 rounded">
                    Current Phase
                  </span>
                )}
              </div>

              {/* Arrow */}
              {!isLast && (
                <ArrowRight className="h-5 w-5 text-gray-600 flex-shrink-0" />
              )}
            </div>
          );
        })}
      </div>

      {/* Timeline Events */}
      {data.timeline && data.timeline.length > 0 && (
        <div className="mt-8 pt-6 border-t border-gray-700">
          <h3 className="text-lg font-semibold text-white mb-4">Session Timeline</h3>
          <div className="space-y-2 max-h-64 overflow-y-auto">
            {data.timeline.map((event: any, idx: number) => (
              <div
                key={idx}
                onClick={() => navigate(`/session/${event.session_id}`)}
                className="bg-gray-700 rounded-lg p-3 cursor-pointer hover:bg-gray-600 transition-colors"
              >
                <div className="flex items-center justify-between">
                  <div>
                    <div className="font-medium text-white">{event.session_title}</div>
                    <div className="text-sm text-gray-400 mt-1">
                      {new Date(event.timestamp).toLocaleString()}
                    </div>
                  </div>
                  <div className="flex gap-2 text-xs">
                    {event.tools && event.tools.length > 0 && (
                      <span className="text-blue-400">
                        {event.tools.length} tool{event.tools.length !== 1 ? 's' : ''}
                      </span>
                    )}
                    {event.targets && event.targets.length > 0 && (
                      <span className="text-green-400">
                        {event.targets.length} target{event.targets.length !== 1 ? 's' : ''}
                      </span>
                    )}
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

export default KillChainVisualization;






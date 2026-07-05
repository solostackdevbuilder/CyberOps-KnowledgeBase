import { Check, Circle } from 'lucide-react';

interface KillChainProgressProps {
  killChainProgress: Record<string, 'completed' | 'current' | 'next'>;
  currentPhase: string;
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

function KillChainProgress({
  killChainProgress,
  currentPhase,
}: KillChainProgressProps) {
  const getPhaseStatus = (phase: string): 'completed' | 'current' | 'next' => {
    return killChainProgress[phase] || 'next';
  };

  const getPhaseColor = (status: 'completed' | 'current' | 'next') => {
    switch (status) {
      case 'completed':
        return 'bg-green-500 text-white';
      case 'current':
        return 'bg-blue-500 text-white animate-pulse';
      case 'next':
        return 'bg-gray-600 text-gray-300';
    }
  };

  const getPhaseIcon = (status: 'completed' | 'current' | 'next') => {
    if (status === 'completed') {
      return <Check className="h-4 w-4" />;
    }
    return <Circle className="h-4 w-4" />;
  };

  return (
    <div className="bg-gray-800 border border-gray-700 rounded-lg p-6">
      <h3 className="text-lg font-semibold text-white mb-4 flex items-center">
        <span className="mr-2">Kill Chain Progress</span>
        <span className="text-sm font-normal text-gray-400 ml-2">
          Current: {currentPhase}
        </span>
      </h3>
      <div className="overflow-x-auto pb-2">
        <div className="flex gap-2 min-w-max">
          {KILL_CHAIN_PHASES.map((phase, index) => {
            const status = getPhaseStatus(phase);
            const isCurrent = status === 'current';
            return (
              <div
                key={phase}
                className={`flex flex-col items-center min-w-[120px] ${
                  index < KILL_CHAIN_PHASES.length - 1 ? 'mr-2' : ''
                }`}
              >
                <div
                  className={`w-full h-2 rounded-full mb-2 ${getPhaseColor(status)}`}
                  title={phase}
                />
                <div
                  className={`flex items-center justify-center w-8 h-8 rounded-full ${getPhaseColor(
                    status
                  )} mb-2`}
                >
                  {getPhaseIcon(status)}
                </div>
                <span
                  className={`text-xs text-center ${
                    isCurrent
                      ? 'text-blue-400 font-semibold'
                      : status === 'completed'
                      ? 'text-green-400'
                      : 'text-gray-500'
                  }`}
                >
                  {phase}
                </span>
              </div>
            );
          })}
        </div>
      </div>
      <div className="mt-4 flex items-center justify-center gap-4 text-xs text-gray-400">
        <div className="flex items-center gap-1">
          <div className="w-3 h-3 rounded-full bg-green-500" />
          <span>Completed</span>
        </div>
        <div className="flex items-center gap-1">
          <div className="w-3 h-3 rounded-full bg-blue-500 animate-pulse" />
          <span>Current</span>
        </div>
        <div className="flex items-center gap-1">
          <div className="w-3 h-3 rounded-full bg-gray-600" />
          <span>Pending</span>
        </div>
      </div>
    </div>
  );
}

export default KillChainProgress;


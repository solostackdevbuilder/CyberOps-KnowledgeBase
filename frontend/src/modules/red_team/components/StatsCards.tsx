import { useEffect, useState } from 'react';
import { FileText, Target, AlertCircle, Wrench } from 'lucide-react';

interface StatsCardsProps {
  totalSessions: number;
  totalTargets: number;
  totalFindings: number;
  totalTools: number;
}

interface StatCardProps {
  icon: React.ReactNode;
  label: string;
  value: number;
  gradient: string;
}

function StatCard({ icon, label, value, gradient }: StatCardProps) {
  const [displayValue, setDisplayValue] = useState(0);

  useEffect(() => {
    // Animate counting up
    const duration = 1000; // 1 second
    const steps = 30;
    const increment = value / steps;
    let current = 0;
    let step = 0;

    const timer = setInterval(() => {
      step++;
      current = Math.min(value, Math.round(increment * step));
      setDisplayValue(current);

      if (step >= steps || current >= value) {
        setDisplayValue(value);
        clearInterval(timer);
      }
    }, duration / steps);

    return () => clearInterval(timer);
  }, [value]);

  return (
    <div
      className={`bg-gradient-to-br ${gradient} rounded-lg p-6 border border-gray-700/50 shadow-lg hover:shadow-xl transition-all duration-300 hover:scale-105`}
    >
      <div className="flex items-center justify-between mb-4">
        <div className="p-2 bg-white/10 rounded-lg">{icon}</div>
      </div>
      <div className="text-4xl font-bold text-white mb-1">{displayValue}</div>
      <div className="text-sm text-gray-300 font-medium">{label}</div>
    </div>
  );
}

function StatsCards({
  totalSessions,
  totalTargets,
  totalFindings,
  totalTools,
}: StatsCardsProps) {
  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 mb-8">
      <StatCard
        icon={<FileText className="h-6 w-6 text-white" />}
        label="Total Sessions"
        value={totalSessions}
        gradient="from-blue-600/20 to-blue-800/20"
      />
      <StatCard
        icon={<Target className="h-6 w-6 text-white" />}
        label="Total Targets"
        value={totalTargets}
        gradient="from-green-600/20 to-green-800/20"
      />
      <StatCard
        icon={<AlertCircle className="h-6 w-6 text-white" />}
        label="Total Findings"
        value={totalFindings}
        gradient="from-yellow-600/20 to-yellow-800/20"
      />
      <StatCard
        icon={<Wrench className="h-6 w-6 text-white" />}
        label="Total Tools"
        value={totalTools}
        gradient="from-purple-600/20 to-purple-800/20"
      />
    </div>
  );
}

export default StatsCards;


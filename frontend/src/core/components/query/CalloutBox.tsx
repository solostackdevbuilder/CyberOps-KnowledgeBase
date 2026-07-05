import React from 'react';
import { AlertTriangle, Info, CheckCircle, AlertCircle, Lightbulb } from 'lucide-react';

type CalloutType = 'info' | 'warning' | 'error' | 'success' | 'tip';

interface CalloutBoxProps {
  type: CalloutType;
  title?: string;
  children: React.ReactNode;
}

const calloutConfig: Record<
  CalloutType,
  {
    icon: React.ComponentType<{ className?: string }>;
    bgColor: string;
    borderColor: string;
    iconColor: string;
    titleColor: string;
    textColor: string;
  }
> = {
  info: {
    icon: Info,
    bgColor: 'bg-blue-500/10',
    borderColor: 'border-blue-500/30',
    iconColor: 'text-blue-400',
    titleColor: 'text-blue-300',
    textColor: 'text-blue-200',
  },
  warning: {
    icon: AlertTriangle,
    bgColor: 'bg-yellow-500/10',
    borderColor: 'border-yellow-500/30',
    iconColor: 'text-yellow-400',
    titleColor: 'text-yellow-300',
    textColor: 'text-yellow-200',
  },
  error: {
    icon: AlertCircle,
    bgColor: 'bg-red-500/10',
    borderColor: 'border-red-500/30',
    iconColor: 'text-red-400',
    titleColor: 'text-red-300',
    textColor: 'text-red-200',
  },
  success: {
    icon: CheckCircle,
    bgColor: 'bg-green-500/10',
    borderColor: 'border-green-500/30',
    iconColor: 'text-green-400',
    titleColor: 'text-green-300',
    textColor: 'text-green-200',
  },
  tip: {
    icon: Lightbulb,
    bgColor: 'bg-purple-500/10',
    borderColor: 'border-purple-500/30',
    iconColor: 'text-purple-400',
    titleColor: 'text-purple-300',
    textColor: 'text-purple-200',
  },
};

export default function CalloutBox({ type, title, children }: CalloutBoxProps) {
  const config = calloutConfig[type];
  const Icon = config.icon;

  return (
    <div
      className={`${config.bgColor} ${config.borderColor} border-l-4 rounded-r-lg p-4 my-4 shadow-lg`}
    >
      <div className="flex items-start gap-3">
        <Icon className={`h-5 w-5 ${config.iconColor} flex-shrink-0 mt-0.5`} />
        <div className="flex-1 min-w-0">
          {title && (
            <h4 className={`font-semibold ${config.titleColor} mb-2`}>{title}</h4>
          )}
          <div className={config.textColor}>{children}</div>
        </div>
      </div>
    </div>
  );
}






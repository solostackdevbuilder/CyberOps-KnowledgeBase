export interface GeneralInsights {
  total_sessions: number;
  total_targets: number;
  total_findings: number;
  total_tools: number;
  top_tools: Array<{ name: string; count: number }>;
  targets_list: string[];
  findings_summary: Array<{ finding: string; count: number }>;
  operators: string[];
  timeline_data: Array<{ date: string; session_count: number }>;
  generated_at: string;
}

export interface NextStep {
  step: string;
  priority: 'High' | 'Medium' | 'Low';
  reasoning: string;
}

export interface ExpertAnalysis {
  current_phase: string;
  phase_confidence: 'High' | 'Medium' | 'Low';
  kill_chain_progress: Record<string, 'completed' | 'current' | 'next'>;
  progress_summary: string;
  gaps_identified: string[];
  recommendations: string[];
  next_steps: NextStep[];
  risk_assessment: string;
  detection_risk_assessment?: string;
  recommended_detection_strategies?: string[]; // DET#### IDs
  detection_coverage_gaps?: string[]; // T#### IDs
  evidence_sessions: string[];
  generated_at: string;
}

export interface InsightsResponse {
  general_insights: GeneralInsights;
  expert_analysis: ExpertAnalysis;
  scope: string | string[];
  generated_at: string;
}


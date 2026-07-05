export interface Screenshot {
  filename: string;
  timestamp: string;
  description?: string;
  source_url?: string;
  source_title?: string;
  source_domain?: string;
}

export interface ScreenshotExtraction {
  filename: string;
  path: string;
  uploaded_at: string;
  extracted_text?: string;
  analysis?: string;
  extraction_status: 'success' | 'failed' | 'no_text' | 'not_supported';
  error_message?: string;
}

export interface Operation {
  id: string;
  name: string;
  description?: string;
  created_at: string;
  status: string;
  session_ids: string[];
}

export interface OperationCreate {
  name: string;
  description?: string;
}

export interface OperationUpdate {
  name?: string;
  description?: string;
  status?: string;
}

export interface Session {
  id: string;
  title: string;
  description?: string;
  tags: string[];
  created_at: string;
  updated_at: string;
  terminal_content: string;
  screenshots: Screenshot[];
  screenshot_extractions?: ScreenshotExtraction[];
  operation_id: string;
  operator_name: string;
  target?: string[];
  tools?: string[];
  findings?: string[];
  /** Primary tool that produced this session's content (e.g. "bloodhound", "crackmapexec"). */
  primary_tool?: string | null;
  /** Minutes the operator spent documenting this session. */
  documentation_time_minutes?: number | null;
}

export interface SessionCreate {
  title: string;
  description?: string;
  tags: string[];
  terminal_content: string;
  screenshots?: Screenshot[];
  operation_id: string;
  operator_name: string;
  target?: string[];
  tools?: string[];
  findings?: string[];
  primary_tool?: string | null;
  documentation_time_minutes?: number | null;
}

export interface SessionUpdate {
  title?: string;
  description?: string;
  tags?: string[];
  terminal_content?: string;
  target?: string[];
  tools?: string[];
  findings?: string[];
  primary_tool?: string | null;
  documentation_time_minutes?: number | null;
}

export interface ExtractedMetadata {
  targets: string[];
  tools: string[];
  findings: string[];
}

export interface QueryRequest {
  question: string;
  operation_id?: string | null;
  session_ids?: string[];
}

export interface QueryResponse {
  answer: string;
  sources: SessionSource[];
  scope: string;
  session_count: number;
  operation_count?: number;
  // Hallucination guard validation fields
  confidence?: number;
  validation_warnings?: string[];
  recommended_action?: 'accept' | 'review' | 'reject';
}

export interface FAAAnalysisResponse {
  items: FAAItem[];
  validation_summary: {
    total_items_from_llm: number;
    validated_items: number;
    dropped_items: number;
    average_confidence: number;
    items_needing_review: number;
    mitre_corrections_made: number;
    grounding_issues: number;
  };
  warnings: string[];
  dropped_count: number;
}

export interface SessionSource {
  session_id: string;
  session_title: string;
  operation_id: string;
  operation_name: string;
  timestamp: string;
}

// Re-export OperationSummary from core (it's shared)
export type { OperationSummary } from '../../../core/types/settings';

export interface DetectionStrategy {
  id: string; // DET####
  name: string;
  description?: string;
  techniques: string[]; // T####
  tactics: string[];
  platforms: string[];
  domain: string;
  url?: string;
}

export interface FAAItem {
  id: string;
  session_id: string;
  classification: 'action' | 'finding';
  content: string;
  output?: string;
  mitre_technique?: string;
  mitre_tactic?: string;
  detection_strategy_ids?: string[]; // DET#### IDs
  severity?: 'critical' | 'high' | 'medium' | 'low';
  timestamp: string;
  source: 'terminal' | 'screenshot' | 'manual';
  confidence_score: number;
  manually_corrected: boolean;
  notes?: string;
  created_at: string;
  updated_at: string;
}

export interface FAAItemCreate {
  session_id: string;
  classification: 'action' | 'finding';
  content: string;
  output?: string;
  mitre_technique?: string;
  mitre_tactic?: string;
  severity?: 'critical' | 'high' | 'medium' | 'low';
  timestamp: string;
  source?: 'terminal' | 'screenshot' | 'manual';
  notes?: string;
}

export interface FAAItemUpdate {
  classification?: 'action' | 'finding';
  content?: string;
  output?: string;
  mitre_technique?: string;
  mitre_tactic?: string;
  severity?: 'critical' | 'high' | 'medium' | 'low';
  notes?: string;
}


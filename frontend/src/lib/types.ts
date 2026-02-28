// TypeScript interfaces matching backend DTOs

export interface User {
  id: string;
  email: string;
  display_name: string | null;
  role: 'coach' | 'coachee' | 'admin';
  coach_id: string | null;
  airtable_user_record_id: string | null;
  last_login: string | null;
}

export interface QuoteObject {
  speaker_label: string | null;
  quote_text: string;
  meeting_id: string | null;
  transcript_id: string | null;
  span_id: string | null;
}

export interface CoachingItem {
  pattern_id: string;
  message: string;
  quotes: QuoteObject[];
}

export interface MicroExperiment {
  experiment_id: string;
  title: string;
  instruction: string;
  success_marker: string;
  pattern_id: string;
  quotes: QuoteObject[];
}

export interface RunStatus {
  run_id: string;
  status: 'queued' | 'running' | 'complete' | 'error';
  gate1_pass: boolean | null;
  analysis_type: string | null;
  error: Record<string, unknown> | null;
  strengths: CoachingItem[];
  focus: CoachingItem | null;
  micro_experiment: MicroExperiment | null;
  pattern_snapshot: Record<string, unknown>[] | null;
  evaluation_summary: Record<string, unknown> | null;
  experiment_tracking: Record<string, unknown> | null;
}

export interface RunRequestStatus {
  run_request_id: string;
  status: string;
  run_id: string | null;
  error: Record<string, unknown> | null;
}

export interface Experiment {
  experiment_record_id: string;
  experiment_id: string;
  title: string;
  instruction: string;
  success_marker: string;
  pattern_id: string;
  status: 'none' | 'assigned' | 'active' | 'completed' | 'abandoned';
  created_at: string | null;
}

export interface ActiveExperiment {
  experiment: Experiment | null;
  recent_events: Record<string, unknown>[];
}

export interface ClientSummary {
  user: User;
  active_experiment: Experiment | null;
  baseline_pack_status: string | null;
  recent_runs: Record<string, unknown>[];
}

export interface TranscriptUpload {
  transcript_id: string;
  speaker_labels: string[];
  word_count: number | null;
  meeting_type: string | null;
  meeting_date: string | null;
}

export interface TranscriptListItem {
  transcript_id: string;
  title: string | null;
  meeting_type: string | null;
  meeting_date: string | null;
  created_at: string | null;
}

export interface BaselinePack {
  baseline_pack_id: string;
  status: string;
  run_id?: string | null;
  strengths?: CoachingItem[];
  focus?: CoachingItem | null;
  micro_experiment?: MicroExperiment | null;
}

export interface CoacheeListItem {
  id: string;
  email: string;
  display_name: string | null;
  airtable_user_record_id: string | null;
}

export interface CoacheeSummary {
  coachee: CoacheeListItem;
  active_baseline_pack: Record<string, unknown> | null;
  active_experiment: Experiment | null;
  recent_runs: Record<string, unknown>[];
}

export interface AdminUser {
  id: string;
  email: string;
  display_name: string | null;
  role: string;
  coach_id: string | null;
  created_at: string | null;
  last_login: string | null;
}

export type TargetRole =
  | 'chair'
  | 'presenter'
  | 'participant'
  | 'manager_1to1'
  | 'report_1to1';

export type MeetingType =
  | 'exec_staff'
  | 'board'
  | 'all_hands'
  | 'cross_functional'
  | 'project_review'
  | 'sprint_planning'
  | 'sprint_retrospective'
  | 'stand_up'
  | 'incident_review'
  | 'client_call'
  | 'one_on_one'
  | 'other';

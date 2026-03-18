// TypeScript interfaces matching backend DTOs

export interface User {
  id: string;
  email: string;
  display_name: string | null;
  role: 'coach' | 'coachee' | 'admin';
  coach_id: string | null;
  airtable_user_record_id: string | null;
  profile_photo_url: string | null;
  last_login: string | null;
}

export interface QuoteObject {
  speaker_label: string | null;
  quote_text: string;
  meeting_id: string | null;
  transcript_id: string | null;
  span_id: string | null;
  start_timestamp: string | null;
  meeting_label: string | null;
  is_target_speaker: boolean | null;
}

export interface CoachingItem {
  pattern_id: string;
  message: string;
  quotes: QuoteObject[];
  suggested_rewrite?: string | null;
  rewrite_for_span_id?: string | null;
  additional_quotes?: QuoteObject[];
}

export interface MicroExperiment {
  experiment_id: string;
  title: string;
  instruction: string;
  success_marker: string;
  pattern_id: string;
  quotes: QuoteObject[];
}

export interface ExperimentDetection {
  experiment_id: string;
  attempt: 'yes' | 'partial' | 'no';
  count_attempts: number;
  quotes: QuoteObject[];
  coaching_note: string | null;
  suggested_rewrite: string | null;
  rewrite_for_span_id: string | null;
}

export interface PatternSnapshotItem {
  pattern_id: string;
  tier: number | null;
  evaluable_status: string;
  numerator?: number;
  denominator?: number;
  ratio?: number;
  balance_assessment?: string;
  notes?: string;
  quotes: QuoteObject[];
  coaching_note?: string | null;
  suggested_rewrite?: string | null;
  rewrite_for_span_id?: string | null;
  success_span_ids?: string[];
}

export interface RunStatus {
  run_id: string;
  status: 'queued' | 'running' | 'complete' | 'error';
  gate1_pass: boolean | null;
  analysis_type: string | null;
  baseline_pack_id: string | null;
  target_speaker_label: string | null;
  error: Record<string, unknown> | null;
  strengths: CoachingItem[];
  focus: CoachingItem | null;
  micro_experiment: MicroExperiment | null;
  pattern_snapshot: PatternSnapshotItem[] | null;
  evaluation_summary: Record<string, unknown> | null;
  experiment_tracking: Record<string, unknown> | null;
  experiment_detection: ExperimentDetection | null;
  human_confirmation: 'confirmed_attempt' | 'confirmed_no_attempt' | null;
  active_experiment_detail: Experiment | null;
  active_experiment_events: Record<string, unknown>[];
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
  status: 'proposed' | 'active' | 'completed' | 'abandoned' | 'parked';
  created_at: string | null;
  attempt_count: number | null;
  meeting_count: number | null;
  started_at: string | null;
  ended_at: string | null;
}

export interface ExperimentActionResponse {
  experiment_record_id: string;
  status: string;
  message: string;
}

export interface HumanConfirmResponse {
  event_record_id: string;
  experiment_record_id: string;
  confirmed: boolean;
}

export interface ActiveExperiment {
  experiment: Experiment | null;
  recent_events: Record<string, unknown>[];
}

export interface RankedExperimentItem {
  experiment: Experiment;
  origin: 'proposed' | 'parked';
  rank: number;
}

export interface ExperimentOptions {
  proposed: Experiment[];
  parked: Experiment[];
  ranked: RankedExperimentItem[];
  at_park_cap: boolean;
}

export interface ClientSummary {
  user: User;
  active_experiment: Experiment | null;
  proposed_experiments: Experiment[];
  parked_experiment_count: number;
  baseline_pack_status: string | null;
  baseline_pack_id: string | null;
  recent_runs: Record<string, unknown>[];
}

export interface TranscriptUpload {
  transcript_id: string;
  speaker_labels: string[];
  word_count: number | null;
  meeting_type: string | null;
  meeting_date: string | null;
  detected_date: string | null;
  speaker_previews: Record<string, string[]>;
}

export interface TranscriptListItem {
  transcript_id: string;
  title: string | null;
  meeting_type: string | null;
  meeting_date: string | null;
  created_at: string | null;
  speaker_labels: string[];
}

export interface BaselinePackMeeting {
  run_id: string | null;
  title: string | null;
  meeting_date: string | null;
  meeting_type: string | null;
  target_role: string | null;
  sub_run_strengths?: CoachingItem[];
  sub_run_focus?: CoachingItem | null;
  sub_run_pattern_snapshot?: Record<string, unknown>[];
}

export interface BaselinePack {
  baseline_pack_id: string;
  status: string;
  target_speaker_label?: string | null;
  run_id?: string | null;
  strengths?: CoachingItem[];
  focus?: CoachingItem | null;
  micro_experiment?: MicroExperiment | null;
  pattern_snapshot?: Record<string, unknown>[];
  meetings?: BaselinePackMeeting[];
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
  proposed_experiments: Experiment[];
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

export interface RunMeta {
  run_id: string;
  analysis_type: string | null;
  title: string | null;
  transcript_id: string | null;
  meeting_date: string | null;
  meeting_type: string | null;
  target_role: string | null;
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

export interface PatternDataPoint {
  pattern_id: string;
  ratio: number;
  opportunity_count: number;
}

export interface RunHistoryPoint {
  run_id: string;
  meeting_date: string | null;
  is_baseline: boolean;
  analysis_type: string | null;
  patterns: PatternDataPoint[];
}

export interface PastExperiment {
  experiment_record_id: string;
  experiment_id: string;
  title: string;
  pattern_id: string;
  status: string;
  started_at: string | null;
  ended_at: string | null;
  attempt_count: number | null;
  meeting_count: number | null;
}

export interface ClientProgress {
  pattern_history: RunHistoryPoint[];
  past_experiments: PastExperiment[];
  trend_window_size: number;
}

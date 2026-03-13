// lib/api.ts — Typed fetch wrapper for backend API

// All API calls use same-origin; Next.js rewrites proxy /api/* to the backend.
// This keeps cookies first-party and avoids third-party cookie blocking.
const BASE_URL = '';

class ApiError extends Error {
  constructor(
    public status: number,
    public detail: string,
    message?: string
  ) {
    super(message ?? detail);
  }
}

async function request<T>(
  path: string,
  options: RequestInit = {}
): Promise<T> {
  const res = await fetch(`${BASE_URL}${path}`, {
    credentials: 'include',
    headers: {
      'Content-Type': 'application/json',
      ...(options.headers ?? {}),
    },
    ...options,
  });

  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = body.detail ?? body.message ?? detail;
    } catch {
      // ignore parse errors
    }
    throw new ApiError(res.status, detail);
  }

  // Handle 204 No Content
  if (res.status === 204) return undefined as unknown as T;
  return res.json() as Promise<T>;
}

// ── Auth ──────────────────────────────────────────────────────────────────────

import type {
  User,
  ClientSummary,
  RunStatus,
  RunRequestStatus,
  TranscriptUpload,
  TranscriptListItem,
  BaselinePack,
  ActiveExperiment,
  Experiment,
  ExperimentActionResponse,
  ExperimentOptions,
  HumanConfirmResponse,
  CoacheeListItem,
  CoacheeSummary,
  AdminUser,
  ClientProgress,
  RunMeta,
} from './types';

export const api = {
  // Auth
  me(): Promise<User> {
    return request('/api/me');
  },
  logout(): Promise<void> {
    return request('/api/auth/logout', { method: 'POST' });
  },

  // Client summary
  clientSummary(): Promise<ClientSummary> {
    return request('/api/client/summary');
  },
  
  // Client progress
  getClientProgress(): Promise<ClientProgress> {
    return request('/api/client/progress');
  },

  // Run metadata (for detail page header)
  getRunMeta(runId: string): Promise<RunMeta> {
    return request(`/api/client/runs/${runId}/meta`);
  },

  // Delete a single-meeting run
  deleteRun(runId: string): Promise<{ deleted: boolean; run_id: string }> {
    return request(`/api/client/runs/${runId}`, { method: 'DELETE' });
  },

  // Transcripts
  uploadTranscript(formData: FormData): Promise<TranscriptUpload> {
    return request('/api/transcripts', {
      method: 'POST',
      headers: {}, // let browser set Content-Type with boundary
      body: formData,
    });
  },
  listTranscripts(): Promise<TranscriptListItem[]> {
    return request('/api/transcripts');
  },
  updateTranscriptDate(transcriptId: string, meetingDate: string | null): Promise<{ transcript_id: string; updated: boolean }> {
    return request(`/api/transcripts/${transcriptId}`, {
      method: 'PATCH',
      body: JSON.stringify({ meeting_date: meetingDate ?? '' }),
    });
  },

  // Runs
  getRun(runId: string): Promise<RunStatus> {
    return request(`/api/runs/${runId}`);
  },
  getRunRequest(runRequestId: string): Promise<RunRequestStatus> {
    return request(`/api/run_requests/${runRequestId}`);
  },

  // Single meeting analysis
  enqueueSingleMeeting(body: {
    transcript_id: string;
    target_speaker_name: string;
    target_speaker_label: string;
    target_role: string;
  }): Promise<RunRequestStatus> {
    return request('/api/coachees/me/analyze', {
      method: 'POST',
      body: JSON.stringify(body),
    });
  },

  coachEnqueueAnalysis(coacheeAuthId: string, body: {
    transcript_id: string;
    target_speaker_name: string;
    target_speaker_label: string;
    target_role: string;
  }): Promise<RunRequestStatus> {
    return request(`/api/coach/coachees/${coacheeAuthId}/analyze`, {
      method: 'POST',
      body: JSON.stringify(body),
    });
  },

  // Baseline packs
  createBaselinePack(body: {
    transcript_ids: string[];
    target_speaker_name: string;
    target_speaker_label: string;
    target_role: string;
  }): Promise<{ baseline_pack_id: string; status: string }> {
    return request('/api/baseline_packs', {
      method: 'POST',
      body: JSON.stringify(body),
    });
  },
  buildBaselinePack(id: string): Promise<{ baseline_pack_id: string; job_id: string; status: string }> {
    return request(`/api/baseline_packs/${id}/build`, { method: 'POST' });
  },
  getBaselinePack(id: string): Promise<BaselinePack> {
    return request(`/api/baseline_packs/${id}`);
  },

  // Experiments — active
  getActiveExperiment(): Promise<ActiveExperiment> {
    return request('/api/client/active_experiment');
  },

  // Experiments — proposed queue
  getProposedExperiments(): Promise<Experiment[]> {
    return request('/api/client/experiments/proposed');
  },

  // Experiment lifecycle actions
  acceptExperiment(experimentRecordId: string): Promise<ExperimentActionResponse> {
    return request(`/api/client/experiments/${experimentRecordId}/accept`, {
      method: 'POST',
    });
  },
  completeExperiment(experimentRecordId: string): Promise<ExperimentActionResponse> {
    return request(`/api/client/experiments/${experimentRecordId}/complete`, {
      method: 'POST',
    });
  },
  parkExperiment(experimentRecordId: string): Promise<ExperimentActionResponse> {
    return request(`/api/client/experiments/${experimentRecordId}/park`, {
      method: 'POST',
    });
  },
  resumeExperiment(experimentRecordId: string): Promise<ExperimentActionResponse> {
    return request(`/api/client/experiments/${experimentRecordId}/resume`, {
      method: 'POST',
    });
  },
  discardExperiment(experimentRecordId: string): Promise<ExperimentActionResponse> {
    return request(`/api/client/experiments/${experimentRecordId}/discard`, {
      method: 'POST',
    });
  },
  abandonExperiment(experimentRecordId: string): Promise<ExperimentActionResponse> {
    // Legacy alias — calls park endpoint
    return request(`/api/client/experiments/${experimentRecordId}/park`, {
      method: 'POST',
    });
  },
  getExperimentOptions(): Promise<ExperimentOptions> {
    return request('/api/client/experiments/options');
  },

  // Human confirmation of experiment attempt
  confirmExperimentAttempt(
    experimentRecordId: string,
    runId: string,
    confirmed: boolean
  ): Promise<HumanConfirmResponse> {
    return request(`/api/client/experiments/${experimentRecordId}/confirm_attempt`, {
      method: 'POST',
      body: JSON.stringify({ run_id: runId, confirmed }),
    });
  },

  // Legacy experiment update (PATCH-based, kept for backward compatibility)
  updateExperiment(
    experimentRecordId: string,
    action: 'complete' | 'abandon'
  ): Promise<Experiment> {
    return request(`/api/experiments/${experimentRecordId}`, {
      method: 'PATCH',
      body: JSON.stringify({ action }),
    });
  },

  // Legacy confirm attempt (kept for backward compatibility)
  confirmAttempt(runId: string, confirmed: boolean): Promise<void> {
    return request(`/api/runs/${runId}/experiment_attempt`, {
      method: 'PATCH',
      body: JSON.stringify({ confirmed }),
    });
  },

  // Coach
  listCoachees(): Promise<CoacheeListItem[]> {
    return request('/api/coach/coachees');
  },
  getCoacheeSummary(coacheeId: string): Promise<CoacheeSummary> {
    return request(`/api/coach/coachees/${coacheeId}/summary`);
  },
  createCoacheeInvite(): Promise<{ invite_url: string; token: string }> {
    return request('/api/invites/coachee', { method: 'POST' });
  },
  searchUsers(q: string): Promise<CoacheeListItem[]> {
    return request(`/api/coach/users/search?q=${encodeURIComponent(q)}`);
  },
  assignCoachee(userId: string): Promise<CoacheeListItem> {
    return request('/api/coach/assign_coachee', {
      method: 'POST',
      body: JSON.stringify({ user_id: userId }),
    });
  },
  getCoacheeProgress(coacheeId: string): Promise<ClientProgress> {
    return request(`/api/coach/coachees/${coacheeId}/progress`);
  },

  // Admin
  listAdminUsers(): Promise<AdminUser[]> {
    return request('/api/admin/users');
  },
  promoteToCoach(userId: string): Promise<User> {
    return request(`/api/admin/users/${userId}/promote`, { method: 'POST' });
  },
  assignCoach(coacheeId: string, coachId: string): Promise<User> {
    return request(`/api/admin/users/${coacheeId}/assign_coach`, {
      method: 'POST',
      body: JSON.stringify({ coach_id: coachId }),
    });
  },
};

export { ApiError };

// lib/api.ts — Typed fetch wrapper for backend API

const BASE_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

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
  CoacheeListItem,
  CoacheeSummary,
  AdminUser,
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

  // Experiments
  getActiveExperiment(): Promise<ActiveExperiment> {
    return request('/api/coachees/me/experiment');
  },
  updateExperiment(
    experimentRecordId: string,
    action: 'complete' | 'abandon'
  ): Promise<Experiment> {
    return request(`/api/experiments/${experimentRecordId}`, {
      method: 'PATCH',
      body: JSON.stringify({ action }),
    });
  },
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
    return request(`/api/coach/coachees/${coacheeId}`);
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

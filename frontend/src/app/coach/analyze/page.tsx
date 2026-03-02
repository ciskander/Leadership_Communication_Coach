'use client';

import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { api } from '@/lib/api';
import { TranscriptUploadPanel } from '@/components/TranscriptUpload';
import { SpeakerChips } from '@/components/SpeakerChips';
import type { CoacheeListItem, TargetRole } from '@/lib/types';

const ROLE_OPTIONS = [
  { value: 'chair',        label: 'Chair / Facilitator' },
  { value: 'presenter',    label: 'Presenter' },
  { value: 'participant',  label: 'Participant' },
  { value: 'manager_1to1', label: '1:1 Manager' },
  { value: 'report_1to1',  label: '1:1 Report' },
];

export default function CoachAnalyzePage() {
  const router = useRouter();
  const [coachees, setCoachees] = useState<CoacheeListItem[]>([]);
  const [loadingCoachees, setLoadingCoachees] = useState(true);

  // Selected coachee
  const [selectedCoacheeId, setSelectedCoacheeId] = useState<string | null>(null);

  // Upload result
  const [transcriptId, setTranscriptId] = useState<string | null>(null);
  const [speakerLabels, setSpeakerLabels] = useState<string[]>([]);

  // Config fields
  const [speakerLabel, setSpeakerLabel] = useState<string | null>(null);
  const [name, setName] = useState('');
  const [role, setRole] = useState<TargetRole | ''>('');

  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.listCoachees().then(setCoachees).finally(() => setLoadingCoachees(false));
  }, []);

  // Pre-fill speaker name when coachee is selected
  useEffect(() => {
    if (selectedCoacheeId) {
      const coachee = coachees.find((c) => c.id === selectedCoacheeId);
      if (coachee) setName(coachee.display_name ?? '');
    }
  }, [selectedCoacheeId, coachees]);

  const handleUploaded = ({ transcript_id, speaker_labels }: { transcript_id: string; speaker_labels: string[] }) => {
    setTranscriptId(transcript_id);
    setSpeakerLabels(speaker_labels);
    setSpeakerLabel(speaker_labels[0] ?? null);
  };

  const ready = selectedCoacheeId && transcriptId && speakerLabel && name && role;

  const handleSubmit = async () => {
    if (!ready) return;
    setSubmitting(true);
    setError(null);
    try {
      const result = await api.coachEnqueueAnalysis(selectedCoacheeId!, {
        transcript_id: transcriptId!,
        target_speaker_name: name,
        target_speaker_label: speakerLabel!,
        target_role: role as TargetRole,
      });
      if (result.run_id) {
        router.push(`/client/runs/${result.run_id}`);
      } else {
        pollRunRequest(result.run_request_id);
      }
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Failed to enqueue');
      setSubmitting(false);
    }
  };

  const pollRunRequest = async (rrId: string) => {
    let count = 0;
    const poll = async () => {
      count++;
      try {
        const status = await api.getRunRequest(rrId);
        if (status.run_id) {
          router.push(`/client/runs/${status.run_id}`);
          return;
        }
        if (status.status === 'error') {
          setError('Analysis failed to start.');
          setSubmitting(false);
          return;
        }
        if (count < 30) setTimeout(poll, 2000);
        else {
          setError('Timed out waiting for analysis to start.');
          setSubmitting(false);
        }
      } catch {
        setError('Failed to poll status.');
        setSubmitting(false);
      }
    };
    poll();
  };

  return (
    <div className="max-w-xl mx-auto space-y-6 py-2">
      <div>
        <h1 className="text-2xl font-bold text-stone-900">Run Analysis</h1>
        <p className="text-sm text-stone-500 mt-1">
          Upload a transcript and run coaching analysis for one of your coachees.
        </p>
      </div>

      {/* Step 1 — Select coachee */}
      <div className="bg-white rounded-2xl border border-stone-200 p-5 space-y-3">
        <p className="text-xs font-semibold text-stone-400 uppercase tracking-widest">
          Step 1 — Select Coachee
        </p>
        {loadingCoachees ? (
          <div className="h-8 flex items-center">
            <div className="w-4 h-4 border-2 border-emerald-500 border-t-transparent rounded-full animate-spin" />
          </div>
        ) : coachees.length === 0 ? (
          <p className="text-sm text-stone-500">
            No coachees yet.{' '}
            <a href="/coach" className="text-emerald-600 underline">
              Invite one first.
            </a>
          </p>
        ) : (
          <div className="grid grid-cols-1 gap-2 max-h-48 overflow-y-auto">
            {coachees.map((c) => (
              <label
                key={c.id}
                className={`flex items-center gap-3 px-3 py-2.5 rounded-xl cursor-pointer border transition-colors ${
                  selectedCoacheeId === c.id
                    ? 'border-emerald-400 bg-emerald-50'
                    : 'border-stone-200 hover:border-stone-300'
                }`}
              >
                <input
                  type="radio"
                  name="coachee"
                  value={c.id}
                  checked={selectedCoacheeId === c.id}
                  onChange={() => setSelectedCoacheeId(c.id)}
                  className="accent-emerald-600"
                />
                <div>
                  <p className="text-sm font-medium text-stone-800">
                    {c.display_name ?? 'Unnamed'}
                  </p>
                  <p className="text-xs text-stone-400">{c.email}</p>
                </div>
              </label>
            ))}
          </div>
        )}
      </div>

      {/* Step 2 — Upload transcript */}
      {selectedCoacheeId && (
        <div className="bg-white rounded-2xl border border-stone-200 p-5 space-y-3">
          <p className="text-xs font-semibold text-stone-400 uppercase tracking-widest">
            Step 2 — Upload Transcript
          </p>
          <TranscriptUploadPanel onUploaded={handleUploaded} />
        </div>
      )}

      {/* Step 3 — Configure */}
      {transcriptId && (
        <div className="bg-white rounded-2xl border border-stone-200 p-5 space-y-3">
          <p className="text-xs font-semibold text-stone-400 uppercase tracking-widest">
            Step 3 — Configure Analysis
          </p>

          {speakerLabels.length > 0 ? (
            <div>
              <p className="text-xs text-stone-500 mb-1.5">Target speaker</p>
              <SpeakerChips
                speakers={speakerLabels}
                selected={speakerLabel}
                onSelect={setSpeakerLabel}
              />
            </div>
          ) : (
            <div>
              <label className="text-xs text-stone-500">Speaker label</label>
              <input
                type="text"
                value={speakerLabel ?? ''}
                onChange={(e) => setSpeakerLabel(e.target.value || null)}
                placeholder="e.g. SPEAKER_00"
                className="mt-1 w-full border border-stone-300 rounded-lg px-3 py-2 text-sm"
              />
            </div>
          )}

          <div>
            <label className="text-xs text-stone-500">Speaker's full name</label>
            <input
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="e.g. Sarah Johnson"
              className="mt-1 w-full border border-stone-300 rounded-lg px-3 py-2 text-sm"
            />
          </div>

          <div>
            <label className="text-xs text-stone-500">Target role</label>
            <select
              value={role}
              onChange={(e) => setRole(e.target.value as TargetRole)}
              className="mt-1 w-full border border-stone-300 rounded-lg px-3 py-2 text-sm"
            >
              <option value="">Select role…</option>
              {ROLE_OPTIONS.map((r) => (
                <option key={r.value} value={r.value}>{r.label}</option>
              ))}
            </select>
          </div>

          {speakerLabel && name && role
            ? <p className="text-xs text-emerald-600 font-medium">✓ Ready to analyse</p>
            : <p className="text-xs text-amber-600">Complete the fields above to continue</p>
          }
        </div>
      )}

      {error && <p className="text-sm text-rose-600">{error}</p>}

      <button
        onClick={handleSubmit}
        disabled={!ready || submitting}
        className="w-full py-3 bg-emerald-600 text-white rounded-xl font-medium text-sm hover:bg-emerald-700 disabled:opacity-40 disabled:cursor-not-allowed transition-colors shadow-sm"
      >
        {submitting ? 'Running analysis…' : 'Run Analysis'}
      </button>
    </div>
  );
}

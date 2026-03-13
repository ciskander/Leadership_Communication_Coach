'use client';

import { Suspense, useEffect, useState } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import Link from 'next/link';
import { api } from '@/lib/api';
import { TranscriptUploadPanel } from '@/components/TranscriptUpload';
import { SpeakerChips } from '@/components/SpeakerChips';
import { RunStatusPoller } from '@/components/RunStatusPoller';
import type { CoacheeListItem, TargetRole } from '@/lib/types';
import { STRINGS } from '@/config/strings';

const ROLE_OPTIONS = STRINGS.roleOptions;

export default function CoachAnalyzePageWrapper() {
  return (
    <Suspense fallback={<div className="flex items-center justify-center h-64"><div className="animate-spin rounded-full h-8 w-8 border-b-2 border-emerald-600" /></div>}>
      <CoachAnalyzePage />
    </Suspense>
  );
}

function CoachAnalyzePage() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const preselectedCoachee = searchParams.get('coachee');

  const [coachees, setCoachees] = useState<CoacheeListItem[]>([]);
  const [loadingCoachees, setLoadingCoachees] = useState(true);

  // Selected coachee
  const [selectedCoacheeId, setSelectedCoacheeId] = useState<string | null>(preselectedCoachee);

  // Upload result
  const [transcriptId, setTranscriptId] = useState<string | null>(null);
  const [speakerLabels, setSpeakerLabels] = useState<string[]>([]);

  // Config fields
  const [speakerLabel, setSpeakerLabel] = useState<string | null>(null);
  const [name, setName] = useState('');
  const [role, setRole] = useState<TargetRole | ''>('');

  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Run result state — show inline instead of redirecting
  const [runId, setRunId] = useState<string | null>(null);

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
        setRunId(result.run_id);
      } else {
        pollRunRequest(result.run_request_id);
      }
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : STRINGS.analyzePage.failedToEnqueue);
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
          setRunId(status.run_id);
          return;
        }
        if (status.status === 'error') {
          setError(STRINGS.analyzePage.analysisFailedToStart);
          setSubmitting(false);
          return;
        }
        if (count < 30) setTimeout(poll, 2000);
        else {
          setError(STRINGS.analyzePage.timedOutWaiting);
          setSubmitting(false);
        }
      } catch {
        setError(STRINGS.analyzePage.failedToPollStatus);
        setSubmitting(false);
      }
    };
    poll();
  };

  // If we have a run ID, show the results inline
  if (runId) {
    const selectedCoachee = coachees.find((c) => c.id === selectedCoacheeId);
    return (
      <div className="max-w-3xl mx-auto space-y-6 py-2">
        <div>
          <Link
            href={selectedCoacheeId ? `/coach/coachees/${selectedCoacheeId}` : '/coach'}
            className="text-sm text-stone-500 hover:text-stone-700 transition-colors"
          >
            ← Back to {selectedCoachee?.display_name ?? 'coachee'}
          </Link>
          <h1 className="text-2xl font-bold text-stone-900 mt-2">
            {STRINGS.common.meetingAnalysis}
          </h1>
          <p className="text-sm text-stone-500 mt-1">
            {selectedCoachee?.display_name ?? selectedCoachee?.email}
          </p>
        </div>
        <RunStatusPoller runId={runId} />
        <div className="flex gap-3">
          <button
            onClick={() => {
              setRunId(null);
              setTranscriptId(null);
              setSpeakerLabels([]);
              setSpeakerLabel(null);
              setRole('');
              setSubmitting(false);
            }}
            className="px-4 py-2 border border-stone-300 text-stone-600 rounded-xl text-sm font-medium hover:bg-stone-50 transition-colors"
          >
            Analyze another
          </button>
          <Link
            href={`/coach/coachees/${selectedCoacheeId}`}
            className="px-4 py-2 bg-emerald-600 text-white rounded-xl text-sm font-medium hover:bg-emerald-700 transition-colors"
          >
            Back to coachee
          </Link>
        </div>
      </div>
    );
  }

  return (
    <div className="max-w-xl mx-auto space-y-6 py-2">
      <div>
        <h1 className="text-2xl font-bold text-stone-900">{STRINGS.coachAnalyze.heading}</h1>
        <p className="text-sm text-stone-500 mt-1">
          {STRINGS.coachAnalyze.subtitle}
        </p>
      </div>

      {/* Step 1 — Select coachee */}
      <div className="bg-white rounded-2xl border border-stone-200 p-5 space-y-3">
        <p className="text-xs font-semibold text-stone-400 uppercase tracking-widest">
          {STRINGS.coachAnalyze.step1}
        </p>
        {loadingCoachees ? (
          <div className="h-8 flex items-center">
            <div className="w-4 h-4 border-2 border-emerald-500 border-t-transparent rounded-full animate-spin" />
          </div>
        ) : coachees.length === 0 ? (
          <p className="text-sm text-stone-500">
            {STRINGS.coachAnalyze.noCoachees}{' '}
            <a href="/coach" className="text-emerald-600 underline">
              {STRINGS.coachAnalyze.inviteFirst}
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
                    {c.display_name ?? STRINGS.coachDashboard.unnamed}
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
            {STRINGS.coachAnalyze.step2}
          </p>
          <TranscriptUploadPanel onUploaded={handleUploaded} />
        </div>
      )}

      {/* Step 3 — Configure */}
      {transcriptId && (
        <div className="bg-white rounded-2xl border border-stone-200 p-5 space-y-3">
          <p className="text-xs font-semibold text-stone-400 uppercase tracking-widest">
            {STRINGS.coachAnalyze.step3}
          </p>

          {speakerLabels.length > 0 ? (
            <div>
              <p className="text-xs text-stone-500 mb-1.5">{STRINGS.coachAnalyze.targetSpeaker}</p>
              <SpeakerChips
                speakers={speakerLabels}
                selected={speakerLabel}
                onSelect={setSpeakerLabel}
              />
            </div>
          ) : (
            <div>
              <label className="text-xs text-stone-500">{STRINGS.analyzePage.speakerLabel}</label>
              <input
                type="text"
                value={speakerLabel ?? ''}
                onChange={(e) => setSpeakerLabel(e.target.value || null)}
                placeholder={STRINGS.analyzePage.speakerLabelPlaceholder}
                className="mt-1 w-full border border-stone-300 rounded-lg px-3 py-2 text-sm"
              />
            </div>
          )}

          <div>
            <label className="text-xs text-stone-500">{STRINGS.coachAnalyze.speakersFullName}</label>
            <input
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder={STRINGS.analyzePage.fullNamePlaceholder}
              className="mt-1 w-full border border-stone-300 rounded-lg px-3 py-2 text-sm"
            />
          </div>

          <div>
            <label className="text-xs text-stone-500">{STRINGS.coachAnalyze.targetRole}</label>
            <select
              value={role}
              onChange={(e) => setRole(e.target.value as TargetRole)}
              className="mt-1 w-full border border-stone-300 rounded-lg px-3 py-2 text-sm"
            >
              <option value="">{STRINGS.analyzePage.selectRole}</option>
              {ROLE_OPTIONS.map((r) => (
                <option key={r.value} value={r.value}>{r.label}</option>
              ))}
            </select>
          </div>

          {speakerLabel && name && role
            ? <p className="text-xs text-emerald-600 font-medium">{STRINGS.coachAnalyze.readyToAnalyse}</p>
            : <p className="text-xs text-amber-600">{STRINGS.coachAnalyze.completeFieldsAbove}</p>
          }
        </div>
      )}

      {error && <p className="text-sm text-rose-600">{error}</p>}

      <button
        onClick={handleSubmit}
        disabled={!ready || submitting}
        className="w-full py-3 bg-emerald-600 text-white rounded-xl font-medium text-sm hover:bg-emerald-700 disabled:opacity-40 disabled:cursor-not-allowed transition-colors shadow-sm"
      >
        {submitting ? STRINGS.coachAnalyze.runningAnalysis : STRINGS.coachAnalyze.runAnalysis}
      </button>
    </div>
  );
}

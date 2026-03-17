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

// ─── Shared input styles ──────────────────────────────────────────────────────

const inputCls = 'mt-1 w-full border border-cv-warm-300 rounded px-3 py-2 text-sm text-cv-stone-800 bg-white focus:outline-none focus:border-cv-teal-400 focus:ring-1 focus:ring-cv-teal-400/30 transition-colors placeholder:text-cv-stone-400';

// ─── Step label ───────────────────────────────────────────────────────────────

function StepLabel({ text, done }: { text: string; done?: boolean }) {
  return (
    <div className="flex items-center gap-2 mb-3">
      {done ? (
        <span className="flex items-center justify-center w-4 h-4 rounded-full bg-cv-teal-600 shrink-0">
          <svg viewBox="0 0 12 12" fill="none" className="w-2.5 h-2.5" aria-hidden="true">
            <path d="M2 6l3 3 5-5" stroke="white" strokeWidth={1.5} strokeLinecap="round" strokeLinejoin="round" />
          </svg>
        </span>
      ) : (
        <span className="w-4 h-4 rounded-full border-2 border-cv-warm-300 shrink-0" />
      )}
      <p className="text-2xs font-semibold uppercase tracking-[0.14em] text-cv-stone-400">{text}</p>
    </div>
  );
}

// ─── Page inner ───────────────────────────────────────────────────────────────

function CoachAnalyzePage() {
  const searchParams       = useSearchParams();
  const preselectedCoachee = searchParams.get('coachee');

  const [coachees, setCoachees]             = useState<CoacheeListItem[]>([]);
  const [loadingCoachees, setLoadingCoachees] = useState(true);
  const [selectedCoacheeId, setSelectedCoacheeId] = useState<string | null>(preselectedCoachee);

  const [transcriptId, setTranscriptId]     = useState<string | null>(null);
  const [speakerLabels, setSpeakerLabels]   = useState<string[]>([]);
  const [speakerLabel, setSpeakerLabel]     = useState<string | null>(null);
  const [name, setName]                     = useState('');
  const [role, setRole]                     = useState<TargetRole | ''>('');
  const [submitting, setSubmitting]         = useState(false);
  const [error, setError]                   = useState<string | null>(null);
  const [runId, setRunId]                   = useState<string | null>(null);

  useEffect(() => {
    api.listCoachees().then(setCoachees).finally(() => setLoadingCoachees(false));
  }, []);

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

  const pollRunRequest = async (rrId: string) => {
    let count = 0;
    const poll = async () => {
      count++;
      try {
        const status = await api.getRunRequest(rrId);
        if (status.run_id) { setRunId(status.run_id); return; }
        if (status.status === 'error') {
          setError(STRINGS.analyzePage.analysisFailedToStart);
          setSubmitting(false);
          return;
        }
        if (count < 30) setTimeout(poll, 2000);
        else { setError(STRINGS.analyzePage.timedOutWaiting); setSubmitting(false); }
      } catch {
        setError(STRINGS.analyzePage.failedToPollStatus);
        setSubmitting(false);
      }
    };
    poll();
  };

  const handleSubmit = async () => {
    if (!ready) return;
    setSubmitting(true);
    setError(null);
    try {
      const result = await api.coachEnqueueAnalysis(selectedCoacheeId!, {
        transcript_id:         transcriptId!,
        target_speaker_name:   name,
        target_speaker_label:  speakerLabel!,
        target_role:           role as TargetRole,
      });
      if (result.run_id) setRunId(result.run_id);
      else pollRunRequest(result.run_request_id);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : STRINGS.analyzePage.failedToEnqueue);
      setSubmitting(false);
    }
  };

  // ── Results view ────────────────────────────────────────────────────────────
  if (runId) {
    const selectedCoachee = coachees.find((c) => c.id === selectedCoacheeId);
    return (
      <div className="max-w-5xl mx-auto space-y-6 py-2">
        <div>
          <Link
            href={selectedCoacheeId ? `/coach/coachees/${selectedCoacheeId}` : '/coach'}
            className="text-sm text-cv-stone-500 hover:text-cv-stone-700 transition-colors"
          >
            ← Back to {selectedCoachee?.display_name ?? 'coachee'}
          </Link>
          <h1 className="font-serif text-2xl text-cv-stone-900 mt-2">
            {STRINGS.common.meetingAnalysis}
          </h1>
          <p className="text-sm text-cv-stone-500 mt-1">
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
            className="px-4 py-2 border border-cv-warm-300 text-cv-stone-600 rounded text-sm font-medium hover:bg-cv-warm-50 transition-colors"
          >
            {STRINGS.coachAnalyze.analyzeAnother ?? 'Analyze another'}
          </button>
          <Link
            href={`/coach/coachees/${selectedCoacheeId}`}
            className="px-4 py-2 bg-cv-teal-600 text-white rounded text-sm font-medium hover:bg-cv-teal-700 transition-colors"
          >
            {STRINGS.coacheeDetail.backToDashboard ?? 'Back to coachee'}
          </Link>
        </div>
      </div>
    );
  }

  // ── Form view ───────────────────────────────────────────────────────────────
  return (
    <div className="max-w-xl mx-auto space-y-5 py-2">
      <div>
        <h1 className="font-serif text-2xl text-cv-stone-900">
          {STRINGS.coachAnalyze.heading}
        </h1>
        <p className="text-sm text-cv-stone-500 mt-1">{STRINGS.coachAnalyze.subtitle}</p>
      </div>

      {/* Step 1 — Select coachee */}
      <div className="bg-white rounded border border-cv-warm-200 p-5">
        <StepLabel text={STRINGS.coachAnalyze.step1} done={!!selectedCoacheeId} />
        {loadingCoachees ? (
          <div className="h-8 flex items-center">
            <span className="w-4 h-4 border-2 border-cv-teal-500 border-t-transparent rounded-full animate-spin" />
          </div>
        ) : coachees.length === 0 ? (
          <p className="text-sm text-cv-stone-500">
            {STRINGS.coachAnalyze.noCoachees}{' '}
            <a href="/coach" className="text-cv-teal-600 underline">
              {STRINGS.coachAnalyze.inviteFirst}
            </a>
          </p>
        ) : (
          <div className="grid grid-cols-1 gap-2 max-h-48 overflow-y-auto">
            {coachees.map((c) => (
              <label
                key={c.id}
                className={[
                  'flex items-center gap-3 px-3 py-2.5 rounded cursor-pointer border transition-colors',
                  selectedCoacheeId === c.id
                    ? 'border-cv-teal-400 bg-cv-teal-50'
                    : 'border-cv-warm-200 hover:border-cv-warm-300',
                ].join(' ')}
              >
                <input
                  type="radio"
                  name="coachee"
                  value={c.id}
                  checked={selectedCoacheeId === c.id}
                  onChange={() => setSelectedCoacheeId(c.id)}
                  className="accent-cv-teal-600"
                />
                <div>
                  <p className="text-sm font-medium text-cv-stone-800">
                    {c.display_name ?? STRINGS.coachDashboard.unnamed}
                  </p>
                  <p className="text-xs text-cv-stone-400">{c.email}</p>
                </div>
              </label>
            ))}
          </div>
        )}
      </div>

      {/* Step 2 — Upload transcript */}
      {selectedCoacheeId && (
        <div className="bg-white rounded border border-cv-warm-200 p-5">
          <StepLabel text={STRINGS.coachAnalyze.step2} done={!!transcriptId} />
          <TranscriptUploadPanel onUploaded={handleUploaded} />
        </div>
      )}

      {/* Step 3 — Configure */}
      {transcriptId && (
        <div className="bg-white rounded border border-cv-warm-200 p-5 space-y-4">
          <StepLabel text={STRINGS.coachAnalyze.step3} done={!!(speakerLabel && name && role)} />

          {speakerLabels.length > 0 ? (
            <div>
              <p className="text-xs text-cv-stone-500 mb-1.5">{STRINGS.coachAnalyze.targetSpeaker}</p>
              <SpeakerChips
                speakers={speakerLabels}
                selected={speakerLabel}
                onSelect={setSpeakerLabel}
              />
            </div>
          ) : (
            <div>
              <label className="text-xs font-medium text-cv-stone-500">{STRINGS.analyzePage.speakerLabel}</label>
              <input
                type="text"
                value={speakerLabel ?? ''}
                onChange={(e) => setSpeakerLabel(e.target.value || null)}
                placeholder={STRINGS.analyzePage.speakerLabelPlaceholder}
                className={inputCls}
              />
            </div>
          )}

          <div>
            <label className="text-xs font-medium text-cv-stone-500">{STRINGS.coachAnalyze.speakersFullName}</label>
            <input
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder={STRINGS.analyzePage.fullNamePlaceholder}
              className={inputCls}
            />
          </div>

          <div>
            <label className="text-xs font-medium text-cv-stone-500">{STRINGS.coachAnalyze.targetRole}</label>
            <select
              value={role}
              onChange={(e) => setRole(e.target.value as TargetRole)}
              className={inputCls}
            >
              <option value="">{STRINGS.analyzePage.selectRole}</option>
              {ROLE_OPTIONS.map((r) => (
                <option key={r.value} value={r.value}>{r.label}</option>
              ))}
            </select>
          </div>

          {speakerLabel && name && role ? (
            <p className="text-xs text-cv-teal-600 font-medium">{STRINGS.coachAnalyze.readyToAnalyse}</p>
          ) : (
            <p className="text-xs text-cv-amber-600">{STRINGS.coachAnalyze.completeFieldsAbove}</p>
          )}
        </div>
      )}

      {error && (
        <p className="text-sm text-cv-red-600 bg-cv-red-50 border border-cv-red-200 rounded px-4 py-3">
          {error}
        </p>
      )}

      <button
        onClick={handleSubmit}
        disabled={!ready || submitting}
        className="w-full py-3 bg-cv-teal-600 text-white rounded font-medium text-sm hover:bg-cv-teal-700 disabled:opacity-40 disabled:cursor-not-allowed transition-colors shadow-sm flex items-center justify-center gap-2"
      >
        {submitting && (
          <span className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin" />
        )}
        {submitting ? STRINGS.coachAnalyze.runningAnalysis : STRINGS.coachAnalyze.runAnalysis}
      </button>
    </div>
  );
}

export default function CoachAnalyzePageWrapper() {
  return (
    <Suspense fallback={
      <div className="flex items-center justify-center h-64">
        <span className="w-8 h-8 border-2 border-cv-teal-600 border-t-transparent rounded-full animate-spin" />
      </div>
    }>
      <CoachAnalyzePage />
    </Suspense>
  );
}

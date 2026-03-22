'use client';

import { useState, useEffect } from 'react';
import { useRouter } from 'next/navigation';
import Link from 'next/link';
import { api } from '@/lib/api';
import { STRINGS } from '@/config/strings';
import { OnboardingTip } from '@/components/OnboardingTip';
import { TranscriptUploadPanel } from '@/components/TranscriptUpload';
import { SpeakerChips } from '@/components/SpeakerChips';
import type { TargetRole } from '@/lib/types';

const ROLE_OPTIONS = STRINGS.roleOptions;

function getFirstName(displayName: string): string {
  return displayName.trim().split(/\s+/)[0].toLowerCase();
}

function matchSpeakerByFirstName(speakers: string[], firstName: string): string | null {
  const lower = firstName.toLowerCase();
  return speakers.find((s) => s.toLowerCase().startsWith(lower)) ?? null;
}

function isGenericLabel(label: string): boolean {
  return /^SPEAKER_\d+/i.test(label) || /^UNKNOWN$/i.test(label);
}

// ─── Step indicator ───────────────────────────────────────────────────────────

function StepBadge({ n, done }: { n: number; done: boolean }) {
  if (done) {
    return (
      <div className="w-6 h-6 rounded-full bg-cv-teal-600 text-white flex items-center justify-center shrink-0">
        <svg viewBox="0 0 12 12" fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round" className="w-3 h-3" aria-hidden="true">
          <path d="M2 6l3 3 5-5" />
        </svg>
      </div>
    );
  }
  return (
    <div className="w-6 h-6 rounded-full bg-cv-stone-800 text-white flex items-center justify-center text-xs font-semibold shrink-0">
      {n}
    </div>
  );
}

// ─── Shared input classes ─────────────────────────────────────────────────────

const inputCls =
  'mt-1 w-full border border-cv-warm-300 rounded px-3 py-2.5 text-sm text-cv-stone-800 bg-white focus:outline-none focus:border-cv-teal-400 focus:ring-1 focus:ring-cv-teal-400/30 transition-colors placeholder:text-cv-stone-400';

// ─── Field label ──────────────────────────────────────────────────────────────

function FieldLabel({ text }: { text: string }) {
  return (
    <label className="text-2xs font-semibold uppercase tracking-[0.12em] text-cv-stone-400">
      {text}
    </label>
  );
}

// ─── Page ─────────────────────────────────────────────────────────────────────

export default function AnalyzePage() {
  const router = useRouter();
  const [currentUserName, setCurrentUserName]     = useState('');
  const [transcriptId, setTranscriptId]           = useState<string | null>(null);
  const [speakerLabels, setSpeakerLabels]         = useState<string[]>([]);
  const [speakerLabel, setSpeakerLabel]           = useState<string | null>(null);
  const [name, setName]                           = useState('');
  const [role, setRole]                           = useState<TargetRole | ''>('');
  const [submitting, setSubmitting]               = useState(false);
  const [submitLabel, setSubmitLabel]             = useState<string>(STRINGS.analyzePage.startingAnalysis);
  const [error, setError]                         = useState<string | null>(null);
  const [speakerPreviews, setSpeakerPreviews]     = useState<Record<string, string[]>>({});
  const [needsSpeakerPick, setNeedsSpeakerPick]   = useState(false);
  const [pendingRunRequestId, setPendingRunRequestId] = useState<string | null>(null);
  const [checkState, setCheckState]               = useState<'idle' | 'checking' | 'still_processing'>('idle');

  useEffect(() => {
    api.me().then((user) => {
      if (user.display_name) setCurrentUserName(user.display_name);
    }).catch(() => {});
  }, []);

  const handleUploaded = ({
    transcript_id,
    speaker_labels,
    speaker_previews = {},
  }: {
    transcript_id: string;
    speaker_labels: string[];
    speaker_previews?: Record<string, string[]>;
    meeting_date?: string | null;
    detected_date?: string | null;
  }) => {
    setTranscriptId(transcript_id);
    setSpeakerLabels(speaker_labels);
    setSpeakerPreviews(speaker_previews);

    const allGeneric = speaker_labels.every(isGenericLabel);
    const firstName  = currentUserName ? getFirstName(currentUserName) : '';
    const matched    = !allGeneric && firstName
      ? matchSpeakerByFirstName(speaker_labels, firstName)
      : null;

    if (matched) {
      setSpeakerLabel(matched);
      setNeedsSpeakerPick(false);
    } else if (allGeneric && speaker_labels.length > 1) {
      setSpeakerLabel(null);
      setNeedsSpeakerPick(true);
    } else {
      setSpeakerLabel(speaker_labels[0] ?? null);
      setNeedsSpeakerPick(false);
    }

    setName(currentUserName || '');
    setRole('');
  };

  const ready = transcriptId && speakerLabel && name && role;

  const handleSubmit = async () => {
    if (!ready) return;
    setSubmitting(true);
    setError(null);
    try {
      const result = await api.enqueueSingleMeeting({
        transcript_id: transcriptId,
        target_speaker_name: name,
        target_speaker_label: speakerLabel,
        target_role: role,
      });
      if (result.run_id) {
        router.push(`/client/runs/${result.run_id}`);
      } else {
        pollRunRequest(result.run_request_id);
      }
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : STRINGS.analyzePage.failedToEnqueue);
      setSubmitLabel(STRINGS.analyzePage.startingAnalysis);
      setSubmitting(false);
    }
  };

  const pollRunRequest = async (rrId: string) => {
    let count = 0;
    let processing = false;
    const MAX_QUEUED_POLLS = 30;        // 30 × 2s = 60s waiting for worker pickup
    const MAX_PROCESSING_POLLS = 150;   // 150 × 2s = 300s for LLM analysis
    const poll = async () => {
      count++;
      try {
        const status = await api.getRunRequest(rrId);
        if (status.run_id) {
          router.push(`/client/runs/${status.run_id}`);
          return;
        }
        if (status.status === 'error') {
          setError(STRINGS.analyzePage.analysisFailedToStart);
          setSubmitLabel(STRINGS.analyzePage.startingAnalysis);
          setSubmitting(false);
          return;
        }
        if (status.status === 'processing') {
          if (!processing) {
            processing = true;
            count = 0; // reset counter once analysis is confirmed in progress
            setSubmitLabel(STRINGS.analyzePage.analysisInProgress);
          }
        }
        const limit = processing ? MAX_PROCESSING_POLLS : MAX_QUEUED_POLLS;
        if (count < limit) setTimeout(poll, 2000);
        else {
          if (processing) {
            setPendingRunRequestId(rrId);
          }
          setError(
            processing
              ? STRINGS.analyzePage.analysisStillRunning
              : STRINGS.analyzePage.timedOutWaiting,
          );
          setSubmitLabel(STRINGS.analyzePage.startingAnalysis);
          setSubmitting(false);
        }
      } catch {
        setError(STRINGS.analyzePage.failedToPollStatus);
        setSubmitLabel(STRINGS.analyzePage.startingAnalysis);
        setSubmitting(false);
      }
    };
    poll();
  };

  const handleCheckNow = async () => {
    if (!pendingRunRequestId) return;
    setCheckState('checking');
    try {
      const status = await api.getRunRequest(pendingRunRequestId);
      if (status.run_id) {
        router.push(`/client/runs/${status.run_id}`);
        return;
      }
      if (status.status === 'error') {
        setError(STRINGS.analyzePage.analysisFailedToStart);
        setPendingRunRequestId(null);
        setCheckState('idle');
        return;
      }
      setCheckState('still_processing');
      setTimeout(() => setCheckState('idle'), 3000);
    } catch {
      setCheckState('idle');
    }
  };

  const step = !transcriptId ? 1 : !speakerLabel || !name || !role ? 2 : 3;

  return (
    <div className="max-w-xl mx-auto space-y-5 py-2">

      <OnboardingTip tipId="analyze" message={STRINGS.onboarding.tipAnalyze} />

      {/* Page heading */}
      <div>
        <h1 className="font-serif text-2xl text-cv-stone-900">
          {STRINGS.analyzePage.heading}
        </h1>
        <p className="text-sm text-cv-stone-500 mt-1">{STRINGS.analyzePage.subtitle}</p>
      </div>

      {/* ── Step 1: Upload ── */}
      <div className="bg-white rounded border border-cv-warm-300 p-5 space-y-3">
        <div className="flex items-center gap-2.5">
          <StepBadge n={1} done={step > 1} />
          <p className="text-sm font-semibold text-cv-stone-800">{STRINGS.analyzePage.step1}</p>
        </div>
        <TranscriptUploadPanel onUploaded={handleUploaded} withMetadata={true} />
      </div>

      {/* ── Step 2: Configure ── */}
      {transcriptId && (
        <div className="bg-white rounded border border-cv-warm-300 p-5 space-y-4">
          <div className="flex items-center gap-2.5">
            <StepBadge n={2} done={step > 2} />
            <p className="text-sm font-semibold text-cv-stone-800">{STRINGS.analyzePage.step2}</p>
          </div>

          {/* Speaker selection */}
          {needsSpeakerPick ? (
            <div className="space-y-2.5">
              <p className="text-2xs font-semibold uppercase tracking-[0.12em] text-cv-stone-400">
                {STRINGS.analyzePage.whichSpeaker}
              </p>
              <div className="grid grid-cols-1 gap-2">
                {speakerLabels.map((label) => {
                  const quotes = speakerPreviews[label] ?? [];
                  return (
                    <button
                      key={label}
                      onClick={() => { setSpeakerLabel(label); setNeedsSpeakerPick(false); }}
                      className={[
                        'text-left p-3.5 rounded border transition-colors',
                        speakerLabel === label
                          ? 'border-cv-teal-500 bg-cv-teal-50'
                          : 'border-cv-warm-300 bg-white hover:border-cv-warm-300',
                      ].join(' ')}
                    >
                      <p className="text-2xs font-semibold uppercase tracking-[0.12em] text-cv-stone-400 mb-1.5">
                        {label}
                      </p>
                      {quotes.map((q, i) => (
                        <p key={i} className="text-sm text-cv-stone-600 leading-snug italic">
                          &ldquo;{q}&rdquo;
                        </p>
                      ))}
                    </button>
                  );
                })}
              </div>
            </div>
          ) : speakerLabels.length > 0 ? (
            <div>
              <p className="text-2xs font-semibold uppercase tracking-[0.12em] text-cv-stone-400 mb-2">
                {STRINGS.analyzePage.whoAreWeAnalysing}
              </p>
              <SpeakerChips
                speakers={speakerLabels}
                selected={speakerLabel}
                onSelect={setSpeakerLabel}
              />
            </div>
          ) : (
            <div>
              <FieldLabel text={STRINGS.analyzePage.speakerLabel} />
              <input
                type="text"
                value={speakerLabel ?? ''}
                onChange={(e) => setSpeakerLabel(e.target.value || null)}
                placeholder={STRINGS.analyzePage.speakerLabelPlaceholder}
                className={inputCls}
              />
            </div>
          )}

          {/* Full name */}
          <div>
            <FieldLabel text={STRINGS.analyzePage.fullName} />
            <input
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder={STRINGS.analyzePage.fullNamePlaceholder}
              className={inputCls}
            />
          </div>

          {/* Role in meeting */}
          <div>
            <FieldLabel text={STRINGS.analyzePage.roleInMeeting} />
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
        </div>
      )}

      {/* Recovery card — shown when processing poll timed out but analysis is still running */}
      {pendingRunRequestId && (
        <div className="bg-cv-amber-50 border border-cv-amber-200 rounded px-5 py-4 space-y-3">
          <div className="flex items-start gap-3">
            <svg viewBox="0 0 16 16" fill="none" className="w-5 h-5 shrink-0 text-cv-amber-600 mt-0.5" aria-hidden="true">
              <circle cx="8" cy="9" r="6" stroke="currentColor" strokeWidth={1.4} />
              <path d="M8 6v3.5l2 1.5" stroke="currentColor" strokeWidth={1.4} strokeLinecap="round" strokeLinejoin="round" />
              <path d="M8 3V1" stroke="currentColor" strokeWidth={1.4} strokeLinecap="round" />
            </svg>
            <div className="space-y-1">
              <p className="text-sm font-medium text-cv-amber-800">{STRINGS.analyzePage.analysisStillRunning}</p>
              {checkState === 'still_processing' && (
                <p className="text-xs text-cv-amber-600">{STRINGS.analyzePage.stillProcessing}</p>
              )}
            </div>
          </div>
          <div className="flex items-center gap-3 pl-8">
            <button
              onClick={handleCheckNow}
              disabled={checkState === 'checking'}
              className="px-4 py-2 bg-cv-teal-600 text-white rounded text-xs font-medium hover:bg-cv-teal-800 transition-colors disabled:opacity-50 flex items-center gap-1.5"
            >
              {checkState === 'checking' && (
                <span className="w-3 h-3 border-2 border-white border-t-transparent rounded-full animate-spin" />
              )}
              {STRINGS.analyzePage.checkNow}
            </button>
            <Link
              href="/client"
              className="text-xs text-cv-stone-400 hover:text-cv-stone-600 transition-colors"
            >
              {STRINGS.analyzePage.backToDashboard}
            </Link>
          </div>
        </div>
      )}

      {/* Error (non-recovery) */}
      {error && !pendingRunRequestId && (
        <p className="text-sm text-cv-red-700 bg-cv-red-50 border border-cv-red-200 rounded px-4 py-3">
          {error}
        </p>
      )}

      {/* Submit */}
      <button
        onClick={handleSubmit}
        disabled={!ready || submitting}
        className="w-full py-3.5 bg-cv-navy-600 text-white rounded font-medium text-sm hover:bg-cv-navy-700 disabled:opacity-40 disabled:cursor-not-allowed transition-colors shadow-sm"
      >
        {submitting ? (
          <span className="flex items-center justify-center gap-2">
            <span className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin" />
            {submitLabel}
          </span>
        ) : (
          <span className="flex items-center justify-center gap-2">
            <span className="shrink-0"><svg viewBox="0 0 24 24" fill="none" className="w-4 h-4 shrink-0" aria-hidden="true"><path d="M9 3L10.5 7.5L15 9L10.5 10.5L9 15L7.5 10.5L3 9L7.5 7.5L9 3Z" stroke="currentColor" strokeWidth={1.7} strokeLinecap="round" strokeLinejoin="round"/><path d="M19 13L19.75 15.25L22 16L19.75 16.75L19 19L18.25 16.75L16 16L18.25 15.25L19 13Z" stroke="currentColor" strokeWidth={1.7} strokeLinecap="round" strokeLinejoin="round"/></svg></span>
            {STRINGS.analyzePage.submitBtn}
          </span>
        )}
      </button>
    </div>
  );
}

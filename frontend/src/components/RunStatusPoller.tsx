'use client';

import { useState, useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { useRunPoller } from '@/hooks/useRunPoller';
import { CoachingCard } from './CoachingCard';
import { PatternSnapshot } from './PatternSnapshot';
import { ExperimentTracker } from './ExperimentTracker';
import { api } from '@/lib/api';
import type { Experiment, ActiveExperiment, PatternSnapshotItem } from '@/lib/types';
import { EvidenceQuote } from './EvidenceQuote';
import Link from 'next/link';

interface RunStatusPollerProps {
  runId: string;
  onComplete?: () => void;
}

export function RunStatusPoller({ runId, onComplete }: RunStatusPollerProps) {
  const { run, pollState, pollCount, retry } = useRunPoller(runId);
  const router = useRouter();

  const [confirmState, setConfirmState] = useState<'idle' | 'loading' | 'done'>('idle');
  const [confirmedValue, setConfirmedValue] = useState<boolean | null>(null);
  const [completeState, setCompleteState] = useState<'idle' | 'loading' | 'done'>('idle');
  const [proposedExperiments, setProposedExperiments] = useState<Experiment[]>([]);
  const [acceptedExpId, setAcceptedExpId] = useState<string | null>(null);
  const [acceptLoading, setAcceptLoading] = useState(false);
  const [activeExpData, setActiveExpData] = useState<ActiveExperiment | null>(null);

  // Restore human confirmation state from the backend (survives refresh).
  useEffect(() => {
    if (run?.human_confirmation) {
      setConfirmState('done');
      setConfirmedValue(run.human_confirmation === 'confirmed_attempt');
    }
  }, [run?.human_confirmation]);

  // When the run completes, populate experiment data for inline rendering.
  // Prefer the experiment detail embedded in the run response (avoids a
  // separate API call that can silently fail). Fall back to the dedicated
  // endpoint only when the run response doesn't include the detail.
  useEffect(() => {
    if (run?.status === 'complete' && run?.gate1_pass === true) {
      const activeExpStatus = (
        run.experiment_tracking as Record<string, unknown> | null
      )?.active_experiment as Record<string, unknown> | null;
      const isActive = activeExpStatus?.status === 'active';
      if (!isActive) {
        api.getProposedExperiments()
          .then(setProposedExperiments)
          .catch(() => {});
      } else if (run.active_experiment_detail) {
        // Use experiment data embedded in the run response
        setActiveExpData({
          experiment: run.active_experiment_detail,
          recent_events: run.active_experiment_events ?? [],
        });
      } else {
        // Fallback: fetch from the dedicated endpoint
        api.getActiveExperiment()
          .then(setActiveExpData)
          .catch(() => {});
      }
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [run?.status]);

  if (pollState === 'polling' || !run) {
    return (
      <div className="flex flex-col items-center justify-center py-20 gap-5">
        <div className="relative">
          <div className="w-14 h-14 rounded-full border-2 border-stone-100" />
          <div className="absolute inset-0 w-14 h-14 rounded-full border-2 border-emerald-500 border-t-transparent animate-spin" />
        </div>
        <div className="text-center space-y-1">
          <p className="text-sm font-medium text-stone-700">
            {pollCount > 20 ? 'Still working…' : 'Analysing your meeting'}
          </p>
          <p className="text-xs text-stone-400">This usually takes 30–60 seconds</p>
        </div>
      </div>
    );
  }

  if (pollState === 'timeout') {
    return (
      <div className="bg-white rounded-2xl border border-stone-200 p-8 text-center space-y-4">
        <div className="text-3xl">⏱</div>
        <p className="text-sm font-medium text-stone-700">Taking longer than expected</p>
        <p className="text-xs text-stone-400">The analysis is still running in the background.</p>
        <button
          onClick={retry}
          className="px-5 py-2.5 bg-emerald-600 text-white rounded-xl text-sm font-medium hover:bg-emerald-700 transition-colors"
        >
          Check again
        </button>
      </div>
    );
  }

  if (pollState === 'error' || run.status === 'error') {
    return (
      <div className="bg-white rounded-2xl border border-rose-200 p-8 text-center space-y-4">
        <div className="text-3xl">⚠</div>
        <p className="text-sm font-medium text-rose-700">Analysis failed</p>
        <p className="text-xs text-stone-400">
          {run?.error ? JSON.stringify(run.error) : 'Something went wrong. Please try again.'}
        </p>
        <button
          onClick={retry}
          className="px-5 py-2.5 bg-emerald-600 text-white rounded-xl text-sm font-medium hover:bg-emerald-700 transition-colors"
        >
          Retry
        </button>
      </div>
    );
  }

  if (run.status === 'complete' && run.gate1_pass === false) {
    return (
      <div className="bg-white rounded-2xl border border-amber-200 p-6 space-y-3">
        <div className="flex items-center gap-3">
          <span className="text-xl">◎</span>
          <p className="text-sm font-semibold text-amber-800">Quality check didn't pass</p>
        </div>
        <p className="text-sm text-stone-600 leading-relaxed">
          The AI output didn't meet our quality requirements. This sometimes happens with shorter or unclear transcripts. Try re-running with a cleaner transcript.
        </p>
        <Link
          href="/client/analyze"
          className="inline-block text-sm px-4 py-2 bg-emerald-600 text-white rounded-xl font-medium hover:bg-emerald-700 transition-colors"
        >
          Try another transcript
        </Link>
      </div>
    );
  }

  // ── Parse experiment tracking ────────────────────────────────────────────────
  const et = run.experiment_tracking as Record<string, unknown> | null;
  const activeExp = et?.active_experiment as Record<string, unknown> | null;
  const detection = run.experiment_detection;

	const hasActiveExp =
	  !!activeExp &&
	  activeExp.status === 'active';

  const attempt = detection?.attempt ?? null;
  const countAttempts = detection?.count_attempts ?? null;
  const detectionQuotes = detection?.quotes ?? [];
  const expRecordId = activeExp
    ? (run.experiment_tracking as Record<string, unknown> & { _record_id?: string })?._record_id ?? null
    : null;

  // ── Handlers ──────────────────────────────────────────────────────────────────

  async function handleConfirm(confirmed: boolean) {
    if (!activeExp || confirmState !== 'idle') return;
    setConfirmState('loading');
    setConfirmedValue(confirmed);
    try {
      const expId = (activeExp as Record<string, unknown>).experiment_record_id as string | undefined;
      if (expId) {
        await api.confirmExperimentAttempt(expId, runId, confirmed);
      }
    } catch {
      // Non-blocking — confirm is best-effort
    } finally {
      setConfirmState('done');
    }
  }

  async function handleComplete() {
    if (completeState !== 'idle') return;
    const expId = (activeExp as Record<string, unknown>).experiment_record_id as string | undefined;
    if (!expId) return;
    setCompleteState('loading');
    try {
      await api.completeExperiment(expId);
      router.push('/client');
    } catch {
      setCompleteState('idle');
    }
  }

  // ── Proposed experiment section (shown when run completes with no active exp) ──

  function ProposedExperimentSection() {
    if (hasActiveExp || proposedExperiments.length === 0) return null;
    const exp = proposedExperiments[0];

    if (acceptedExpId === exp.experiment_record_id) {
      return (
        <section className="bg-emerald-50 border border-emerald-200 rounded-2xl p-5 flex items-center gap-3">
          <span className="text-emerald-600 text-lg">✦</span>
          <div>
            <p className="text-sm font-semibold text-emerald-800">Experiment accepted — good luck!</p>
            <Link href="/client" className="text-xs text-emerald-600 hover:text-emerald-800 underline">
              View on dashboard →
            </Link>
          </div>
        </section>
      );
    }

    return (
      <section className="bg-violet-50 border border-violet-200 rounded-2xl p-5 space-y-3">
        <div className="flex items-center gap-2">
          <span className="text-base">◈</span>
          <p className="text-sm font-semibold text-violet-800">Your experiment is ready</p>
        </div>
        <div className="space-y-1">
          <span className="text-xs font-semibold text-stone-400 uppercase tracking-widest">
            {exp.pattern_id.replace(/_/g, ' ')}
          </span>
          <p className="text-sm font-semibold text-stone-900 leading-snug">{exp.title}</p>
        </div>
        <div className="bg-white rounded-xl p-3">
          <p className="text-xs font-semibold text-stone-400 uppercase tracking-widest mb-1">What to do</p>
          <p className="text-xs text-stone-600 leading-relaxed">{exp.instruction}</p>
        </div>
        <div className="bg-white rounded-xl p-3">
          <p className="text-xs font-semibold text-stone-400 uppercase tracking-widest mb-1">Success looks like</p>
          <p className="text-xs text-stone-600 leading-relaxed">{exp.success_marker}</p>
        </div>
        <div className="flex items-center gap-3 pt-1">
          <button
            onClick={async () => {
              if (acceptLoading) return;
              setAcceptLoading(true);
              try {
                await api.acceptExperiment(exp.experiment_record_id);
                setAcceptedExpId(exp.experiment_record_id);
              } catch {
                // non-fatal — user can always accept from the dashboard
              } finally {
                setAcceptLoading(false);
              }
            }}
            disabled={acceptLoading}
            className="px-4 py-2 bg-emerald-600 text-white rounded-xl text-xs font-semibold hover:bg-emerald-700 transition-colors disabled:opacity-60"
          >
            {acceptLoading ? 'Accepting…' : 'Accept experiment'}
          </button>
          <Link href="/client" className="text-xs text-stone-500 hover:text-stone-700 transition-colors">
            Decide later
          </Link>
        </div>
      </section>
    );
  }

  // ── Experiment section ─────────────────────────────────────────────────────

  function ExperimentSection() {
    if (!hasActiveExp) return null;

    const attemptConfig =
      attempt === 'yes'
        ? {
            icon: '✦',
            bgColor: 'bg-emerald-50',
            labelColor: 'text-emerald-800',
            label: 'Nicely done!',
            desc: `The model detected ${countAttempts ?? 'multiple'} clear attempt${(countAttempts ?? 0) !== 1 ? 's' : ''} at your experiment in this meeting. Keep it up.`,
          }
        : attempt === 'partial'
        ? {
            icon: '◎',
            bgColor: 'bg-amber-50',
            labelColor: 'text-amber-800',
            label: 'Partial attempt detected',
            desc: `You made a partial attempt at your experiment${countAttempts ? ` — ${countAttempts} instance${countAttempts !== 1 ? 's' : ''} noted` : ''}. You're on the right track.`,
          }
        : confirmState === 'done' && confirmedValue
        ? {
            icon: '◈',
            bgColor: 'bg-emerald-50',
            labelColor: 'text-emerald-800',
            label: 'User confirmed attempt',
            desc: null,
          }
        : {
            icon: '◈',
            bgColor: 'bg-stone-50',
            labelColor: 'text-stone-700',
            label: 'No attempt detected',
            desc: null,
          };

    return (
      <div className="space-y-4">
        {/* Detection banner */}
        <section className="bg-white rounded-2xl border border-stone-200 overflow-hidden">
          <div className={`flex items-center gap-2.5 px-5 py-3.5 border-b border-stone-100 ${attemptConfig.bgColor}`}>
            <span className="text-base">{attemptConfig.icon}</span>
            <h3 className={`text-sm font-semibold ${attemptConfig.labelColor}`}>
              Experiment: {attemptConfig.label}
            </h3>
          </div>

          <div className="px-5 py-4 space-y-2">
            {attempt !== 'no' && (
              <p className="text-sm text-stone-700 leading-relaxed">{attemptConfig.desc}</p>
            )}

            {/* Evidence quotes from the transcript */}
            {attempt !== 'no' && detectionQuotes.length > 0 && (
              <div className="space-y-3">
                <div>
                  <p className="text-xs font-semibold text-stone-400 uppercase tracking-widest mb-1.5">
                    {attempt === 'yes' ? 'From the transcript' : 'What you said'}
                  </p>
                  {detectionQuotes.map((q, i) => (
                    <EvidenceQuote key={i} quote={q} />
                  ))}
                </div>

                {/* Coaching for partial attempts */}
                {attempt === 'partial' && detection?.coaching_note && (
                  <div>
                    <p className="text-xs font-semibold text-stone-400 uppercase tracking-widest mb-1.5">
                      What worked and what was missing
                    </p>
                    <p className="text-sm text-stone-700 leading-relaxed">
                      {detection.coaching_note}
                    </p>
                  </div>
                )}

                {attempt === 'partial' && detection?.suggested_rewrite && (
                  <div>
                    <p className="text-xs font-semibold text-stone-400 uppercase tracking-widest mb-1.5">
                      Next time, try something like
                    </p>
                    <blockquote className="border-l-4 border-emerald-300 pl-4 py-1 my-2 bg-emerald-50 rounded-r-md">
                      <p className="text-sm text-stone-700 italic">
                        &ldquo;{detection.suggested_rewrite}&rdquo;
                      </p>
                    </blockquote>
                  </div>
                )}
              </div>
            )}

            {/* Missed detection prompt */}
            {attempt === 'no' && confirmState === 'idle' && (
              <div className="space-y-2">
                <p className="text-sm text-stone-700 leading-relaxed">
                  The model didn&apos;t detect your experiment being tried in this meeting — but
                  it&apos;s possible we missed something. Did you attempt the experiment?
                </p>
                <div className="flex gap-2 pt-1">
                  <button
                    onClick={() => handleConfirm(true)}
                    className="px-4 py-2 bg-emerald-600 text-white rounded-xl text-xs font-semibold hover:bg-emerald-700 transition-colors"
                  >
                    Yes, I tried it
                  </button>
                  <button
                    onClick={() => handleConfirm(false)}
                    className="px-4 py-2 bg-white border border-stone-300 text-stone-700 rounded-xl text-xs font-semibold hover:bg-stone-50 transition-colors"
                  >
                    Not this time
                  </button>
                </div>
              </div>
            )}

            {attempt === 'no' && confirmState === 'loading' && (
              <p className="text-xs text-stone-400">Saving…</p>
            )}

            {attempt === 'no' && confirmState === 'done' && (
              <p className="text-sm text-stone-700 leading-relaxed">
                {confirmedValue
                  ? 'Thanks for letting us know! We\u2019ve recorded your attempt — the model doesn\u2019t always catch everything.'
                  : 'Got it — no worries. Just a gentle reminder to try again next time.'}
              </p>
            )}

            <p className="text-xs text-stone-400">
              Experiment {activeExp?.experiment_id as string}
            </p>
          </div>
        </section>

        {/* Full experiment tracker */}
        <h2 className="text-base font-semibold text-stone-800 mt-2">Current Experiment</h2>
        {activeExpData?.experiment ? (
          <ExperimentTracker
            experiment={activeExpData.experiment}
            events={activeExpData.recent_events}
            onComplete={() => router.push('/client')}
            onAbandon={() => router.push('/client')}
          />
        ) : (
          // Fallback while data is loading or if fetch failed
          <div className="bg-white rounded-2xl border border-stone-200 p-5 space-y-3">
            <p className="text-xs font-semibold text-stone-400 uppercase tracking-widest">
              Your experiment
            </p>
            <div className="flex gap-3 flex-wrap">
              <Link
                href="/client/experiment"
                className="px-5 py-2.5 bg-emerald-600 text-white rounded-xl text-sm font-semibold hover:bg-emerald-700 transition-colors"
              >
                View on My Experiment →
              </Link>
            </div>
          </div>
        )}
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Success banner */}
      <div className="bg-emerald-50 border border-emerald-200 rounded-2xl px-5 py-3.5 flex items-center gap-3">
        <span className="text-emerald-600 text-lg">✦</span>
        <div>
          <p className="text-sm font-semibold text-emerald-800">Analysis complete</p>
          <p className="text-xs text-emerald-600">Here's your personalised coaching feedback</p>
        </div>
      </div>

      <CoachingCard
        strengths={run.strengths}
        focus={run.focus}
        microExperiment={
          hasActiveExp ||
          proposedExperiments.length > 0 ||
          !!run.baseline_pack_id
            ? null
            : run.micro_experiment
        }
      />

      <ProposedExperimentSection />

      <ExperimentSection />

      {run.pattern_snapshot && run.pattern_snapshot.length > 0 && (
        <section>
          <p className="text-xs font-semibold text-stone-400 uppercase tracking-widest mb-3">
            Pattern snapshot
          </p>
          <PatternSnapshot patterns={run.pattern_snapshot} />
        </section>
      )}
    </div>
  );
}

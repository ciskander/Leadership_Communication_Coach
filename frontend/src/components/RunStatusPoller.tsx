'use client';

import { useState, useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { useRunPoller } from '@/hooks/useRunPoller';
import { CoachingCard } from './CoachingCard';
import { PatternSnapshot } from './PatternSnapshot';
import { ExperimentTracker } from './ExperimentTracker';
import { api } from '@/lib/api';
import type { Experiment, ActiveExperiment } from '@/lib/types';
import Link from 'next/link';

interface RunStatusPollerProps {
  runId: string;
  onComplete?: () => void;
}

export function RunStatusPoller({ runId, onComplete }: RunStatusPollerProps) {
  const { run, pollState, pollCount, retry } = useRunPoller(runId);
  const router = useRouter();

  const [confirmState, setConfirmState] = useState<'idle' | 'loading' | 'done'>('idle');
  const [completeState, setCompleteState] = useState<'idle' | 'loading' | 'done'>('idle');
  const [proposedExperiments, setProposedExperiments] = useState<Experiment[]>([]);
  const [acceptedExpId, setAcceptedExpId] = useState<string | null>(null);
  const [acceptLoading, setAcceptLoading] = useState(false);
  const [activeExpData, setActiveExpData] = useState<ActiveExperiment | null>(null);

  // When the run completes without an active experiment, fetch any proposed
  // experiments so the user can accept inline without going back to the dashboard.
  // When it completes WITH an active experiment, fetch the full experiment + events
  // so we can render ExperimentTracker inline.
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
      } else {
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
  const detection = et?.detection_in_this_meeting as Record<string, unknown> | null;

	const hasActiveExp =
	  !!activeExp &&
	  activeExp.status === 'active';

  const attempt = detection?.attempt as string | null;
  const countAttempts = detection?.count_attempts as number | null;
  const detectionQuotes = (detection?.quotes as Array<{ quote_text: string; speaker_label?: string }>) ?? [];
  const expRecordId = activeExp
    ? (run.experiment_tracking as Record<string, unknown> & { _record_id?: string })?._record_id ?? null
    : null;

  // ── Handlers ──────────────────────────────────────────────────────────────────

  async function handleConfirm(confirmed: boolean) {
    if (!activeExp || confirmState !== 'idle') return;
    setConfirmState('loading');
    try {
      // We need the experiment_record_id — it comes via the active_experiment
      // on the run's experiment_tracking. We store it in the run's
      // active experiment info if available, otherwise fall through gracefully.
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
            borderColor: 'border-emerald-200',
            labelColor: 'text-emerald-800',
            label: 'Nicely done!',
            desc: `The model detected ${countAttempts ?? 'multiple'} clear attempt${(countAttempts ?? 0) !== 1 ? 's' : ''} at your experiment in this meeting. Keep it up.`,
          }
        : attempt === 'partial'
        ? {
            icon: '◎',
            bgColor: 'bg-amber-50',
            borderColor: 'border-amber-200',
            labelColor: 'text-amber-800',
            label: 'Partial attempt detected',
            desc: `You made a partial attempt at your experiment${countAttempts ? ` — ${countAttempts} instance${countAttempts !== 1 ? 's' : ''} noted` : ''}. You're on the right track.`,
          }
        : {
            icon: '◈',
            bgColor: 'bg-stone-50',
            borderColor: 'border-stone-200',
            labelColor: 'text-stone-700',
            label: 'No attempt detected',
            desc: null,
          };

    return (
      <div className="space-y-4">
        {/* Detection banner */}
        <section
          className={`rounded-2xl border p-5 space-y-3 ${attemptConfig.bgColor} ${attemptConfig.borderColor}`}
        >
          <div className="flex items-center gap-2">
            <span className="text-base">{attemptConfig.icon}</span>
            <p className={`text-sm font-semibold ${attemptConfig.labelColor}`}>
              Experiment: {attemptConfig.label}
            </p>
          </div>

          {attempt !== 'no' && (
            <p className="text-sm text-stone-600 leading-relaxed">{attemptConfig.desc}</p>
          )}

          {/* Evidence quotes from the transcript */}
          {attempt !== 'no' && detectionQuotes.length > 0 && (
            <div className="space-y-2 pt-1">
              {detectionQuotes.map((q, i) => (
                <blockquote
                  key={i}
                  className="border-l-2 border-current opacity-60 pl-3 py-1"
                >
                  <p className="text-xs leading-relaxed italic">
                    &ldquo;{q.quote_text}&rdquo;
                  </p>
                  {q.speaker_label && (
                    <p className="text-xs mt-0.5 font-medium not-italic">
                      — {q.speaker_label}
                    </p>
                  )}
                </blockquote>
              ))}
            </div>
          )}

          {/* Missed detection prompt */}
          {attempt === 'no' && confirmState === 'idle' && (
            <div className="space-y-2">
              <p className="text-sm text-stone-600 leading-relaxed">
                The model didn't detect your experiment being tried in this meeting — but it's
                possible we missed something. Did you attempt the experiment?
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
            <p className="text-sm text-stone-600 leading-relaxed">
              Got it — no worries. Just a gentle reminder to try again next time.
            </p>
          )}

          <p className="text-xs text-stone-400">
            Experiment {activeExp?.experiment_id as string}
          </p>
        </section>

        {/* Full experiment tracker */}
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
          <PatternSnapshot patterns={run.pattern_snapshot as never} />
        </section>
      )}
    </div>
  );
}

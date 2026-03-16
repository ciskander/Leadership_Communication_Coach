'use client';

import { useState, useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { useRunPoller } from '@/hooks/useRunPoller';
import { CoachingCard } from './CoachingCard';
import { PatternSnapshot, buildTrendData } from './PatternSnapshot';
import type { PatternTrendData } from './PatternSnapshot';
import { ExperimentTracker } from './ExperimentTracker';
import { api } from '@/lib/api';
import type { Experiment, ActiveExperiment, PatternSnapshotItem } from '@/lib/types';
import { EvidenceQuote } from './EvidenceQuote';
import Link from 'next/link';
import { STRINGS } from '@/config/strings';

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
  const [trendData, setTrendData] = useState<Record<string, PatternTrendData> | undefined>(undefined);

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
  // Note: we fetch this data even when gate1_pass is false, because the
  // backend still returns full analysis data and the UI should display it.
  useEffect(() => {
    if (run?.status === 'complete') {
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

      // Fetch trend data for sparklines (non-blocking, best-effort)
      // Scope to baseline through the current run so the sparkline reflects
      // history up to this meeting, not the full timeline.
      api.getClientProgress()
        .then((progress) => {
          const trends = buildTrendData(progress.pattern_history, progress.trend_window_size, runId);
          setTrendData(Object.keys(trends).length > 0 ? trends : undefined);
        })
        .catch(() => {});
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
            {pollCount > 20 ? STRINGS.runStatusPoller.stillWorking : STRINGS.runStatusPoller.analysing}
          </p>
          <p className="text-xs text-stone-400">{STRINGS.runStatusPoller.usuallyTakes}</p>
        </div>
      </div>
    );
  }

  if (pollState === 'timeout') {
    return (
      <div className="bg-white rounded border border-stone-200 p-8 text-center space-y-4">
        <div className="flex justify-center"><svg viewBox="0 0 16 16" fill="none" className="w-8 h-8 text-cv-amber-600" aria-hidden="true"><circle cx="8" cy="9" r="6" stroke="currentColor" strokeWidth={1.4}/><path d="M8 6v3.5l2 1.5" stroke="currentColor" strokeWidth={1.4} strokeLinecap="round" strokeLinejoin="round"/><path d="M8 3V1" stroke="currentColor" strokeWidth={1.4} strokeLinecap="round"/></svg></div>
        <p className="text-sm font-medium text-stone-700">{STRINGS.runStatusPoller.timeoutTitle}</p>
        <p className="text-xs text-stone-400">{STRINGS.runStatusPoller.timeoutDesc}</p>
        <button
          onClick={retry}
          className="px-5 py-2.5 bg-emerald-600 text-white rounded text-sm font-medium hover:bg-emerald-700 transition-colors"
        >
          {STRINGS.runStatusPoller.checkAgain}
        </button>
      </div>
    );
  }

  if (pollState === 'error' || run.status === 'error') {
    return (
      <div className="bg-white rounded border border-rose-200 p-8 text-center space-y-4">
        <div className="flex justify-center"><svg viewBox="0 0 16 16" fill="none" className="w-8 h-8 text-rose-500" aria-hidden="true"><path d="M8 1L1 14h14L8 1z" stroke="currentColor" strokeWidth={1.4} strokeLinejoin="round"/><path d="M8 6v4" stroke="currentColor" strokeWidth={1.4} strokeLinecap="round"/><circle cx="8" cy="12" r="0.5" fill="currentColor"/></svg></div>
        <p className="text-sm font-medium text-rose-700">{STRINGS.runStatusPoller.errorTitle}</p>
        <p className="text-xs text-stone-400">
          {run?.error ? JSON.stringify(run.error) : STRINGS.runStatusPoller.errorFallback}
        </p>
        <button
          onClick={retry}
          className="px-5 py-2.5 bg-emerald-600 text-white rounded text-sm font-medium hover:bg-emerald-700 transition-colors"
        >
          {STRINGS.common.retry}
        </button>
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
  const targetSpeaker = run?.target_speaker_label ?? null;
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
      // Refresh experiment data so the tracker shows updated attempt counts
      api.getActiveExperiment()
        .then(setActiveExpData)
        .catch(() => {});
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
      router.push('/client/experiment');
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
        <section className="bg-emerald-50 border border-emerald-200 rounded p-5 flex items-center gap-3">
          <svg viewBox="0 0 16 16" fill="none" className="w-5 h-5 shrink-0 text-cv-teal-600" aria-hidden="true"><circle cx="8" cy="8" r="7" stroke="currentColor" strokeWidth={1.4}/><path d="M5 8l2 2 4-4" stroke="currentColor" strokeWidth={1.4} strokeLinecap="round" strokeLinejoin="round"/></svg>
          <div>
            <p className="text-sm font-semibold text-emerald-800">{STRINGS.runStatusPoller.experimentAccepted}</p>
            <Link href="/client" className="text-xs text-emerald-600 hover:text-emerald-800 underline">
              {STRINGS.runStatusPoller.viewOnDashboard}
            </Link>
          </div>
        </section>
      );
    }

    return (
      <section className="bg-violet-50 border border-violet-200 rounded p-5 space-y-3">
        <div className="flex items-center gap-2">
          <svg viewBox="0 0 16 16" fill="none" className="w-4 h-4 shrink-0 text-violet-600" aria-hidden="true"><path d="M6 1v5L2 14h12L10 6V1" stroke="currentColor" strokeWidth={1.4} strokeLinejoin="round"/><path d="M4.5 1h7" stroke="currentColor" strokeWidth={1.4} strokeLinecap="round"/></svg>
          <p className="text-sm font-semibold text-violet-800">{STRINGS.runStatusPoller.experimentReady}</p>
        </div>
        <div className="space-y-1">
          <span className="text-xs font-semibold text-stone-400 uppercase tracking-widest">
            {exp.pattern_id.replace(/_/g, ' ')}
          </span>
          <p className="text-sm font-semibold text-stone-900 leading-snug">{exp.title}</p>
        </div>
        <div className="bg-white rounded p-3">
          <p className="text-xs font-semibold text-stone-400 uppercase tracking-widest mb-1">{STRINGS.common.whatToDo}</p>
          <p className="text-xs text-stone-600 leading-relaxed">{exp.instruction}</p>
        </div>
        <div className="bg-white rounded p-3">
          <p className="text-xs font-semibold text-stone-400 uppercase tracking-widest mb-1">{STRINGS.common.successLooksLike}</p>
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
            className="px-4 py-2 bg-emerald-600 text-white rounded text-xs font-semibold hover:bg-emerald-700 transition-colors disabled:opacity-60"
          >
            {acceptLoading ? STRINGS.common.accepting : STRINGS.common.acceptExperiment}
          </button>
          <Link href="/client/experiment?expand=1" className="text-xs text-stone-500 hover:text-stone-700 transition-colors">
            {STRINGS.experimentPage.seeMoreOptions}
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
            icon: <svg viewBox="0 0 16 16" fill="none" className="w-4 h-4 shrink-0 text-cv-teal-600" aria-hidden="true"><circle cx="8" cy="8" r="7" stroke="currentColor" strokeWidth={1.4}/><path d="M5 8l2 2 4-4" stroke="currentColor" strokeWidth={1.4} strokeLinecap="round" strokeLinejoin="round"/></svg>,
            bgColor: 'bg-emerald-50',
            labelColor: 'text-emerald-800',
            label: STRINGS.runStatusPoller.nicelyDone,
            desc: STRINGS.runStatusPoller.clearAttempts(countAttempts ?? 'multiple'),
          }
        : attempt === 'partial'
        ? {
            icon: <svg viewBox="0 0 16 16" fill="none" className="w-4 h-4 shrink-0 text-cv-amber-600" aria-hidden="true"><circle cx="8" cy="8" r="7" stroke="currentColor" strokeWidth={1.4}/><path d="M5 8h6" stroke="currentColor" strokeWidth={1.4} strokeLinecap="round"/></svg>,
            bgColor: 'bg-amber-50',
            labelColor: 'text-amber-800',
            label: STRINGS.runStatusPoller.partialAttemptDetected,
            desc: STRINGS.runStatusPoller.partialAttemptDesc(countAttempts),
          }
        : confirmState === 'done' && confirmedValue
        ? {
            icon: <svg viewBox="0 0 16 16" fill="none" className="w-4 h-4 shrink-0 text-cv-teal-600" aria-hidden="true"><path d="M11.5 1.5l3 3-9 9H2.5v-3l9-9z" stroke="currentColor" strokeWidth={1.4} strokeLinejoin="round"/><path d="M9.5 3.5l3 3" stroke="currentColor" strokeWidth={1.4}/></svg>,
            bgColor: 'bg-emerald-50',
            labelColor: 'text-emerald-800',
            label: STRINGS.runStatusPoller.userConfirmedAttempt,
            desc: null,
          }
        : {
            icon: <svg viewBox="0 0 16 16" fill="none" className="w-4 h-4 shrink-0 text-stone-400" aria-hidden="true"><circle cx="8" cy="8" r="7" stroke="currentColor" strokeWidth={1.4}/><path d="M6 6h4M6 10h4" stroke="currentColor" strokeWidth={1.4} strokeLinecap="round"/></svg>,
            bgColor: 'bg-stone-50',
            labelColor: 'text-stone-700',
            label: STRINGS.runStatusPoller.noAttemptDetected,
            desc: null,
          };

    return (
      <div className="space-y-4">
        {/* Detection banner */}
        <section className="bg-white rounded border border-stone-200 overflow-hidden">
          <div className={`flex items-center gap-2.5 px-5 py-3.5 border-b border-stone-100 ${attemptConfig.bgColor}`}>
            {attemptConfig.icon}
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
                    {attempt === 'yes' ? STRINGS.runStatusPoller.fromTranscript : STRINGS.runStatusPoller.whatYouSaid}
                  </p>
                  {detectionQuotes.map((q, i) => (
                    <EvidenceQuote key={i} quote={q} targetSpeaker={targetSpeaker} />
                  ))}
                </div>

                {/* Coaching for partial attempts */}
                {attempt === 'partial' && detection?.coaching_note && (
                  <div>
                    <p className="text-xs font-semibold text-stone-400 uppercase tracking-widest mb-1.5">
                      {STRINGS.runStatusPoller.whatWorkedMissing}
                    </p>
                    <p className="text-sm text-stone-700 leading-relaxed">
                      {detection.coaching_note}
                    </p>
                  </div>
                )}

                {attempt === 'partial' && detection?.suggested_rewrite && (
                  <div>
                    <p className="text-xs font-semibold text-stone-400 uppercase tracking-widest mb-1.5">
                      {STRINGS.common.nextTimeTry}
                    </p>
                    <blockquote className="border-l-4 border-cv-teal-700 pl-4 py-1 my-2 bg-emerald-50 rounded-r-md">
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
                  {STRINGS.runStatusPoller.missedDetectionPrompt}
                </p>
                <div className="flex gap-2 pt-1">
                  <button
                    onClick={() => handleConfirm(true)}
                    className="px-4 py-2 bg-emerald-600 text-white rounded text-xs font-semibold hover:bg-emerald-700 transition-colors"
                  >
                    {STRINGS.runStatusPoller.yesITriedIt}
                  </button>
                  <button
                    onClick={() => handleConfirm(false)}
                    className="px-4 py-2 bg-white border border-stone-300 text-stone-700 rounded text-xs font-semibold hover:bg-stone-50 transition-colors"
                  >
                    {STRINGS.runStatusPoller.notThisTime}
                  </button>
                </div>
              </div>
            )}

            {attempt === 'no' && confirmState === 'loading' && (
              <p className="text-xs text-stone-400">{STRINGS.common.saving}</p>
            )}

            {attempt === 'no' && confirmState === 'done' && (
              <p className="text-sm text-stone-700 leading-relaxed">
                {confirmedValue
                  ? STRINGS.runStatusPoller.confirmedYes
                  : STRINGS.runStatusPoller.confirmedNo}
              </p>
            )}

            <p className="text-xs text-stone-400">
              Experiment {activeExp?.experiment_id as string}
            </p>
          </div>
        </section>

        {/* Full experiment tracker */}
        <h2 className="text-base font-semibold text-stone-800 mt-2">{STRINGS.runStatusPoller.currentExperiment}</h2>
        {activeExpData?.experiment ? (
          <ExperimentTracker
            experiment={activeExpData.experiment}
            events={activeExpData.recent_events}
            onComplete={() => router.push('/client/experiment')}
            onPark={() => router.push('/client/experiment')}
          />
        ) : (
          // Fallback while data is loading or if fetch failed
          <div className="bg-white rounded border border-stone-200 p-5 space-y-3">
            <p className="text-xs font-semibold text-stone-400 uppercase tracking-widest">
              {STRINGS.runStatusPoller.yourExperiment}
            </p>
            <div className="flex gap-3 flex-wrap">
              <Link
                href="/client/experiment"
                className="px-5 py-2.5 bg-emerald-600 text-white rounded text-sm font-semibold hover:bg-emerald-700 transition-colors"
              >
                {STRINGS.runStatusPoller.viewOnMyExperiment}
              </Link>
            </div>
          </div>
        )}
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Status banner */}
      {run.gate1_pass === false ? (
        <div className="bg-amber-50 border border-amber-200 rounded px-5 py-3.5 flex items-start gap-3">
          <svg viewBox="0 0 16 16" fill="none" className="w-5 h-5 shrink-0 text-cv-amber-600 mt-0.5" aria-hidden="true"><path d="M8 1L1 14h14L8 1z" stroke="currentColor" strokeWidth={1.4} strokeLinejoin="round"/><path d="M8 6v4" stroke="currentColor" strokeWidth={1.4} strokeLinecap="round"/><circle cx="8" cy="12" r="0.5" fill="currentColor"/></svg>
          <div>
            <p className="text-sm font-semibold text-amber-800">{STRINGS.runStatusPoller.qualityCheckFailed}</p>
            <p className="text-xs text-amber-600">{STRINGS.runStatusPoller.qualityCheckDesc}</p>
          </div>
        </div>
      ) : (
        <div className="bg-emerald-50 border border-emerald-200 rounded px-5 py-3.5 flex items-center gap-3">
          <svg viewBox="0 0 16 16" fill="none" className="w-5 h-5 shrink-0 text-cv-teal-600" aria-hidden="true"><circle cx="8" cy="8" r="7" stroke="currentColor" strokeWidth={1.4}/><path d="M5 8l2 2 4-4" stroke="currentColor" strokeWidth={1.4} strokeLinecap="round" strokeLinejoin="round"/></svg>
          <div>
            <p className="text-sm font-semibold text-emerald-800">{STRINGS.runStatusPoller.analysisComplete}</p>
            <p className="text-xs text-emerald-600">{STRINGS.runStatusPoller.analysisFeedback}</p>
          </div>
        </div>
      )}

      <CoachingCard
        strengths={run.strengths}
        focus={run.focus}
        targetSpeaker={targetSpeaker}
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
            {STRINGS.runStatusPoller.patternSnapshot}
          </p>
          <PatternSnapshot patterns={run.pattern_snapshot} targetSpeaker={targetSpeaker} trendData={trendData} />
        </section>
      )}
    </div>
  );
}

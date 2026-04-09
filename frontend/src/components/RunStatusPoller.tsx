'use client';

import { useState, useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { useRunPoller } from '@/hooks/useRunPoller';
import { CoachingCard } from './CoachingCard';
import { PatternSnapshot, buildTrendData } from './PatternSnapshot';
import type { PatternTrendData } from './PatternSnapshot';
import { ExperimentTracker } from './ExperimentTracker';
import { api } from '@/lib/api';
import type { Experiment, ActiveExperiment, PatternSnapshotItem, CoachingTheme, QuoteObject } from '@/lib/types';
import { EvidenceQuote, EvidenceQuoteList } from './EvidenceQuote';
import Link from 'next/link';
import { STRINGS } from '@/config/strings';

// ─── Theme card sub-components ──────────────────────────────────────────────

/** Renders a single strength-nature coaching theme (teal section). */
function StrengthThemeCard({
  theme,
  targetSpeaker,
}: {
  theme: CoachingTheme;
  targetSpeaker: string | null;
}) {
  const [expanded, setExpanded] = useState(false);
  const themeQuotes = theme.quotes ?? [];
  const successQuotes = theme.best_success_span_id
    ? themeQuotes.filter((q) => q.span_id === theme.best_success_span_id)
    : [];
  const hasDetail = successQuotes.length > 0;

  return (
    <div className="px-5 py-4">
      <div className="min-w-0">
        <p className="text-sm font-medium text-stone-800 mb-1">{theme.theme}</p>
        <p className="text-sm text-stone-600 leading-relaxed">{theme.explanation}</p>
      </div>
      {expanded && successQuotes.length > 0 && (
        <div className="mt-3">
          <p className="text-2xs font-medium text-cv-stone-400 uppercase tracking-widest mb-1.5">
            {STRINGS.runStatusPoller.whatYouDidWell}
          </p>
          <EvidenceQuoteList quotes={successQuotes} targetSpeaker={targetSpeaker} />
        </div>
      )}
      {hasDetail && (
        <div className="flex justify-end mt-2">
          <button
            type="button"
            onClick={() => setExpanded(!expanded)}
            className="text-xs text-cv-teal-600 hover:text-cv-teal-800 whitespace-nowrap"
          >
            {expanded ? STRINGS.runStatusPoller.hideDetails : STRINGS.runStatusPoller.showDetails}
          </button>
        </div>
      )}
    </div>
  );
}

/** Renders a single developmental/mixed coaching theme (rose section). */
function DevelopmentalThemeCard({
  theme,
  showPriorityBadge,
  targetSpeaker,
}: {
  theme: CoachingTheme;
  showPriorityBadge: boolean;
  targetSpeaker: string | null;
}) {
  const [expanded, setExpanded] = useState(false);
  const themeQuotes = theme.quotes ?? [];
  const successQuotes = theme.best_success_span_id
    ? themeQuotes.filter((q) => q.span_id === theme.best_success_span_id)
    : [];
  const rewriteQuotes = theme.rewrite_for_span_id
    ? themeQuotes.filter((q) => q.span_id === theme.rewrite_for_span_id)
    : [];
  const hasDetail = !!(theme.coaching_note || theme.suggested_rewrite || successQuotes.length > 0 || rewriteQuotes.length > 0);

  // Mode A: best_success_span_id is set AND coaching_note is set
  // Mode B: best_success_span_id is null AND coaching_note is set
  const modeA = !!theme.best_success_span_id && !!theme.coaching_note;

  return (
    <div className="px-5 py-4">
      <div className="min-w-0">
        {showPriorityBadge && (
          <div className="flex items-center gap-2 mb-1.5">
            <span className={`text-xs font-medium px-2 py-0.5 rounded-full ${
              theme.priority === 'primary'
                ? 'bg-cv-rose-100 text-cv-rose-700 border border-cv-rose-700'
                : 'bg-cv-amber-50 text-cv-amber-700 border border-cv-amber-700'
            }`}>
              {theme.priority === 'primary'
                ? STRINGS.runStatusPoller.primaryThemeLabel
                : STRINGS.runStatusPoller.secondaryThemeLabel}
            </span>
          </div>
        )}
        <p className="text-sm font-medium text-stone-800 mb-1">{theme.theme}</p>
        <p className="text-sm text-stone-600 leading-relaxed">{theme.explanation}</p>
      </div>

      {expanded && hasDetail && (
        <div className="mt-3 space-y-3">
          {/* Mode A: What you did well + coaching note */}
          {modeA && successQuotes.length > 0 && (
            <div>
              <p className="text-2xs font-medium text-cv-stone-400 uppercase tracking-widest mb-1.5">
                {STRINGS.runStatusPoller.whatYouDidWell}
              </p>
              <EvidenceQuoteList quotes={successQuotes} targetSpeaker={targetSpeaker} />
            </div>
          )}

          {/* Mode A: "Where you can improve" heading; Mode B: "What worked and what was missing" heading */}
          {theme.coaching_note && (
            <div>
              <p className="text-2xs font-medium text-cv-stone-400 uppercase tracking-widest mb-1.5">
                {modeA ? STRINGS.common.whereYouCanImprove : STRINGS.runStatusPoller.whatWorkedMissing}
              </p>
              <p className="text-sm text-cv-stone-700 leading-relaxed">{theme.coaching_note}</p>
            </div>
          )}

          {/* For example, in this meeting you said */}
          {rewriteQuotes.length > 0 && (
            <div>
              <p className="text-2xs font-medium text-cv-stone-400 uppercase tracking-widest mb-1.5">
                {STRINGS.common.forExampleYouSaid}
              </p>
              <EvidenceQuoteList quotes={rewriteQuotes} targetSpeaker={targetSpeaker} />
            </div>
          )}

          {/* Next time, try something like */}
          {theme.suggested_rewrite && (
            <div>
              <p className="text-2xs font-medium text-cv-stone-400 uppercase tracking-widest mb-1.5">
                {STRINGS.common.nextTimeTry}
              </p>
              <blockquote className="border-l-[2px] border-cv-teal-700 pl-4 py-1 my-2 bg-cv-teal-50 rounded-r-md">
                <p className="text-sm text-cv-stone-700 italic">
                  &ldquo;{theme.suggested_rewrite}&rdquo;
                </p>
              </blockquote>
            </div>
          )}
        </div>
      )}
      {hasDetail && (
        <div className="flex justify-end mt-2">
          <button
            type="button"
            onClick={() => setExpanded(!expanded)}
            className="text-xs text-cv-rose-700 hover:text-cv-rose-700/80 whitespace-nowrap"
          >
            {expanded ? STRINGS.runStatusPoller.hideDetails : STRINGS.runStatusPoller.showDetails}
          </button>
        </div>
      )}
    </div>
  );
}

// ─── Main component ─────────────────────────────────────────────────────────

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
  const [expCheckDone, setExpCheckDone] = useState(false);
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
        // Also check if there's an active experiment that was accepted
        // after this run was analyzed (run data reflects analysis-time state)
        api.getActiveExperiment()
          .then((data) => { if (data?.experiment) setActiveExpData(data); })
          .catch(() => {})
          .finally(() => setExpCheckDone(true));
      } else if (run.active_experiment_detail) {
        // Use experiment data embedded in the run response
        setActiveExpData({
          experiment: run.active_experiment_detail,
          recent_events: run.active_experiment_events ?? [],
        });
        setExpCheckDone(true);
      } else {
        // Fallback: fetch from the dedicated endpoint
        api.getActiveExperiment()
          .then(setActiveExpData)
          .catch(() => {})
          .finally(() => setExpCheckDone(true));
      }

      // Fetch trend data for sparklines (non-blocking, best-effort)
      // Scope to baseline through the current run so the sparkline reflects
      // history up to this meeting, not the full timeline.
      api.getClientProgress()
        .then((progress) => {
          const trends = buildTrendData(progress.pattern_history, 1, runId);
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
          <div className="w-14 h-14 rounded-full border-2 border-cv-stone-100" />
          <div className="absolute inset-0 w-14 h-14 rounded-full border-2 border-cv-teal-600 border-t-transparent animate-spin" />
        </div>
        <div className="text-center space-y-1">
          <p className="text-sm font-medium text-cv-stone-700">
            {pollCount > 20 ? STRINGS.runStatusPoller.stillWorking : STRINGS.runStatusPoller.analysing}
          </p>
          <p className="text-xs text-cv-stone-400">{STRINGS.runStatusPoller.usuallyTakes}</p>
        </div>
      </div>
    );
  }

  if (pollState === 'timeout') {
    return (
      <div className="bg-white rounded border border-cv-warm-300 p-8 text-center space-y-4">
        <div className="flex justify-center"><svg viewBox="0 0 16 16" fill="none" className="w-8 h-8 text-cv-amber-600" aria-hidden="true"><circle cx="8" cy="9" r="6" stroke="currentColor" strokeWidth={1.4}/><path d="M8 6v3.5l2 1.5" stroke="currentColor" strokeWidth={1.4} strokeLinecap="round" strokeLinejoin="round"/><path d="M8 3V1" stroke="currentColor" strokeWidth={1.4} strokeLinecap="round"/></svg></div>
        <p className="text-sm font-medium text-cv-stone-700">{STRINGS.runStatusPoller.timeoutTitle}</p>
        <p className="text-xs text-cv-stone-400">{STRINGS.runStatusPoller.timeoutDesc}</p>
        <button
          onClick={retry}
          className="px-5 py-2.5 bg-cv-teal-600 text-white rounded text-sm font-medium hover:bg-cv-teal-800 transition-colors"
        >
          {STRINGS.runStatusPoller.checkAgain}
        </button>
      </div>
    );
  }

  if (pollState === 'error' || run.status === 'error') {
    return (
      <div className="bg-white rounded border border-cv-red-100 p-8 text-center space-y-4">
        <div className="flex justify-center"><svg viewBox="0 0 16 16" fill="none" className="w-8 h-8 text-cv-red-400" aria-hidden="true"><path d="M8 1L1 14h14L8 1z" stroke="currentColor" strokeWidth={1.4} strokeLinejoin="round"/><path d="M8 6v4" stroke="currentColor" strokeWidth={1.4} strokeLinecap="round"/><circle cx="8" cy="12" r="0.5" fill="currentColor"/></svg></div>
        <p className="text-sm font-medium text-cv-red-600">{STRINGS.runStatusPoller.errorTitle}</p>
        <p className="text-xs text-cv-stone-400">
          {run?.error ? JSON.stringify(run.error) : STRINGS.runStatusPoller.errorFallback}
        </p>
        <button
          onClick={retry}
          className="px-5 py-2.5 bg-cv-teal-600 text-white rounded text-sm font-medium hover:bg-cv-teal-800 transition-colors"
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

	const hasActiveExpFromRun =
	  !!activeExp &&
	  activeExp.status === 'active';
	// Also consider an active experiment that was accepted after this run
	const hasActiveExp = hasActiveExpFromRun || (activeExpData?.experiment?.status === 'active');

  const attempt = detection?.attempt ?? null;
  const countAttempts = detection?.count_attempts ?? null;
  const detectionQuotes = detection?.quotes ?? [];
  const targetSpeaker = run?.target_speaker_label ?? null;
  const graduationRec = et?.graduation_recommendation as {
    recommendation: string;
    rationale: string;
    park_reason: string | null;
  } | null;
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
      router.push('/client/experiment?action=completed');
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
        <section className="bg-cv-teal-50 border border-cv-teal-100 rounded p-5 flex items-center gap-3">
          <svg viewBox="0 0 16 16" fill="none" className="w-5 h-5 shrink-0 text-cv-teal-600" aria-hidden="true"><circle cx="8" cy="8" r="7" stroke="currentColor" strokeWidth={1.4}/><path d="M5 8l2 2 4-4" stroke="currentColor" strokeWidth={1.4} strokeLinecap="round" strokeLinejoin="round"/></svg>
          <div>
            <p className="text-sm font-medium text-cv-teal-800">{STRINGS.runStatusPoller.experimentAccepted}</p>
            <Link href="/client" className="text-xs text-cv-teal-600 hover:text-cv-teal-800 underline">
              {STRINGS.runStatusPoller.viewOnDashboard}
            </Link>
          </div>
        </section>
      );
    }

    return (
      <section className="bg-white rounded border border-cv-warm-300 p-5 space-y-4">
        <div className="space-y-1">
          {(exp.related_patterns?.length ? exp.related_patterns : exp.pattern_id ? [exp.pattern_id] : []).length > 0 && (
            <span className="text-2xs font-medium text-cv-stone-400 uppercase tracking-widest">
              {(exp.related_patterns?.length ? exp.related_patterns : [exp.pattern_id!])
                .map(pid => STRINGS.patternLabels[pid] ?? pid.replace(/_/g, ' '))
                .join(', ')}
            </span>
          )}
          <p className="text-sm font-medium text-cv-stone-900 leading-snug">{exp.title}</p>
        </div>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
          <div className="bg-cv-warm-100 rounded p-3">
            <p className="text-2xs font-medium text-cv-stone-400 uppercase tracking-widest mb-1.5">{STRINGS.common.whatToDo}</p>
            <p className="text-xs text-cv-stone-600 font-light leading-relaxed">{exp.instruction}</p>
          </div>
          <div className="bg-cv-warm-100 rounded p-3">
            <p className="text-2xs font-medium text-cv-stone-400 uppercase tracking-widest mb-1.5">{STRINGS.common.successLooksLike}</p>
            <p className="text-xs text-cv-stone-600 font-light leading-relaxed">{exp.success_marker}</p>
          </div>
        </div>
        <div className="flex items-center gap-3">
          <button
            onClick={async () => {
              if (acceptLoading) return;
              setAcceptLoading(true);
              try {
                await api.acceptExperiment(exp.experiment_record_id);
                setAcceptedExpId(exp.experiment_record_id);
                // Fetch active experiment data so ExperimentSection renders
                api.getActiveExperiment()
                  .then(setActiveExpData)
                  .catch(() => {});
              } catch {
                // non-fatal — user can always accept from the dashboard
              } finally {
                setAcceptLoading(false);
              }
            }}
            disabled={acceptLoading}
            className="px-4 py-2 bg-cv-teal-600 text-cv-teal-50 rounded text-xs font-medium hover:bg-cv-teal-800 transition-colors disabled:opacity-50"
          >
            {acceptLoading ? STRINGS.common.accepting : STRINGS.common.acceptExperiment}
          </button>
          <Link href="/client/experiment?expand=1" className="text-xs text-cv-stone-400 hover:text-cv-stone-600 transition-colors">
            {STRINGS.experimentPage.seeMoreOptions}
          </Link>
        </div>
      </section>
    );
  }

  // ── Attempt history (expandable, rendered at bottom of Experiment section) ──

  function AttemptHistorySection({
    sortedEvents,
    summaryText,
    attemptStyles,
    humanStyles,
  }: {
    sortedEvents: { event_id?: string; id?: string; attempt?: string; meeting_date?: string; created_at?: string; human_confirmed?: string }[];
    summaryText: string;
    attemptStyles: Record<string, { color: string; dot: string; bg: string; label: string; dateColor?: string }>;
    humanStyles: Record<string, { label: string; color: string; border: string }>;
  }) {
    const [historyOpen, setHistoryOpen] = useState(false);

    return (
      <div>
        <p className="text-2xs font-semibold uppercase tracking-[0.14em] text-cv-amber-800 mb-1.5">
          {STRINGS.experimentTracker.attemptHistory}
        </p>
        {sortedEvents.length > 0 ? (
          <>
            <button
              onClick={() => setHistoryOpen(!historyOpen)}
              className="w-full flex items-center justify-between gap-2 text-sm text-cv-stone-600 leading-relaxed hover:text-cv-stone-800 transition-colors"
            >
              <span>{summaryText}</span>
              <svg
                viewBox="0 0 16 16"
                fill="none"
                className={`w-3.5 h-3.5 shrink-0 text-cv-stone-400 transition-transform duration-200 ${historyOpen ? 'rotate-180' : ''}`}
                aria-hidden="true"
              >
                <path d="M4 6l4 4 4-4" stroke="currentColor" strokeWidth={1.5} strokeLinecap="round" strokeLinejoin="round" />
              </svg>
            </button>
            {historyOpen && (
              <ul className="space-y-1.5 mt-2">
                {sortedEvents.map((ev, i) => {
                  const cfg = attemptStyles[ev.attempt ?? 'no'] ?? attemptStyles.no;
                  const humanCfg = ev.human_confirmed ? humanStyles[ev.human_confirmed] : undefined;
                  const displayDate = ev.meeting_date || ev.created_at;
                  return (
                    <li key={ev.event_id ?? ev.id ?? i} className={`flex items-center gap-2 rounded px-3 py-2 ${cfg.bg}`}>
                      <span className={`w-2 h-2 rounded-full shrink-0 ${cfg.dot}`} />
                      <span className={`text-xs font-semibold ${cfg.color}`}>{cfg.label}</span>
                      {humanCfg && (
                        <span className={`text-xs font-medium px-2 py-0.5 rounded-full bg-white border ${humanCfg.border} ${humanCfg.color}`} title={STRINGS.humanConfirmation.tooltip}>
                          {humanCfg.label}
                        </span>
                      )}
                      {displayDate && (
                        <span className={`text-xs ml-auto shrink-0 tabular-nums ${cfg.dateColor ?? 'text-cv-stone-400'}`}>
                          {new Date(displayDate).toLocaleDateString('en-US', { month: 'short', day: 'numeric' })}
                        </span>
                      )}
                    </li>
                  );
                })}
              </ul>
            )}
          </>
        ) : (
          <p className="text-sm text-cv-stone-600 leading-relaxed">{summaryText}</p>
        )}
      </div>
    );
  }

  // ── Experiment section ─────────────────────────────────────────────────────

  function ExperimentSection() {
    const [detailOpen, setDetailOpen] = useState(false);
    if (!hasActiveExp) return null;

    const hasDetails =
      (attempt === 'yes' && detectionQuotes.length > 0) ||
      (attempt === 'partial' && detectionQuotes.length > 0);

    const attemptConfig =
      attempt === 'yes'
        ? {
            icon: <svg viewBox="0 0 16 16" fill="none" className="w-4 h-4 shrink-0 text-cv-teal-600" aria-hidden="true"><circle cx="8" cy="8" r="7" stroke="currentColor" strokeWidth={1.4}/><path d="M5 8l2 2 4-4" stroke="currentColor" strokeWidth={1.4} strokeLinecap="round" strokeLinejoin="round"/></svg>,
            bgColor: 'bg-cv-teal-50',
            labelColor: 'text-cv-teal-800',
            label: STRINGS.runStatusPoller.nicelyDone,
            desc: STRINGS.runStatusPoller.clearAttempts(countAttempts ?? 'multiple'),
          }
        : attempt === 'partial'
        ? {
            icon: <svg viewBox="0 0 16 16" fill="none" className="w-4 h-4 shrink-0 text-cv-amber-600" aria-hidden="true"><circle cx="8" cy="8" r="7" stroke="currentColor" strokeWidth={1.4}/><path d="M5 8h6" stroke="currentColor" strokeWidth={1.4} strokeLinecap="round"/></svg>,
            bgColor: 'bg-cv-amber-50',
            labelColor: 'text-cv-amber-800',
            label: STRINGS.runStatusPoller.partialAttemptDetected,
            desc: STRINGS.runStatusPoller.partialAttemptDesc(countAttempts),
          }
        : confirmState === 'done' && confirmedValue
        ? {
            icon: <svg viewBox="0 0 16 16" fill="none" className="w-4 h-4 shrink-0 text-cv-teal-600" aria-hidden="true"><path d="M6 1v5L2 14h12L10 6V1" stroke="currentColor" strokeWidth={1.4} strokeLinejoin="round"/><path d="M4.5 1h7" stroke="currentColor" strokeWidth={1.4} strokeLinecap="round"/></svg>,
            bgColor: 'bg-cv-teal-50',
            labelColor: 'text-cv-teal-800',
            label: STRINGS.runStatusPoller.userConfirmedAttempt,
            desc: null,
          }
        : {
            icon: <svg viewBox="0 0 16 16" fill="none" className="w-4 h-4 shrink-0 text-cv-stone-400" aria-hidden="true"><path d="M6 1v5L2 14h12L10 6V1" stroke="currentColor" strokeWidth={1.4} strokeLinejoin="round"/><path d="M4.5 1h7" stroke="currentColor" strokeWidth={1.4} strokeLinecap="round"/></svg>,
            bgColor: 'bg-cv-warm-50',
            labelColor: 'text-cv-stone-700',
            label: STRINGS.runStatusPoller.noAttemptDetected,
            desc: null,
          };

    return (
      <section className="bg-white rounded border border-cv-amber-800 overflow-hidden">
        {/* Section header */}
        <div className="flex items-center gap-2.5 px-5 py-3.5 border-b border-cv-warm-300 bg-cv-amber-800">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.7} strokeLinecap="round" strokeLinejoin="round" className="w-4 h-4 text-cv-amber-50 shrink-0" aria-hidden="true">
            <path d="M9 3H15" /><path d="M9 3V9L4 18H20L15 9V3" /><path d="M7.5 14H16.5" />
          </svg>
          <h3 className="text-sm font-semibold text-cv-amber-50">{STRINGS.runStatusPoller.experimentSectionHeading}</h3>
        </div>

        <div className="px-5 py-4 space-y-4">
          {/* Current experiment tracker (slim — no attempt history or CTAs) */}
          <p className="text-2xs font-semibold uppercase tracking-[0.14em] text-cv-amber-800">{STRINGS.runStatusPoller.currentExperiment}</p>
          {activeExpData?.experiment ? (
            <ExperimentTracker
              experiment={activeExpData.experiment}
              events={activeExpData.recent_events}
              onComplete={() => router.push('/client/experiment?action=completed')}
              onPark={(expId) => router.push(`/client/experiment?action=parked${expId ? `&parked_id=${expId}` : ''}`)}
              slim
            />
          ) : (
            // Fallback while data is loading or if fetch failed
            <div className="bg-white rounded border border-cv-warm-300 p-5 space-y-3">
              <p className="text-2xs font-semibold uppercase tracking-[0.14em] text-cv-amber-800">
                {STRINGS.runStatusPoller.yourExperiment}
              </p>
              <div className="flex gap-3 flex-wrap">
                <Link
                  href="/client/experiment"
                  className="px-5 py-2.5 bg-cv-teal-600 text-cv-teal-50 rounded text-sm font-medium hover:bg-cv-teal-800 transition-colors"
                >
                  {STRINGS.runStatusPoller.viewOnMyExperiment}
                </Link>
              </div>
            </div>
          )}

          {/* "In this meeting" heading + detection banner (only when run had active experiment at analysis time) */}
          {hasActiveExpFromRun && <>
          <p className="text-2xs font-semibold uppercase tracking-[0.14em] text-cv-amber-800">{STRINGS.runStatusPoller.inThisMeeting}</p>
          <div className="rounded border border-cv-stone-400 overflow-hidden">
            <div className={`flex items-center gap-2.5 px-5 py-3.5 border-b border-cv-warm-300 ${attemptConfig.bgColor}`}>
            {attemptConfig.icon}
            <h3 className={`text-sm font-semibold ${attemptConfig.labelColor}`}>
              {attemptConfig.label}
            </h3>
          </div>

          <div className="px-5 py-4 space-y-2">
            {/* Status blurb — always visible */}
            {attempt !== 'no' && (
              <p className="text-sm text-cv-stone-700 leading-relaxed">{attemptConfig.desc}</p>
            )}

            {/* Toggle for evidence details */}
            {hasDetails && (
              <button
                type="button"
                onClick={() => setDetailOpen(!detailOpen)}
                className="flex items-center gap-1.5 text-xs text-cv-stone-400 hover:text-cv-stone-600 transition-colors pt-1"
              >
                <svg
                  viewBox="0 0 20 20"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth={2}
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  className={`w-3.5 h-3.5 transition-transform duration-200 ${detailOpen ? 'rotate-180' : ''}`}
                  aria-hidden="true"
                >
                  <path d="M5 8l5 5 5-5" />
                </svg>
                {detailOpen ? STRINGS.runStatusPoller.hideDetails : STRINGS.runStatusPoller.showDetails}
              </button>
            )}

            {/* Collapsible evidence details */}
            {detailOpen && (
              <>
                {/* Evidence quotes — full attempts: simple list with span separators */}
                {attempt === 'yes' && detectionQuotes.length > 0 && (
                  <div className="space-y-3 pt-2">
                    <div>
                      <p className="text-2xs font-medium text-cv-stone-400 uppercase tracking-widest mb-1.5">
                        {STRINGS.runStatusPoller.fromTranscript}
                      </p>
                      <EvidenceQuoteList quotes={detectionQuotes} targetSpeaker={targetSpeaker} />
                    </div>

                    {run?.experiment_coaching?.coaching_note && (
                      <div>
                        <p className="text-2xs font-medium text-cv-stone-400 uppercase tracking-widest mb-1.5">
                          {STRINGS.runStatusPoller.coachsNote}
                        </p>
                        <p className="text-sm text-cv-stone-700 leading-relaxed">
                          {run?.experiment_coaching?.coaching_note}
                        </p>
                      </div>
                    )}
                  </div>
                )}

                {/* Evidence quotes — partial attempts: split by rewrite_for_span_id */}
                {attempt === 'partial' && detectionQuotes.length > 0 && (() => {
                  const rewriteSpanId = run?.experiment_coaching?.rewrite_for_span_id;
                  const successQuotes = rewriteSpanId
                    ? detectionQuotes.filter(q => q.span_id !== rewriteSpanId)
                    : detectionQuotes;
                  const rewriteGroupQuotes = rewriteSpanId
                    ? detectionQuotes.filter(q => q.span_id === rewriteSpanId)
                    : [];

                  return (
                    <div className="space-y-3 pt-2">
                      {/* What you did well — quotes not linked to the rewrite */}
                      {successQuotes.length > 0 && (
                        <div>
                          <p className="text-2xs font-medium text-cv-stone-400 uppercase tracking-widest mb-1.5">
                            {STRINGS.runStatusPoller.whatYouDidWell}
                          </p>
                          <EvidenceQuoteList quotes={successQuotes} targetSpeaker={targetSpeaker} />
                        </div>
                      )}

                      {/* What worked and what was missing — coaching note */}
                      {run?.experiment_coaching?.coaching_note && (
                        <div>
                          <p className="text-2xs font-medium text-cv-stone-400 uppercase tracking-widest mb-1.5">
                            {STRINGS.runStatusPoller.whatWorkedMissing}
                          </p>
                          <p className="text-sm text-cv-stone-700 leading-relaxed">
                            {run?.experiment_coaching?.coaching_note}
                          </p>
                        </div>
                      )}

                      {/* For example, you said — the full rewrite evidence span */}
                      {rewriteGroupQuotes.length > 0 && (
                        <div>
                          <p className="text-2xs font-medium text-cv-stone-400 uppercase tracking-widest mb-1.5">
                            {STRINGS.common.forExampleYouSaid}
                          </p>
                          <EvidenceQuoteList quotes={rewriteGroupQuotes} targetSpeaker={targetSpeaker} />
                        </div>
                      )}

                      {/* Next time, try something like — suggested rewrite */}
                      {run?.experiment_coaching?.suggested_rewrite && (
                        <div>
                          <p className="text-2xs font-medium text-cv-stone-400 uppercase tracking-widest mb-1.5">
                            {STRINGS.common.nextTimeTry}
                          </p>
                          <blockquote className="border-l-[2px] border-cv-teal-700 pl-4 py-1 my-2 bg-cv-teal-50 rounded-r-md">
                            <p className="text-sm text-cv-stone-700 italic">
                              &ldquo;{run?.experiment_coaching?.suggested_rewrite}&rdquo;
                            </p>
                          </blockquote>
                        </div>
                      )}

                    </div>
                  );
                })()}
              </>
            )}

            {/* Missed detection prompt — always visible (requires user action) */}
            {attempt === 'no' && confirmState === 'idle' && (
              <div className="space-y-2">
                <p className="text-sm text-cv-stone-700 leading-relaxed">
                  {STRINGS.runStatusPoller.missedDetectionPrompt}
                </p>
                <div className="flex gap-2 pt-1">
                  <button
                    onClick={() => handleConfirm(true)}
                    className="px-4 py-2 bg-cv-teal-700 text-white rounded text-xs font-semibold hover:bg-cv-teal-800 transition-colors"
                  >
                    {STRINGS.runStatusPoller.yesITriedIt}
                  </button>
                  <button
                    onClick={() => handleConfirm(false)}
                    className="px-4 py-2 bg-white border border-cv-warm-300 text-cv-stone-700 rounded text-xs font-semibold hover:bg-cv-warm-50 transition-colors"
                  >
                    {STRINGS.runStatusPoller.notThisTime}
                  </button>
                </div>
              </div>
            )}

            {attempt === 'no' && confirmState === 'loading' && (
              <p className="text-xs text-cv-stone-400">{STRINGS.common.saving}</p>
            )}

            {attempt === 'no' && confirmState === 'done' && (
              <p className="text-sm text-cv-stone-700 leading-relaxed">
                {confirmedValue
                  ? STRINGS.runStatusPoller.confirmedYes
                  : STRINGS.runStatusPoller.confirmedNo}
              </p>
            )}

            <p className="text-xs text-cv-stone-400">
              Experiment {activeExp?.experiment_id as string}
            </p>
          </div>
          </div>
          </>}

          {/* Graduation / parking recommendation banner */}
          {graduationRec && graduationRec.recommendation === 'graduate' && (
            <div className="rounded border border-cv-teal-300 bg-cv-teal-50 overflow-hidden">
              <div className="flex items-center gap-2.5 px-5 py-3 border-b border-cv-teal-200 bg-cv-teal-50">
                <svg viewBox="0 0 37 32" fill="currentColor" className="w-4 h-4 shrink-0 text-cv-teal-700" aria-hidden="true">
                  <path d="M36.078,7.173L19.876,0.346c-0.865-0.365-1.858-0.365-2.728,0L0.922,7.183C0.362,7.42,0.009,7.944,0,8.554c-0.009,0.607,0.329,1.143,0.881,1.394L2.59,10.73C2.538,10.809,2.5,10.898,2.5,11v9c0,0.005,0.003,0.01,0.003,0.016c-1.172,0.207-2.066,1.226-2.066,2.456c0,1.111,0.733,2.043,1.736,2.368l-1.798,4.164c-0.271,0.629-0.206,1.326,0.18,1.912C1.002,31.595,1.787,32,2.656,32l0.289-0.014c0.813-0.066,1.539-0.481,1.941-1.111c0.344-0.537,0.418-1.182,0.203-1.767L3.541,24.89c1.086-0.272,1.896-1.248,1.896-2.418c0-1.188-0.833-2.18-1.945-2.433C3.493,20.025,3.5,20.014,3.5,20v-8.853l4,1.833V20h0.01c0.103,2.257,5.827,3.439,11.49,3.439S30.387,22.257,30.49,20h0.01v-7.551l5.607-2.507C36.664,9.694,37.006,9.16,37,8.549C36.993,7.938,36.641,7.41,36.078,7.173z M4.045,30.336c-0.235,0.368-0.677,0.613-1.186,0.654L2.656,31c-0.531,0-1.005-0.236-1.266-0.634c-0.2-0.304-0.234-0.647-0.097-0.966l1.533-3.552l1.323,3.604C4.259,29.746,4.221,30.061,4.045,30.336z M4.438,22.472c0,0.827-0.673,1.5-1.5,1.5s-1.5-0.673-1.5-1.5s0.673-1.5,1.5-1.5S4.438,21.645,4.438,22.472z M29.5,18.419c-1.898-1.305-6.219-1.98-10.5-1.98s-8.602,0.675-10.5,1.98v-7.278c0-1.097,3.185-2.641,10.266-2.641c7.004,0,10.734,1.57,10.734,2.703V18.419z M19,22.439c-6.409,0-10.5-1.48-10.5-2.5s4.091-2.5,10.5-2.5s10.5,1.48,10.5,2.5S25.409,22.439,19,22.439z M35.699,9.03L30.5,11.354v-0.151c0-2.181-4.825-3.703-11.734-3.703C11.922,7.5,7.5,8.929,7.5,11.141v0.741L1.297,9.038C1.017,8.911,0.999,8.646,1,8.567s0.027-0.343,0.311-0.463l16.227-6.837c0.619-0.263,1.331-0.261,1.95,0l16.202,6.827c0.285,0.12,0.31,0.386,0.311,0.464C36.001,8.638,35.981,8.903,35.699,9.03z"/>
                </svg>
                <h4 className="text-sm font-semibold text-cv-teal-800">{STRINGS.runStatusPoller.graduationRecommendationTitle}</h4>
              </div>
              <div className="px-5 py-3.5 space-y-2">
                <p className="text-sm text-cv-stone-700 leading-relaxed">{graduationRec.rationale}</p>
              </div>
            </div>
          )}
          {graduationRec && graduationRec.recommendation === 'park' && (
            <div className="rounded border border-cv-amber-200 bg-cv-amber-50 overflow-hidden">
              <div className="flex items-center gap-2.5 px-5 py-3 border-b border-cv-amber-200 bg-cv-amber-100">
                <svg viewBox="0 0 16 16" fill="none" className="w-4 h-4 shrink-0 text-cv-amber-700" aria-hidden="true">
                  <rect x="3.5" y="2.5" width="3" height="11" rx="1" fill="currentColor"/><rect x="9.5" y="2.5" width="3" height="11" rx="1" fill="currentColor"/>
                </svg>
                <h4 className="text-sm font-semibold text-cv-amber-800">{STRINGS.runStatusPoller.parkRecommendationTitle}</h4>
              </div>
              <div className="px-5 py-3.5 space-y-2">
                <p className="text-sm text-cv-stone-700 leading-relaxed">{graduationRec.rationale}</p>
              </div>
            </div>
          )}

          {/* Attempt history (pulled from ExperimentTracker) */}
          {activeExpData?.experiment && (() => {
            const events = activeExpData.recent_events as { event_id?: string; id?: string; attempt?: string; meeting_date?: string; created_at?: string; human_confirmed?: string }[];
            const sortedEvents = [...events]
              .sort((a, b) => {
                const da = a.meeting_date || a.created_at || '';
                const db = b.meeting_date || b.created_at || '';
                return db.localeCompare(da);
              })
              .slice(0, 10);
            const successCount = sortedEvents.filter((e) => e.attempt === 'yes').length;
            const partialCount = sortedEvents.filter((e) => e.attempt === 'partial').length;
            const totalAttempted = successCount + partialCount;
            const summaryText = sortedEvents.length === 0
              ? STRINGS.experimentTracker.analyzeToStart
              : totalAttempted === 0
                ? STRINGS.experimentTracker.noAttemptsYet(sortedEvents.length)
                : STRINGS.experimentTracker.attemptsDetected(totalAttempted, sortedEvents.length);

            const ATTEMPT_STYLES: Record<string, { color: string; dot: string; bg: string; label: string; dateColor?: string }> = {
              yes:     { color: 'text-cv-teal-700',  dot: 'bg-cv-teal-500',  bg: 'bg-cv-teal-50',  label: STRINGS.attemptLabels.yes     },
              partial: { color: 'text-cv-amber-800', dot: 'bg-cv-amber-600', bg: 'bg-cv-amber-50', label: STRINGS.attemptLabels.partial, dateColor: 'text-cv-amber-800' },
              no:      { color: 'text-cv-stone-500', dot: 'bg-cv-stone-300', bg: 'bg-cv-warm-100', label: STRINGS.attemptLabels.no      },
            };

            const HUMAN_STYLES: Record<string, { label: string; color: string; border: string }> = {
              confirmed_attempt:    { label: STRINGS.humanConfirmation.confirmed_attempt,    color: 'text-cv-teal-700',  border: 'border-cv-teal-300'  },
              confirmed_no_attempt: { label: STRINGS.humanConfirmation.confirmed_no_attempt, color: 'text-cv-stone-500', border: 'border-cv-stone-300' },
            };

            return (
              <AttemptHistorySection
                sortedEvents={sortedEvents}
                summaryText={summaryText}
                attemptStyles={ATTEMPT_STYLES}
                humanStyles={HUMAN_STYLES}
              />
            );
          })()}

          {/* CTA buttons (pulled from ExperimentTracker) */}
          {activeExpData?.experiment && activeExpData.experiment.status === 'active' && (
            <div className="flex gap-2 flex-wrap pt-1">
              <Link
                href="/client/analyze"
                className="flex-1 flex items-center justify-center gap-2 px-4 py-2.5 bg-cv-navy-600 text-white rounded text-sm font-medium hover:bg-cv-navy-700 transition-colors"
              >
                <svg viewBox="0 0 24 24" fill="none" className="w-4 h-4 shrink-0" aria-hidden="true"><path d="M9 3L10.5 7.5L15 9L10.5 10.5L9 15L7.5 10.5L3 9L7.5 7.5L9 3Z" stroke="currentColor" strokeWidth={1.7} strokeLinecap="round" strokeLinejoin="round"/><path d="M19 13L19.75 15.25L22 16L19.75 16.75L19 19L18.25 16.75L16 16L18.25 15.25L19 13Z" stroke="currentColor" strokeWidth={1.7} strokeLinecap="round" strokeLinejoin="round"/></svg>
                {STRINGS.experimentTracker.analyzeMeeting}
              </Link>
              <button
                onClick={handleComplete}
                disabled={completeState === 'loading'}
                className="flex-1 py-2.5 bg-cv-teal-600 text-white rounded text-sm font-medium hover:bg-cv-teal-700 disabled:opacity-50 transition-colors"
              >
                {completeState === 'loading' ? STRINGS.common.saving : STRINGS.experimentTracker.markComplete}
              </button>
              <button
                onClick={() => {
                  const expId = (activeExp as Record<string, unknown>).experiment_record_id as string | undefined;
                  if (expId) {
                    api.parkExperiment(expId).then(() => {
                      router.push(`/client/experiment?action=parked${expId ? `&parked_id=${expId}` : ''}`);
                    });
                  }
                }}
                className="flex-1 flex items-center justify-center gap-2 px-4 py-2.5 bg-cv-warm-100 border border-cv-stone-400 text-cv-stone-600 rounded text-sm font-medium hover:bg-cv-warm-200 transition-colors"
              >
                <svg viewBox="0 0 16 16" fill="none" className="w-4 h-4 shrink-0" aria-hidden="true"><rect x="3.5" y="2.5" width="3" height="11" rx="1" fill="currentColor"/><rect x="9.5" y="2.5" width="3" height="11" rx="1" fill="currentColor"/></svg>
                {STRINGS.experimentTracker.parkForNow}
              </button>
            </div>
          )}
        </div>
      </section>
    );
  }

  // Build strength/growth-area pattern IDs for highlight badges
  const patternScores: Record<string, number> = {};
  for (const ps of run.pattern_snapshot ?? []) {
    if (ps.score != null) patternScores[ps.pattern_id] = ps.score;
  }
  const strengthThemePatternIds = run.coaching_themes
    .filter((t) => t.nature === 'strength')
    .flatMap((t) => t.related_patterns)
    .filter((pid) => (patternScores[pid] ?? 0) >= 0.70);
  const growthAreaPatternIds = run.coaching_themes
    .filter((t) => t.nature === 'developmental' || t.nature === 'mixed')
    .flatMap((t) => t.related_patterns)
    .filter((pid) => run.pattern_coaching.some((pc) => pc.pattern_id === pid && pc.suggested_rewrite));

  // Helper: find quote(s) by span_id across all pattern snapshot items
  const allQuotes = (run.pattern_snapshot ?? []).flatMap((p) => p.quotes ?? []);
  function findQuotesBySpanId(spanId: string | null | undefined) {
    if (!spanId) return [];
    return allQuotes.filter((q) => q.span_id === spanId);
  }

  // Split coaching themes by nature
  const strengthThemes = run.coaching_themes.filter((t) => t.nature === 'strength');
  const developmentalThemes = run.coaching_themes.filter(
    (t) => t.nature === 'developmental' || t.nature === 'mixed'
  );

  return (
    <div className="space-y-6">
      {/* Quality check failed banner (success banner removed) */}
      {run.gate1_pass === false && (
        <div className="bg-cv-amber-50 border border-cv-amber-200 rounded px-5 py-4 flex items-start gap-3">
          <svg viewBox="0 0 16 16" fill="none" className="w-5 h-5 shrink-0 text-cv-amber-600 mt-0.5" aria-hidden="true"><path d="M8 1L1 14h14L8 1z" stroke="currentColor" strokeWidth={1.4} strokeLinejoin="round"/><path d="M8 6v4" stroke="currentColor" strokeWidth={1.4} strokeLinecap="round"/><circle cx="8" cy="12" r="0.5" fill="currentColor"/></svg>
          <div>
            <p className="text-sm font-semibold text-cv-amber-800">{STRINGS.runStatusPoller.qualityCheckFailed}</p>
            <p className="text-sm text-cv-amber-600 font-light mt-0.5">{STRINGS.runStatusPoller.qualityCheckDesc}</p>
          </div>
        </div>
      )}

      {/* Executive summary */}
      {run.executive_summary && (
        <section className="bg-white rounded border border-cv-navy-600 overflow-hidden">
          <div className="flex items-center gap-2.5 px-5 py-3.5 border-b border-cv-warm-300 bg-cv-navy-600">
            <svg viewBox="0 0 20 20" fill="currentColor" className="w-4 h-4 text-cv-blue-50 shrink-0" aria-hidden="true">
              <path fillRule="evenodd" d="M4.5 2A1.5 1.5 0 003 3.5v13A1.5 1.5 0 004.5 18h11a1.5 1.5 0 001.5-1.5V7.621a1.5 1.5 0 00-.44-1.06l-4.12-4.122A1.5 1.5 0 0011.378 2H4.5zm2.25 8.5a.75.75 0 000 1.5h6.5a.75.75 0 000-1.5h-6.5zm0 3a.75.75 0 000 1.5h6.5a.75.75 0 000-1.5h-6.5z" clipRule="evenodd" />
            </svg>
            <h3 className="text-sm font-semibold text-cv-blue-50">{STRINGS.runStatusPoller.summaryHeading}</h3>
          </div>
          <div className="px-5 py-4">
            <p className="text-sm text-cv-stone-700 leading-relaxed">{run.executive_summary}</p>
          </div>
        </section>
      )}

      <CoachingCard
        focus={run.focus}
        targetSpeaker={targetSpeaker}
        microExperiment={
          hasActiveExp ||
          !expCheckDone ||
          proposedExperiments.length > 0 ||
          !!acceptedExpId ||
          !!run.baseline_pack_id
            ? null
            : run.micro_experiment
        }
        patternSnapshot={run.pattern_snapshot}
        patternCoaching={run.pattern_coaching}
        trendData={trendData}
      />

      {/* Strength themes — teal styling */}
      {strengthThemes.length > 0 && (
        <section className="bg-white rounded border border-cv-teal-700 overflow-hidden">
          <div className="flex items-center gap-2.5 px-5 py-3.5 border-b border-cv-warm-300 bg-cv-teal-700">
            <svg viewBox="0 0 24 24" fill="currentColor" className="w-4 h-4 text-cv-teal-50 shrink-0" aria-hidden="true">
              <path d="M22,3H19V2a1,1,0,0,0-1-1H6A1,1,0,0,0,5,2V3H2A1,1,0,0,0,1,4V6a4.994,4.994,0,0,0,4.276,4.927A7.009,7.009,0,0,0,11,15.92V18H7a1,1,0,0,0-.949.684l-1,3A1,1,0,0,0,6,23H18a1,1,0,0,0,.948-1.316l-1-3A1,1,0,0,0,17,18H13V15.92a7.009,7.009,0,0,0,5.724-4.993A4.994,4.994,0,0,0,23,6V4A1,1,0,0,0,22,3ZM5,8.829A3.006,3.006,0,0,1,3,6V5H5ZM16.279,20l.333,1H7.387l.334-1ZM17,9A5,5,0,0,1,7,9V3H17Zm4-3a3.006,3.006,0,0,1-2,2.829V5h2ZM10.667,8.667,9,7.292,11,7l1-2,1,2,2,.292L13.333,8.667,13.854,11,12,9.667,10.146,11Z"/>
            </svg>
            <h3 className="text-sm font-semibold text-cv-teal-50">{STRINGS.coachingCard.strengthsHeading}</h3>
          </div>
          <div className="divide-y divide-cv-warm-300">
            {strengthThemes.map((theme, idx) => (
              <StrengthThemeCard key={idx} theme={theme} targetSpeaker={targetSpeaker} />
            ))}
          </div>
        </section>
      )}

      {/* Developmental/mixed themes — rose styling */}
      {developmentalThemes.length > 0 && (
        <section className="bg-white rounded border border-cv-rose-700 overflow-hidden">
          <div className="flex items-center gap-2.5 px-5 py-3.5 border-b border-cv-warm-300 bg-cv-rose-700">
            <svg viewBox="0 0 20 20" fill="currentColor" className="w-4 h-4 text-cv-rose-50 shrink-0" aria-hidden="true">
              <path d="M10 12.5a2.5 2.5 0 100-5 2.5 2.5 0 000 5z" />
              <path fillRule="evenodd" d="M.664 10.59a1.651 1.651 0 010-1.186A10.004 10.004 0 0110 3c4.257 0 7.893 2.66 9.336 6.41.147.381.146.804 0 1.186A10.004 10.004 0 0110 17c-4.257 0-7.893-2.66-9.336-6.41zM14 10a4 4 0 11-8 0 4 4 0 018 0z" clipRule="evenodd" />
            </svg>
            <h3 className="text-sm font-semibold text-cv-rose-50">{STRINGS.coachingCard.coachingThemesHeading}</h3>
          </div>
          <div className="divide-y divide-cv-warm-300">
            {developmentalThemes.map((theme, idx) => (
              <DevelopmentalThemeCard key={idx} theme={theme} showPriorityBadge={developmentalThemes.length >= 2} targetSpeaker={targetSpeaker} />
            ))}
          </div>
        </section>
      )}

      <ProposedExperimentSection />

      <ExperimentSection />

      {run.pattern_snapshot && run.pattern_snapshot.length > 0 && (
        <section className="bg-white rounded border border-cv-stone-700 overflow-hidden">
          <div className="flex items-center gap-2.5 px-5 py-3.5 border-b border-cv-warm-300 bg-cv-stone-700">
            <svg viewBox="0 0 20 20" fill="currentColor" className="w-4 h-4 text-cv-stone-50 shrink-0" aria-hidden="true">
              <rect x="2" y="2.35" width="1.8" height="1.8" />
              <rect x="7" y="2.35" width="11" height="1.8" />
              <rect x="2" y="6.85" width="1.8" height="1.8" />
              <rect x="7" y="6.85" width="11" height="1.8" />
              <rect x="2" y="11.35" width="1.8" height="1.8" />
              <rect x="7" y="11.35" width="11" height="1.8" />
              <rect x="2" y="15.85" width="1.8" height="1.8" />
              <rect x="7" y="15.85" width="11" height="1.8" />
            </svg>
            <h3 className="text-sm font-semibold text-cv-stone-50">{STRINGS.runStatusPoller.patternSnapshot}</h3>
          </div>
          <div className="px-5 py-4">
            <PatternSnapshot
              patterns={run.pattern_snapshot}
              patternCoaching={run.pattern_coaching}
              targetSpeaker={targetSpeaker}
              trendData={trendData}
              groupByCluster
              strengthPatternIds={strengthThemePatternIds}
              growthAreaPatternIds={growthAreaPatternIds}
            />
          </div>
        </section>
      )}
    </div>
  );
}

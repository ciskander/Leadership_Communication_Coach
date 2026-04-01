'use client';

import { useState, useEffect, Suspense } from 'react';
import { useSearchParams } from 'next/navigation';
import Link from 'next/link';
import { api } from '@/lib/api';
import { useActiveExperiment } from '@/hooks/useActiveExperiment';
import { useProposedPoller } from '@/hooks/useProposedPoller';
import { ExperimentTracker } from '@/components/ExperimentTracker';
import type { Experiment, ExperimentOptions, RankedExperimentItem } from '@/lib/types';
import { STRINGS } from '@/config/strings';
import { OnboardingTip } from '@/components/OnboardingTip';

// ─── Helpers ──────────────────────────────────────────────────────────────────

function RelatedPatternsLabel({ relatedPatterns, patternId }: { relatedPatterns?: string[]; patternId?: string }) {
  const pids = relatedPatterns?.length ? relatedPatterns : patternId ? [patternId] : [];
  if (pids.length === 0) return null;
  return (
    <span className="text-2xs font-semibold uppercase tracking-[0.14em] text-cv-teal-600">
      {pids.map(pid => STRINGS.patternLabels[pid] ?? pid.replace(/_/g, ' ')).join(', ')}
    </span>
  );
}

function timeAgo(dateStr: string | null): string {
  if (!dateStr) return '';
  const diff  = Date.now() - new Date(dateStr).getTime();
  const days  = Math.floor(diff / 86_400_000);
  if (days < 1)   return 'today';
  if (days === 1) return '1 day ago';
  if (days < 7)   return `${days} days ago`;
  const weeks = Math.floor(days / 7);
  if (weeks === 1) return '1 week ago';
  if (weeks < 5)   return `${weeks} weeks ago`;
  const months = Math.floor(days / 30);
  if (months === 1) return '1 month ago';
  return `${months} months ago`;
}

/** Shared inset box used in proposed + parked cards */
function InsetBox({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="bg-cv-warm-50 border border-cv-warm-300 rounded p-3">
      <p className="text-2xs font-semibold uppercase tracking-[0.14em] text-cv-stone-400 mb-1">
        {label}
      </p>
      {children}
    </div>
  );
}

/** Inline spinner */
function Spinner() {
  return (
    <span className="w-3.5 h-3.5 border-2 border-current border-t-transparent rounded-full animate-spin inline-block" />
  );
}

// ─── Proposed experiment card ─────────────────────────────────────────────────

function ProposedExperimentCard({
  experiment,
  onAccepted,
  compact = false,
}: {
  experiment: Experiment;
  onAccepted: () => void;
  compact?: boolean;
}) {
  const [state, setState]     = useState<'idle' | 'loading' | 'error'>('idle');
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  async function handleAccept() {
    if (state !== 'idle') return;
    setState('loading');
    setErrorMsg(null);
    try {
      await api.acceptExperiment(experiment.experiment_record_id);
      onAccepted();
    } catch (err: unknown) {
      setErrorMsg(err instanceof Error ? err.message : 'Something went wrong.');
      setState('error');
    }
  }

  return (
    <div className="bg-white rounded border border-cv-stone-400 p-5 space-y-3">
      <div className="space-y-1">
        <RelatedPatternsLabel relatedPatterns={experiment.related_patterns} patternId={experiment.pattern_id} />
        <p className="text-sm font-semibold text-cv-stone-900 leading-snug font-serif">
          {experiment.title}
        </p>
      </div>

      {!compact && (
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
          <InsetBox label={STRINGS.common.whatToDo}>
            <p className="text-xs text-cv-stone-600 leading-relaxed">{experiment.instruction}</p>
          </InsetBox>
          <InsetBox label={STRINGS.common.successLooksLike}>
            <p className="text-xs text-cv-stone-600 leading-relaxed">{experiment.success_marker}</p>
          </InsetBox>
        </div>
      )}

      {errorMsg && <p className="text-xs text-cv-red-600">{errorMsg}</p>}

      <div className="flex items-center gap-3">
        <button
          onClick={handleAccept}
          disabled={state === 'loading'}
          className="flex items-center gap-2 px-4 py-2 bg-cv-teal-600 text-white rounded text-xs font-semibold hover:bg-cv-teal-700 transition-colors disabled:opacity-60"
        >
          {state === 'loading' && <Spinner />}
          {state === 'loading' ? STRINGS.common.accepting : STRINGS.common.acceptExperiment}
        </button>
        <span className="text-2xs text-cv-stone-400 ml-auto tabular-nums">{experiment.experiment_id}</span>
      </div>
    </div>
  );
}

// ─── Parked experiment card ───────────────────────────────────────────────────

function ParkedExperimentCard({
  experiment,
  onResumed,
  onDiscarded,
}: {
  experiment: Experiment;
  onResumed: () => void;
  onDiscarded: () => void;
}) {
  const [state, setState]       = useState<'idle' | 'loading' | 'confirm-discard'>('idle');
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  async function handleResume() {
    if (state === 'loading') return;
    setState('loading');
    setErrorMsg(null);
    try {
      await api.resumeExperiment(experiment.experiment_record_id);
      onResumed();
    } catch (err: unknown) {
      setErrorMsg(err instanceof Error ? err.message : 'Something went wrong.');
      setState('idle');
    }
  }

  async function handleDiscard() {
    setState('loading');
    setErrorMsg(null);
    try {
      await api.discardExperiment(experiment.experiment_record_id);
      onDiscarded();
    } catch (err: unknown) {
      setErrorMsg(err instanceof Error ? err.message : 'Something went wrong.');
      setState('idle');
    }
  }

  return (
    <div className="bg-white rounded border border-cv-amber-200 p-5 space-y-3">
      <div className="flex items-start justify-between gap-3">
        <div className="space-y-1 min-w-0">
          <div className="flex items-center gap-2">
            <span className="text-2xs font-semibold px-2 py-0.5 rounded-full bg-cv-amber-100 text-cv-amber-700 border border-cv-amber-700">
              {STRINGS.experimentPage.parked}
            </span>
            {experiment.ended_at && (
              <span className="text-2xs text-cv-stone-400">{timeAgo(experiment.ended_at)}</span>
            )}
          </div>
          <RelatedPatternsLabel relatedPatterns={experiment.related_patterns} patternId={experiment.pattern_id} />
          <p className="text-sm font-semibold text-cv-stone-900 leading-snug font-serif">
            {experiment.title}
          </p>
        </div>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
        <InsetBox label={STRINGS.common.whatToDo}>
          <p className="text-xs text-cv-stone-600 leading-relaxed">{experiment.instruction}</p>
        </InsetBox>
        <InsetBox label={STRINGS.common.successLooksLike}>
          <p className="text-xs text-cv-stone-600 leading-relaxed">{experiment.success_marker}</p>
        </InsetBox>
      </div>

      {errorMsg && <p className="text-xs text-cv-red-600">{errorMsg}</p>}

      {state === 'confirm-discard' ? (
        <div className="bg-cv-red-50 border border-cv-red-200 rounded p-3 space-y-2">
          <p className="text-xs text-cv-red-700">{STRINGS.experimentPage.discardConfirm}</p>
          <div className="flex gap-2">
            <button
              onClick={handleDiscard}
              className="px-3 py-1.5 bg-cv-red-600 text-white rounded text-xs font-semibold hover:bg-cv-red-700 transition-colors"
            >
              {STRINGS.experimentPage.discard}
            </button>
            <button
              onClick={() => setState('idle')}
              className="px-3 py-1.5 bg-white border border-cv-warm-300 text-cv-stone-600 rounded text-xs font-semibold hover:bg-cv-warm-50 transition-colors"
            >
              {STRINGS.common.cancel}
            </button>
          </div>
        </div>
      ) : (
        <div className="flex items-center gap-3">
          <button
            onClick={handleResume}
            disabled={state === 'loading'}
            className="flex items-center gap-2 px-4 py-2 bg-cv-amber-600 text-white rounded text-xs font-semibold hover:bg-cv-amber-700 transition-colors disabled:opacity-60"
          >
            {state === 'loading' && <Spinner />}
            {state === 'loading' ? STRINGS.experimentPage.resuming : STRINGS.experimentPage.resumeExperiment}
          </button>
          <button
            onClick={() => setState('confirm-discard')}
            disabled={state === 'loading'}
            className="text-xs text-cv-stone-400 hover:text-cv-red-600 transition-colors"
          >
            {STRINGS.experimentPage.discard}
          </button>
          <span className="text-2xs text-cv-stone-400 ml-auto tabular-nums">{experiment.experiment_id}</span>
        </div>
      )}
    </div>
  );
}

// ─── Section heading ──────────────────────────────────────────────────────────

function SectionHeading({ text }: { text: string }) {
  return (
    <h2 className="text-2xs font-semibold uppercase tracking-[0.14em] text-cv-stone-400 mb-3">
      {text}
    </h2>
  );
}

// ─── Main page (inner) ────────────────────────────────────────────────────────

function ExperimentPageInner() {
  const { data, loading, error, refetch } = useActiveExperiment();
  const { proposed, pollState, startPolling, reset: resetPoller } = useProposedPoller();

  const [options, setOptions]             = useState<ExperimentOptions | null>(null);
  const [seedLoading, setSeedLoading]     = useState(true);
  const [lastAction, setLastAction]       = useState<'completed' | 'parked' | null>(null);
  const [justParkedId, setJustParkedId]   = useState<string | null>(null);
  const searchParams                      = useSearchParams();
  const [showMore, setShowMore]           = useState(searchParams.get('expand') === '1');
  const [backfillRetries, setBackfillRetries] = useState(0);
  const MAX_BACKFILL_RETRIES = 8;

  function fetchOptions(parkedId?: string) {
    const id = parkedId ?? justParkedId ?? undefined;
    api.getExperimentOptions(id)
      .then(setOptions)
      .catch(() => setOptions(null))
      .finally(() => setSeedLoading(false));
  }

  useEffect(() => {
    // When arriving from RunStatusPoller after completing/parking an experiment,
    // the ?action= param signals that we should immediately start polling for
    // the next proposed experiment (the Celery task is already in-flight).
    const inboundAction = searchParams.get('action');
    const inboundParkedId = searchParams.get('parked_id');
    if (inboundParkedId) setJustParkedId(inboundParkedId);

    fetchOptions(inboundParkedId ?? undefined);

    if (inboundAction === 'completed' || inboundAction === 'parked') {
      setLastAction(inboundAction);
      setBackfillRetries(0);
      resetPoller();
      startPolling();
    }
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const experiment = data?.experiment;
  const events     = data?.recent_events ?? [];
  const hasActive  = !!experiment && experiment.status === 'active';

  // When the page loads (or refreshes) with no active experiment and no options
  // yet, automatically start polling for proposed experiments.
  useEffect(() => {
    if (!loading && !hasActive && pollState === 'idle') {
      startPolling();
    }
  }, [loading, hasActive]); // eslint-disable-line react-hooks/exhaustive-deps

  const isBackfilling = !!(
    options &&
    options.ranked.length < 3 &&
    backfillRetries < MAX_BACKFILL_RETRIES &&
    (options.ranked.length > 0 || lastAction !== null || !hasActive)
  );

  useEffect(() => {
    if (!isBackfilling) return;
    const t = setTimeout(() => {
      setBackfillRetries((r) => r + 1);
      fetchOptions();
    }, 5000);
    return () => clearTimeout(t);
  }, [isBackfilling, backfillRetries]);

  const rankedItems: RankedExperimentItem[] = (() => {
    const baseRanked = options?.ranked ?? [];
    if (proposed.length === 0) return baseRanked;
    const seen = new Set(baseRanked.map((r) => r.experiment.experiment_record_id));
    const extras: RankedExperimentItem[] = [];
    for (const exp of proposed) {
      if (!seen.has(exp.experiment_record_id)) {
        extras.push({ experiment: exp, origin: 'proposed', rank: baseRanked.length + extras.length + 1 });
      }
    }
    return [...baseRanked, ...extras].slice(0, 3);
  })();

  const parkedExperiments = options?.parked ?? [];
  const atParkCap         = options?.at_park_cap ?? false;
  const isPolling         = pollState === 'polling';

  function handleComplete() {
    setLastAction('completed'); setShowMore(false); setBackfillRetries(0);
    resetPoller(); refetch(false); startPolling(); fetchOptions();
  }
  function handlePark(parkedExperimentId?: string) {
    setLastAction('parked'); setShowMore(false); setBackfillRetries(0);
    if (parkedExperimentId) setJustParkedId(parkedExperimentId);
    resetPoller(); refetch(false); startPolling(); fetchOptions(parkedExperimentId);
  }
  function handleAccepted() {
    setLastAction(null); setJustParkedId(null); setShowMore(false); setBackfillRetries(0);
    resetPoller(); refetch(); fetchOptions();
  }
  function handleResumed() {
    setLastAction(null); setJustParkedId(null); setShowMore(false); resetPoller(); refetch(); fetchOptions();
  }
  function handleDiscarded() { fetchOptions(); }

  // ── Loading / error states ────────────────────────────────────────────────
  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <span className="w-8 h-8 border-2 border-cv-teal-600 border-t-transparent rounded-full animate-spin" />
      </div>
    );
  }

  if (error) {
    return (
      <p className="text-sm text-cv-red-600 bg-cv-red-50 border border-cv-red-200 rounded px-4 py-3">
        {error}
      </p>
    );
  }

  // ── Post-action banner ────────────────────────────────────────────────────
  function PostActionBanner() {
    if (!lastAction) return null;
    if (lastAction === 'completed') {
      return (
        <div className="bg-cv-teal-50 border border-cv-teal-200 rounded px-5 py-4 flex items-center gap-3">
          <svg viewBox="0 0 20 20" fill="currentColor" className="w-5 h-5 text-cv-teal-600 shrink-0" aria-hidden="true">
            <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.857-9.809a.75.75 0 00-1.214-.882l-3.483 4.79-1.88-1.88a.75.75 0 10-1.06 1.061l2.5 2.5a.75.75 0 001.137-.089l4-5.5z" clipRule="evenodd" />
          </svg>
          <div>
            <p className="text-sm font-semibold text-cv-teal-800">{STRINGS.experimentPage.completeBanner}</p>
            <p className="text-xs text-cv-teal-700 mt-0.5">{STRINGS.experimentPage.completeSubtext}</p>
          </div>
        </div>
      );
    }
    return (
      <div className="bg-cv-amber-50 border border-cv-amber-200 rounded px-5 py-4 flex items-center gap-3">
        <svg viewBox="0 0 20 20" fill="currentColor" className="w-5 h-5 text-cv-amber-600 shrink-0" aria-hidden="true">
          <path fillRule="evenodd" d="M2 10a8 8 0 1116 0 8 8 0 01-16 0zm5-2.25A.75.75 0 017.75 7h.5a.75.75 0 01.75.75v4.5a.75.75 0 01-.75.75h-.5A.75.75 0 017 12.25v-4.5zm4.25-.75a.75.75 0 00-.75.75v4.5c0 .414.336.75.75.75h.5a.75.75 0 00.75-.75v-4.5a.75.75 0 00-.75-.75h-.5z" clipRule="evenodd" />
        </svg>
        <div>
          <p className="text-sm font-semibold text-cv-amber-800">{STRINGS.experimentPage.parkedBanner}</p>
          <p className="text-xs text-cv-amber-700 mt-0.5">{STRINGS.experimentPage.parkedSubtext}</p>
        </div>
      </div>
    );
  }

  const overallLoading = seedLoading && !lastAction;
  const showCapScreen  = atParkCap && !hasActive;
  const hasOptions     = rankedItems.length > 0;

  return (
    <div className="max-w-4xl mx-auto space-y-5 py-2">
      <OnboardingTip tipId="experiment" message={STRINGS.onboarding.tipExperiment} />

      {/* Page heading */}
      <div>
        <h1 className="font-serif text-2xl text-cv-stone-900">
          {STRINGS.experimentPage.heading}
        </h1>
        <p className="text-sm text-cv-stone-500 mt-1">{STRINGS.experimentPage.subtitle}</p>
      </div>

      {hasActive ? (
        <ExperimentTracker
          experiment={experiment}
          events={events as Record<string, unknown>[]}
          onComplete={handleComplete}
          onPark={handlePark}
        />
      ) : (
        <>
          <PostActionBanner />

          {/* Polling indicator */}
          {isPolling && (
            <div className="flex items-center gap-3 px-5 py-3 bg-cv-teal-50 border border-cv-teal-100 rounded">
              <span className="w-4 h-4 border-2 border-cv-teal-500 border-t-transparent rounded-full animate-spin shrink-0" />
              <p className="text-sm text-cv-teal-700">{STRINGS.experimentPage.findingExperiment}</p>
            </div>
          )}

          {/* Park-cap screen */}
          {showCapScreen && parkedExperiments.length > 0 && (
            <section>
              <div className="bg-cv-amber-50 border border-cv-amber-200 rounded px-5 py-4 mb-4">
                <p className="text-sm font-semibold text-cv-amber-800">
                  {STRINGS.experimentPage.parkCapMessage(parkedExperiments.length)}
                </p>
                <p className="text-xs text-cv-amber-700 mt-1">
                  {STRINGS.experimentPage.parkCapHint}
                </p>
              </div>
              <div className="space-y-3">
                {parkedExperiments.map((exp) => (
                  <ParkedExperimentCard
                    key={exp.experiment_record_id}
                    experiment={exp}
                    onResumed={handleResumed}
                    onDiscarded={handleDiscarded}
                  />
                ))}
              </div>
            </section>
          )}

          {/* Experiment options */}
          {!showCapScreen && !overallLoading && hasOptions && isBackfilling ? (
            <div className="flex items-center gap-3 px-5 py-4 bg-cv-teal-50 border border-cv-teal-100 rounded">
              <span className="w-4 h-4 border-2 border-cv-teal-500 border-t-transparent rounded-full animate-spin shrink-0" />
              <p className="text-sm text-cv-teal-700">{STRINGS.experimentPage.generatingOptions}</p>
            </div>
          ) : !showCapScreen && !overallLoading && hasOptions ? (
            <section>
              {!showMore ? (
                <>
                  <SectionHeading text={lastAction ? STRINGS.experimentPage.recommendedNext : STRINGS.experimentPage.suggestedExperiment} />
                  {rankedItems[0].origin === 'parked' ? (
                    <ParkedExperimentCard
                      experiment={rankedItems[0].experiment}
                      onResumed={handleResumed}
                      onDiscarded={handleDiscarded}
                    />
                  ) : (
                    <ProposedExperimentCard
                      experiment={rankedItems[0].experiment}
                      onAccepted={handleAccepted}
                    />
                  )}
                  {rankedItems.length > 1 && (
                    <button
                      onClick={() => setShowMore(true)}
                      className="mt-3 w-full py-2.5 bg-cv-warm-50 border border-cv-warm-300 text-cv-stone-600 rounded text-sm font-medium hover:bg-cv-warm-100 transition-colors"
                    >
                      {STRINGS.experimentPage.seeMoreOptions}
                    </button>
                  )}
                </>
              ) : (
                <>
                  <div className="flex items-center justify-between mb-3">
                    <SectionHeading text={STRINGS.experimentPage.chooseNext} />
                    <button
                      onClick={() => setShowMore(false)}
                      className="text-xs text-cv-stone-500 hover:text-cv-stone-700 transition-colors -mt-3"
                    >
                      {STRINGS.experimentPage.backToRecommendation}
                    </button>
                  </div>
                  <div className="space-y-3">
                    {rankedItems.map((item) => (
                      <div key={item.experiment.experiment_record_id}>
                        <p className={`text-xs font-medium mb-1.5 ${item.rank === 1 ? 'text-cv-teal-600' : 'text-cv-stone-400'}`}>
                          {STRINGS.experimentPage.rankLabel(item.rank)}
                          {item.origin === 'parked' && (
                            <span className="ml-2 text-2xs font-semibold px-2 py-0.5 rounded-full bg-cv-amber-100 text-cv-amber-700">
                              {STRINGS.experimentPage.parked}
                            </span>
                          )}
                        </p>
                        {item.origin === 'parked' ? (
                          <ParkedExperimentCard
                            experiment={item.experiment}
                            onResumed={handleResumed}
                            onDiscarded={handleDiscarded}
                          />
                        ) : (
                          <ProposedExperimentCard
                            experiment={item.experiment}
                            onAccepted={handleAccepted}
                          />
                        )}
                      </div>
                    ))}
                  </div>
                </>
              )}
            </section>
          ) : !showCapScreen && !overallLoading && !isPolling && !hasOptions ? (
            /* Empty state */
            <div className="bg-white rounded border border-dashed border-cv-warm-300 p-12 text-center space-y-4">
              {/* Beaker icon */}
              <div className="flex justify-center">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.5} strokeLinecap="round" strokeLinejoin="round" className="w-10 h-10 text-cv-stone-300" aria-hidden="true">
                  <path d="M9 3H15M9 3V9L4 18H20L15 9V3M9 3H15M7.5 14H16.5" />
                </svg>
              </div>
              <p className="text-cv-stone-600 font-semibold">{STRINGS.experimentPage.noActiveExperiment}</p>
              <p className="text-sm text-cv-stone-400 max-w-xs mx-auto leading-relaxed">
                {STRINGS.experimentPage.noActiveExperimentDesc}
              </p>
              <div className="flex gap-3 justify-center pt-2">
                <Link
                  href="/client/analyze"
                  className="flex items-center gap-2 px-5 py-2.5 bg-cv-navy-600 text-white rounded text-sm font-medium hover:bg-cv-navy-700 transition-colors"
                >
                  <span className="shrink-0"><svg viewBox="0 0 16 16" fill="none" className="w-4 h-4 shrink-0" aria-hidden="true"><path d="M8 1v3M8 12v3M1 8h3M12 8h3M3.05 3.05l2.12 2.12M10.83 10.83l2.12 2.12M3.05 12.95l2.12-2.12M10.83 5.17l2.12-2.12" stroke="currentColor" strokeWidth={1.4} strokeLinecap="round"/></svg></span>
                  {STRINGS.experimentTracker.analyzeMeeting}
                </Link>
                <Link
                  href="/client/baseline/new"
                  className="px-5 py-2.5 bg-white border border-cv-warm-300 text-cv-stone-700 rounded text-sm font-medium hover:bg-cv-warm-50 transition-colors"
                >
                  {STRINGS.clientDashboard.createBaseline}
                </Link>
              </div>
            </div>
          ) : null}
        </>
      )}
    </div>
  );
}

export default function ExperimentPage() {
  return (
    <Suspense>
      <ExperimentPageInner />
    </Suspense>
  );
}

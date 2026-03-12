'use client';

import { useState, useEffect } from 'react';
import { useSearchParams } from 'next/navigation';
import Link from 'next/link';
import { api } from '@/lib/api';
import { useActiveExperiment } from '@/hooks/useActiveExperiment';
import { useProposedPoller } from '@/hooks/useProposedPoller';
import { ExperimentTracker } from '@/components/ExperimentTracker';
import type { Experiment, ExperimentOptions, RankedExperimentItem } from '@/lib/types';
import { STRINGS } from '@/config/strings';
import { OnboardingTip } from '@/components/OnboardingTip';

function PatternLabel({ id }: { id: string }) {
  return (
    <span className="text-xs font-semibold text-stone-400 uppercase tracking-widest">
      {id.replace(/_/g, ' ')}
    </span>
  );
}

function timeAgo(dateStr: string | null): string {
  if (!dateStr) return '';
  const diff = Date.now() - new Date(dateStr).getTime();
  const days = Math.floor(diff / 86_400_000);
  if (days < 1) return 'today';
  if (days === 1) return '1 day ago';
  if (days < 7) return `${days} days ago`;
  const weeks = Math.floor(days / 7);
  if (weeks === 1) return '1 week ago';
  if (weeks < 5) return `${weeks} weeks ago`;
  const months = Math.floor(days / 30);
  if (months === 1) return '1 month ago';
  return `${months} months ago`;
}

// ── Proposed Experiment Card ──────────────────────────────────────────────────

function ProposedExperimentCard({
  experiment,
  onAccepted,
  compact = false,
}: {
  experiment: Experiment;
  onAccepted: () => void;
  compact?: boolean;
}) {
  const [state, setState] = useState<'idle' | 'loading' | 'error'>('idle');
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
    <div className="bg-white rounded-2xl border border-stone-200 p-5 space-y-3">
      <div className="space-y-1">
        <PatternLabel id={experiment.pattern_id} />
        <p className="text-sm font-semibold text-stone-900 leading-snug">{experiment.title}</p>
      </div>
      {!compact && (
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
          <div className="bg-stone-50 rounded-xl p-3">
            <p className="text-xs font-semibold text-stone-400 uppercase tracking-widest mb-1">{STRINGS.common.whatToDo}</p>
            <p className="text-xs text-stone-600 leading-relaxed">{experiment.instruction}</p>
          </div>
          <div className="bg-stone-50 rounded-xl p-3">
            <p className="text-xs font-semibold text-stone-400 uppercase tracking-widest mb-1">{STRINGS.common.successLooksLike}</p>
            <p className="text-xs text-stone-600 leading-relaxed">{experiment.success_marker}</p>
          </div>
        </div>
      )}
      {errorMsg && <p className="text-xs text-rose-600">{errorMsg}</p>}
      <div className="flex items-center gap-3">
        <button
          onClick={handleAccept}
          disabled={state === 'loading'}
          className="px-4 py-2 bg-emerald-600 text-white rounded-xl text-xs font-semibold hover:bg-emerald-700 transition-colors disabled:opacity-60"
        >
          {state === 'loading' ? STRINGS.common.accepting : STRINGS.common.acceptExperiment}
        </button>
        <span className="text-xs text-stone-400 ml-auto">{experiment.experiment_id}</span>
      </div>
    </div>
  );
}

// ── Parked Experiment Card ────────────────────────────────────────────────────

function ParkedExperimentCard({
  experiment,
  onResumed,
  onDiscarded,
}: {
  experiment: Experiment;
  onResumed: () => void;
  onDiscarded: () => void;
}) {
  const [state, setState] = useState<'idle' | 'loading' | 'confirm-discard'>('idle');
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
    <div className="bg-white rounded-2xl border border-amber-200 p-5 space-y-3">
      <div className="flex items-start justify-between gap-3">
        <div className="space-y-1 min-w-0">
          <div className="flex items-center gap-2">
            <span className="text-xs font-semibold px-2 py-0.5 rounded-full bg-amber-100 text-amber-700">
              {STRINGS.experimentPage.parked}
            </span>
            {experiment.ended_at && (
              <span className="text-xs text-stone-400">
                {timeAgo(experiment.ended_at)}
              </span>
            )}
          </div>
          <PatternLabel id={experiment.pattern_id} />
          <p className="text-sm font-semibold text-stone-900 leading-snug">{experiment.title}</p>
        </div>
      </div>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
        <div className="bg-stone-50 rounded-xl p-3">
          <p className="text-xs font-semibold text-stone-400 uppercase tracking-widest mb-1">{STRINGS.common.whatToDo}</p>
          <p className="text-xs text-stone-600 leading-relaxed">{experiment.instruction}</p>
        </div>
        <div className="bg-stone-50 rounded-xl p-3">
          <p className="text-xs font-semibold text-stone-400 uppercase tracking-widest mb-1">{STRINGS.common.successLooksLike}</p>
          <p className="text-xs text-stone-600 leading-relaxed">{experiment.success_marker}</p>
        </div>
      </div>
      {errorMsg && <p className="text-xs text-rose-600">{errorMsg}</p>}

      {state === 'confirm-discard' ? (
        <div className="bg-rose-50 border border-rose-200 rounded-xl p-3 space-y-2">
          <p className="text-xs text-rose-700">{STRINGS.experimentPage.discardConfirm}</p>
          <div className="flex gap-2">
            <button
              onClick={handleDiscard}
              className="px-3 py-1.5 bg-rose-600 text-white rounded-lg text-xs font-semibold hover:bg-rose-700 transition-colors"
            >
              {STRINGS.experimentPage.discard}
            </button>
            <button
              onClick={() => setState('idle')}
              className="px-3 py-1.5 bg-white border border-stone-300 text-stone-600 rounded-lg text-xs font-semibold hover:bg-stone-50 transition-colors"
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
            className="px-4 py-2 bg-amber-600 text-white rounded-xl text-xs font-semibold hover:bg-amber-700 transition-colors disabled:opacity-60"
          >
            {state === 'loading' ? STRINGS.experimentPage.resuming : STRINGS.experimentPage.resumeExperiment}
          </button>
          <button
            onClick={() => setState('confirm-discard')}
            disabled={state === 'loading'}
            className="text-xs text-stone-400 hover:text-rose-600 transition-colors"
          >
            {STRINGS.experimentPage.discard}
          </button>
          <span className="text-xs text-stone-400 ml-auto">{experiment.experiment_id}</span>
        </div>
      )}
    </div>
  );
}

// ── Main Page ─────────────────────────────────────────────────────────────────

export default function ExperimentPage() {
  const { data, loading, error, refetch } = useActiveExperiment();
  const { proposed, pollState, startPolling, reset: resetPoller } = useProposedPoller();

  // Seed proposed + parked + ranked lists from a one-shot fetch on mount
  const [options, setOptions] = useState<ExperimentOptions | null>(null);
  const [seedLoading, setSeedLoading] = useState(true);
  const [lastAction, setLastAction] = useState<'completed' | 'parked' | null>(null);
  const searchParams = useSearchParams();
  const [showMore, setShowMore] = useState(searchParams.get('expand') === '1');
  const [backfillRetries, setBackfillRetries] = useState(0);
  const MAX_BACKFILL_RETRIES = 8; // 40 seconds max

  function fetchOptions() {
    api.getExperimentOptions()
      .then(setOptions)
      .catch(() => setOptions(null))
      .finally(() => setSeedLoading(false));
  }

  useEffect(() => {
    fetchOptions();
  }, []);

  // Poll for backfill: when we have fewer than 3 ranked items and expect more
  // (either mid-backfill or just after a park/complete action), re-fetch until
  // we have 3 or hit the retry cap.
  const isBackfilling = !!(
    options &&
    options.ranked.length < 3 &&
    backfillRetries < MAX_BACKFILL_RETRIES &&
    // Either we have some options and need more, or we just completed/parked
    (options.ranked.length > 0 || lastAction !== null)
  );

  useEffect(() => {
    if (!isBackfilling) return;
    const t = setTimeout(() => {
      setBackfillRetries((r) => r + 1);
      fetchOptions();
    }, 5000);
    return () => clearTimeout(t);
  }, [isBackfilling, backfillRetries]);

  // Build the ranked list, incorporating any newly-polled proposed experiments
  const rankedItems: RankedExperimentItem[] = (() => {
    const baseRanked = options?.ranked ?? [];
    if (proposed.length === 0) return baseRanked;

    // Merge polled proposed into ranked, deduplicating by record ID
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
  const atParkCap = options?.at_park_cap ?? false;
  const isPolling = pollState === 'polling';

  function handleComplete() {
    setLastAction('completed');
    setShowMore(false);
    setBackfillRetries(0);
    resetPoller();
    refetch(false);
    startPolling();
    fetchOptions();
  }

  function handlePark() {
    setLastAction('parked');
    setShowMore(false);
    setBackfillRetries(0);
    resetPoller();
    refetch(false);
    startPolling();
    fetchOptions();
  }

  function handleAccepted() {
    setLastAction(null);
    setShowMore(false);
    setBackfillRetries(0);
    resetPoller();
    refetch();
    fetchOptions();
  }

  function handleResumed() {
    setLastAction(null);
    setShowMore(false);
    resetPoller();
    refetch();
    fetchOptions();
  }

  function handleDiscarded() {
    fetchOptions();
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-emerald-600" />
      </div>
    );
  }

  if (error) {
    return <p className="text-sm text-rose-600">{error}</p>;
  }

  const experiment = data?.experiment;
  const events = data?.recent_events ?? [];
  const hasActive = !!experiment && experiment.status === 'active';

  function PostActionBanner() {
    if (!lastAction) return null;
    if (lastAction === 'completed') {
      return (
        <div className="bg-emerald-50 border border-emerald-200 rounded-2xl px-5 py-4 flex items-center gap-3">
          <span className="text-xl">🎉</span>
          <div>
            <p className="text-sm font-semibold text-emerald-800">{STRINGS.experimentPage.completeBanner}</p>
            <p className="text-xs text-emerald-700 mt-0.5">{STRINGS.experimentPage.completeSubtext}</p>
          </div>
        </div>
      );
    }
    return (
      <div className="bg-amber-50 border border-amber-200 rounded-2xl px-5 py-4 flex items-center gap-3">
        <span className="text-xl">⏸</span>
        <div>
          <p className="text-sm font-semibold text-amber-800">{STRINGS.experimentPage.parkedBanner}</p>
          <p className="text-xs text-amber-700 mt-0.5">{STRINGS.experimentPage.parkedSubtext}</p>
        </div>
      </div>
    );
  }

  const overallLoading = seedLoading && !lastAction;

  // At park cap — only show parked experiments, no new proposals
  const showCapScreen = atParkCap && !hasActive;
  // Has options to show
  const hasOptions = rankedItems.length > 0;

  return (
    <div className="max-w-2xl mx-auto space-y-5 py-2">
      <OnboardingTip tipId="experiment" message={STRINGS.onboarding.tipExperiment} />
      <div>
        <h1 className="text-2xl font-bold text-stone-900">{STRINGS.experimentPage.heading}</h1>
        <p className="text-sm text-stone-500 mt-1">
          {STRINGS.experimentPage.subtitle}
        </p>
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
            <div className="flex items-center gap-3 px-5 py-3 bg-blue-50 rounded-2xl border border-blue-100">
              <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-blue-500 flex-shrink-0" />
              <p className="text-sm text-blue-700">{STRINGS.experimentPage.findingExperiment}</p>
            </div>
          )}

          {/* Park cap screen — user must resume or discard a parked experiment */}
          {showCapScreen && parkedExperiments.length > 0 && (
            <section>
              <div className="bg-amber-50 border border-amber-200 rounded-2xl px-5 py-4 mb-4">
                <p className="text-sm font-medium text-amber-800">
                  {STRINGS.experimentPage.parkCapMessage(parkedExperiments.length)}
                </p>
                <p className="text-xs text-amber-700 mt-1">
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

          {/* Experiment options — 1 top recommendation by default, all 3 ranked on "See more" */}
          {!showCapScreen && !overallLoading && hasOptions && isBackfilling ? (
            <div className="flex items-center gap-3 px-5 py-4 bg-blue-50 rounded-2xl border border-blue-100">
              <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-blue-500 flex-shrink-0" />
              <p className="text-sm text-blue-700">{STRINGS.experimentPage.generatingOptions}</p>
            </div>
          ) : !showCapScreen && !overallLoading && hasOptions ? (
            <section>
              {!showMore ? (
                <>
                  {/* Default: show only the top-ranked item */}
                  <h2 className="text-xs font-semibold text-stone-400 uppercase tracking-widest mb-3">
                    {lastAction ? STRINGS.experimentPage.recommendedNext : STRINGS.experimentPage.suggestedExperiment}
                  </h2>
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
                      className="mt-3 w-full py-2.5 bg-stone-50 border border-stone-200 text-stone-600 rounded-xl text-sm font-medium hover:bg-stone-100 transition-colors"
                    >
                      {STRINGS.experimentPage.seeMoreOptions}
                    </button>
                  )}
                </>
              ) : (
                <>
                  {/* Expanded: all ranked options (proposed + parked merged) */}
                  <div className="flex items-center justify-between mb-3">
                    <h2 className="text-xs font-semibold text-stone-400 uppercase tracking-widest">
                      {STRINGS.experimentPage.chooseNext}
                    </h2>
                    <button
                      onClick={() => setShowMore(false)}
                      className="text-xs text-stone-500 hover:text-stone-700 transition-colors"
                    >
                      {STRINGS.experimentPage.backToRecommendation}
                    </button>
                  </div>
                  <div className="space-y-3">
                    {rankedItems.map((item) => (
                      <div key={item.experiment.experiment_record_id}>
                        <p className={`text-xs font-medium mb-1.5 ${item.rank === 1 ? 'text-emerald-600' : 'text-stone-400'}`}>
                          {STRINGS.experimentPage.rankLabel(item.rank)}
                          {item.origin === 'parked' && (
                            <span className="ml-2 text-xs font-semibold px-2 py-0.5 rounded-full bg-amber-100 text-amber-700">
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
            <div className="bg-white rounded-2xl border border-dashed border-stone-300 p-12 text-center space-y-4">
              <div className="text-4xl">🧪</div>
              <p className="text-stone-600 font-medium">{STRINGS.experimentPage.noActiveExperiment}</p>
              <p className="text-sm text-stone-400 max-w-xs mx-auto leading-relaxed">
                {STRINGS.experimentPage.noActiveExperimentDesc}
              </p>
              <div className="flex gap-3 justify-center pt-2">
                <Link
                  href="/client/analyze"
                  className="px-5 py-2.5 bg-blue-600 text-white rounded-xl text-sm font-medium hover:bg-blue-700 transition-colors"
                >
                  {STRINGS.experimentTracker.analyzeMeeting}
                </Link>
                <Link
                  href="/client/baseline/new"
                  className="px-5 py-2.5 bg-white border border-stone-300 text-stone-700 rounded-xl text-sm font-medium hover:bg-stone-50 transition-colors"
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

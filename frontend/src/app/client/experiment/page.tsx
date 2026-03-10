'use client';

import { useState, useEffect } from 'react';
import Link from 'next/link';
import { api } from '@/lib/api';
import { useActiveExperiment } from '@/hooks/useActiveExperiment';
import { useProposedPoller } from '@/hooks/useProposedPoller';
import { ExperimentTracker } from '@/components/ExperimentTracker';
import type { Experiment, ExperimentOptions } from '@/lib/types';

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
            <p className="text-xs font-semibold text-stone-400 uppercase tracking-widest mb-1">What to do</p>
            <p className="text-xs text-stone-600 leading-relaxed">{experiment.instruction}</p>
          </div>
          <div className="bg-stone-50 rounded-xl p-3">
            <p className="text-xs font-semibold text-stone-400 uppercase tracking-widest mb-1">Success looks like</p>
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
          {state === 'loading' ? 'Accepting…' : 'Accept experiment'}
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
              Parked
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
          <p className="text-xs font-semibold text-stone-400 uppercase tracking-widest mb-1">What to do</p>
          <p className="text-xs text-stone-600 leading-relaxed">{experiment.instruction}</p>
        </div>
        <div className="bg-stone-50 rounded-xl p-3">
          <p className="text-xs font-semibold text-stone-400 uppercase tracking-widest mb-1">Success looks like</p>
          <p className="text-xs text-stone-600 leading-relaxed">{experiment.success_marker}</p>
        </div>
      </div>
      {errorMsg && <p className="text-xs text-rose-600">{errorMsg}</p>}

      {state === 'confirm-discard' ? (
        <div className="bg-rose-50 border border-rose-200 rounded-xl p-3 space-y-2">
          <p className="text-xs text-rose-700">Permanently discard this experiment? This cannot be undone.</p>
          <div className="flex gap-2">
            <button
              onClick={handleDiscard}
              className="px-3 py-1.5 bg-rose-600 text-white rounded-lg text-xs font-semibold hover:bg-rose-700 transition-colors"
            >
              Discard
            </button>
            <button
              onClick={() => setState('idle')}
              className="px-3 py-1.5 bg-white border border-stone-300 text-stone-600 rounded-lg text-xs font-semibold hover:bg-stone-50 transition-colors"
            >
              Cancel
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
            {state === 'loading' ? 'Resuming…' : 'Resume experiment'}
          </button>
          <button
            onClick={() => setState('confirm-discard')}
            disabled={state === 'loading'}
            className="text-xs text-stone-400 hover:text-rose-600 transition-colors"
          >
            Discard
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

  // Seed proposed + parked lists from a one-shot fetch on mount
  const [options, setOptions] = useState<ExperimentOptions | null>(null);
  const [seedLoading, setSeedLoading] = useState(true);
  const [lastAction, setLastAction] = useState<'completed' | 'parked' | null>(null);
  const [showMore, setShowMore] = useState(false);

  function fetchOptions() {
    api.getExperimentOptions()
      .then(setOptions)
      .catch(() => setOptions(null))
      .finally(() => setSeedLoading(false));
  }

  useEffect(() => {
    fetchOptions();
  }, []);

  // Merge seed + poller proposed results, deduplicated by record ID
  const allProposed = (() => {
    const map = new Map<string, Experiment>();
    for (const exp of options?.proposed ?? []) map.set(exp.experiment_record_id, exp);
    for (const exp of proposed) map.set(exp.experiment_record_id, exp);
    return Array.from(map.values());
  })();

  const parkedExperiments = options?.parked ?? [];
  const atParkCap = options?.at_park_cap ?? false;
  const isPolling = pollState === 'polling';

  // The top recommendation is the first proposed experiment
  const topRecommendation = allProposed[0] ?? null;
  const otherProposed = allProposed.slice(1);

  function handleComplete() {
    setLastAction('completed');
    setShowMore(false);
    resetPoller();
    refetch(false);
    startPolling();
    fetchOptions();
  }

  function handlePark() {
    setLastAction('parked');
    setShowMore(false);
    resetPoller();
    refetch(false);
    startPolling();
    fetchOptions();
  }

  function handleAccepted() {
    setLastAction(null);
    setShowMore(false);
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
            <p className="text-sm font-semibold text-emerald-800">Experiment complete — well done!</p>
            <p className="text-xs text-emerald-700 mt-0.5">Ready for your next challenge? Pick one below.</p>
          </div>
        </div>
      );
    }
    return (
      <div className="bg-amber-50 border border-amber-200 rounded-2xl px-5 py-4 flex items-center gap-3">
        <span className="text-xl">⏸</span>
        <div>
          <p className="text-sm font-semibold text-amber-800">Experiment parked.</p>
          <p className="text-xs text-amber-700 mt-0.5">You can resume it anytime. Pick your next focus below.</p>
        </div>
      </div>
    );
  }

  const overallLoading = seedLoading && !lastAction;

  // At park cap — only show parked experiments, no new proposals
  const showCapScreen = atParkCap && !hasActive;
  // Has options to show (either proposed or parked)
  const hasOptions = allProposed.length > 0 || parkedExperiments.length > 0;
  // Show "See more options" button when there are more options beyond the top recommendation
  const hasMoreOptions = otherProposed.length > 0 || parkedExperiments.length > 0;

  return (
    <div className="max-w-2xl mx-auto space-y-5 py-2">
      <div>
        <h1 className="text-2xl font-bold text-stone-900">My Experiment</h1>
        <p className="text-sm text-stone-500 mt-1">
          Track your progress on your current communication experiment.
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
              <p className="text-sm text-blue-700">Finding your next experiment…</p>
            </div>
          )}

          {/* Park cap screen — user must resume or discard a parked experiment */}
          {showCapScreen && parkedExperiments.length > 0 && (
            <section>
              <div className="bg-amber-50 border border-amber-200 rounded-2xl px-5 py-4 mb-4">
                <p className="text-sm font-medium text-amber-800">
                  You have {parkedExperiments.length} parked experiment{parkedExperiments.length !== 1 ? 's' : ''} (the maximum).
                </p>
                <p className="text-xs text-amber-700 mt-1">
                  Resume one to continue, or discard one to free up space for new suggestions.
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

          {/* Normal flow: top recommendation + see more options */}
          {!showCapScreen && !overallLoading && hasOptions ? (
            <section>
              {/* Top recommendation */}
              {topRecommendation && !showMore && (
                <>
                  <div className="flex items-center justify-between mb-3">
                    <h2 className="text-xs font-semibold text-stone-400 uppercase tracking-widest">
                      {lastAction ? 'Recommended next experiment' : 'Suggested Experiment'}
                    </h2>
                  </div>
                  <ProposedExperimentCard
                    experiment={topRecommendation}
                    onAccepted={handleAccepted}
                  />
                  {hasMoreOptions && (
                    <button
                      onClick={() => setShowMore(true)}
                      className="mt-3 w-full py-2.5 bg-stone-50 border border-stone-200 text-stone-600 rounded-xl text-sm font-medium hover:bg-stone-100 transition-colors"
                    >
                      See more options
                    </button>
                  )}
                </>
              )}

              {/* Expanded: all options (proposed + parked) */}
              {showMore && (
                <>
                  <div className="flex items-center justify-between mb-3">
                    <h2 className="text-xs font-semibold text-stone-400 uppercase tracking-widest">
                      Choose your next experiment
                    </h2>
                    <button
                      onClick={() => setShowMore(false)}
                      className="text-xs text-stone-500 hover:text-stone-700 transition-colors"
                    >
                      Back to recommendation
                    </button>
                  </div>

                  <div className="space-y-3">
                    {/* All proposed experiments */}
                    {allProposed.map((exp, i) => (
                      <div key={exp.experiment_record_id}>
                        {i === 0 && (
                          <p className="text-xs text-emerald-600 font-medium mb-1.5">Top pick</p>
                        )}
                        <ProposedExperimentCard
                          experiment={exp}
                          onAccepted={handleAccepted}
                          compact={i > 0}
                        />
                      </div>
                    ))}

                    {/* Parked experiments section */}
                    {parkedExperiments.length > 0 && (
                      <>
                        <div className="pt-2">
                          <p className="text-xs font-semibold text-stone-400 uppercase tracking-widest mb-3">
                            Previously parked
                          </p>
                        </div>
                        {parkedExperiments.map((exp) => (
                          <ParkedExperimentCard
                            key={exp.experiment_record_id}
                            experiment={exp}
                            onResumed={handleResumed}
                            onDiscarded={handleDiscarded}
                          />
                        ))}
                      </>
                    )}
                  </div>
                </>
              )}

              {/* No proposals yet but parked exist — show parked + polling hint */}
              {allProposed.length === 0 && parkedExperiments.length > 0 && !showMore && (
                <>
                  {isPolling && (
                    <div className="bg-blue-50 border border-blue-100 rounded-xl px-4 py-3 flex items-center gap-3 mb-3">
                      <div className="animate-spin rounded-full h-3.5 w-3.5 border-b-2 border-blue-500 flex-shrink-0" />
                      <p className="text-xs text-blue-700">New suggestions arriving shortly…</p>
                    </div>
                  )}
                  <h2 className="text-xs font-semibold text-stone-400 uppercase tracking-widest mb-3">
                    {isPolling ? 'Or resume a parked experiment' : 'Resume a parked experiment'}
                  </h2>
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
                </>
              )}
            </section>
          ) : !showCapScreen && !overallLoading && !isPolling && !hasOptions ? (
            <div className="bg-white rounded-2xl border border-dashed border-stone-300 p-12 text-center space-y-4">
              <div className="text-4xl">🧪</div>
              <p className="text-stone-600 font-medium">No active experiment</p>
              <p className="text-sm text-stone-400 max-w-xs mx-auto leading-relaxed">
                Complete a baseline pack or single-meeting analysis to receive your first personalised experiment.
              </p>
              <div className="flex gap-3 justify-center pt-2">
                <Link
                  href="/client/analyze"
                  className="px-5 py-2.5 bg-emerald-600 text-white rounded-xl text-sm font-medium hover:bg-emerald-700 transition-colors"
                >
                  Analyse a meeting
                </Link>
                <Link
                  href="/client/baseline/new"
                  className="px-5 py-2.5 bg-white border border-stone-300 text-stone-700 rounded-xl text-sm font-medium hover:bg-stone-50 transition-colors"
                >
                  Create baseline
                </Link>
              </div>
            </div>
          ) : null}
        </>
      )}
    </div>
  );
}

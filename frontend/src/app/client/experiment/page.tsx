'use client';

import { useState, useEffect } from 'react';
import Link from 'next/link';
import { api } from '@/lib/api';
import { useActiveExperiment } from '@/hooks/useActiveExperiment';
import { useProposedPoller } from '@/hooks/useProposedPoller';
import { ExperimentTracker } from '@/components/ExperimentTracker';
import type { Experiment } from '@/lib/types';

function PatternLabel({ id }: { id: string }) {
  return (
    <span className="text-xs font-semibold text-stone-400 uppercase tracking-widest">
      {id.replace(/_/g, ' ')}
    </span>
  );
}

function ProposedExperimentCard({
  experiment,
  onAccepted,
}: {
  experiment: Experiment;
  onAccepted: () => void;
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
      <div className="flex items-center gap-3">
        <button
          onClick={handleAccept}
          disabled={state === 'loading'}
          className="px-4 py-2 bg-emerald-600 text-white rounded-xl text-xs font-semibold hover:bg-emerald-700 transition-colors disabled:opacity-60"
        >
          {state === 'loading' ? 'Accepting…' : 'Accept experiment'}
        </button>
        <Link
          href="/client"
          className="text-xs text-stone-500 hover:text-stone-700 transition-colors"
        >
          Decide later
        </Link>
        <span className="text-xs text-stone-400 ml-auto">{experiment.experiment_id}</span>
      </div>
    </div>
  );
}

export default function ExperimentPage() {
  const { data, loading, error, refetch } = useActiveExperiment();
  const { proposed, pollState, startPolling, reset: resetPoller } = useProposedPoller();

  // Seed proposed list from a one-shot fetch on mount (for pre-existing proposals)
  const [seedProposed, setSeedProposed] = useState<Experiment[]>([]);
  const [seedLoading, setSeedLoading] = useState(true);
  const [lastAction, setLastAction] = useState<'completed' | 'abandoned' | null>(null);

  useEffect(() => {
    api.getProposedExperiments()
      .then(setSeedProposed)
      .catch(() => setSeedProposed([]))
      .finally(() => setSeedLoading(false));
  }, []);

  // Merge seed + poller results, deduplicated by record ID
  const allProposed = (() => {
    const map = new Map<string, Experiment>();
    for (const exp of seedProposed) map.set(exp.experiment_record_id, exp);
    for (const exp of proposed) map.set(exp.experiment_record_id, exp);
    return Array.from(map.values());
  })();

  const isPolling = pollState === 'polling';

  function handleComplete() {
    setLastAction('completed');
    resetPoller();
    refetch();
    startPolling();
  }

  function handleAbandon() {
    setLastAction('abandoned');
    resetPoller();
    refetch();
    startPolling();
  }

  function handleAccepted() {
    setLastAction(null);
    resetPoller();
    refetch();
    // Re-seed proposed list after accepting
    api.getProposedExperiments()
      .then(setSeedProposed)
      .catch(() => setSeedProposed([]));
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
      <div className="bg-stone-50 border border-stone-200 rounded-2xl px-5 py-4 flex items-center gap-3">
        <span className="text-xl">→</span>
        <div>
          <p className="text-sm font-semibold text-stone-700">Experiment abandoned.</p>
          <p className="text-xs text-stone-500 mt-0.5">No problem — pick a new direction below.</p>
        </div>
      </div>
    );
  }

  const overallLoading = seedLoading && !lastAction;

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
          onAbandon={handleAbandon}
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

          {!overallLoading && allProposed.length > 0 ? (
            <section>
              <div className="flex items-center justify-between mb-3">
                <h2 className="text-xs font-semibold text-stone-400 uppercase tracking-widest">
                  {lastAction ? 'Choose your next experiment' : 'Suggested Experiments'}
                </h2>
                <span className="text-xs text-stone-400">
                  {allProposed.length} suggestion{allProposed.length !== 1 ? 's' : ''}
                </span>
              </div>
              <div className="space-y-3">
                {allProposed.map((exp) => (
                  <ProposedExperimentCard
                    key={exp.experiment_record_id}
                    experiment={exp}
                    onAccepted={handleAccepted}
                  />
                ))}
              </div>
            </section>
          ) : !overallLoading && !isPolling ? (
            <div className="bg-white rounded-2xl border border-dashed border-stone-300 p-12 text-center space-y-4">
              <div className="text-4xl">◈</div>
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

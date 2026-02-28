'use client';

import { useRunPoller } from '@/hooks/useRunPoller';
import { CoachingCard } from './CoachingCard';
import { PatternSnapshot } from './PatternSnapshot';

interface RunStatusPollerProps {
  runId: string;
  onComplete?: () => void;
}

export function RunStatusPoller({ runId, onComplete }: RunStatusPollerProps) {
  const { run, pollState, pollCount, retry } = useRunPoller(runId);

  if (pollState === 'polling' || !run) {
    return (
      <div className="flex flex-col items-center justify-center py-16 gap-4">
        <div className="animate-spin rounded-full h-10 w-10 border-b-2 border-indigo-600" />
        <p className="text-sm text-gray-600">
          {pollCount > 20
            ? 'Still processing… this may take a moment.'
            : 'Analyzing your meeting…'}
        </p>
      </div>
    );
  }

  if (pollState === 'timeout') {
    return (
      <div className="text-center py-16 space-y-3">
        <p className="text-sm text-amber-700">
          This is taking longer than expected.
        </p>
        <button
          onClick={retry}
          className="text-sm px-4 py-2 bg-indigo-600 text-white rounded-md hover:bg-indigo-700"
        >
          Check again
        </button>
      </div>
    );
  }

  if (pollState === 'error' || run.status === 'error') {
    return (
      <div className="text-center py-16 space-y-3">
        <p className="text-sm text-red-700">
          {run?.error
            ? JSON.stringify(run.error)
            : 'Analysis failed. Please try again.'}
        </p>
        <button
          onClick={retry}
          className="text-sm px-4 py-2 bg-indigo-600 text-white rounded-md hover:bg-indigo-700"
        >
          Retry
        </button>
      </div>
    );
  }

  if (run.status === 'complete' && run.gate1_pass === false) {
    return (
      <div className="bg-amber-50 border border-amber-200 rounded-lg p-6">
        <p className="text-sm font-medium text-amber-800">
          Validation did not pass (Gate 1 fail).
        </p>
        <p className="text-xs text-amber-700 mt-1">
          The AI output did not meet quality requirements. Please try re-running.
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-8">
      <CoachingCard
        strengths={run.strengths}
        focus={run.focus}
        microExperiment={run.micro_experiment}
      />

      {run.pattern_snapshot && run.pattern_snapshot.length > 0 && (
        <section>
          <h3 className="text-sm font-semibold text-gray-700 uppercase tracking-wide mb-3">
            Pattern Snapshot
          </h3>
          <PatternSnapshot patterns={run.pattern_snapshot as never} />
        </section>
      )}
    </div>
  );
}

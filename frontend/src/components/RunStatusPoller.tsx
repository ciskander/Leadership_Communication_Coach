'use client';

import { useRunPoller } from '@/hooks/useRunPoller';
import { CoachingCard } from './CoachingCard';
import { PatternSnapshot } from './PatternSnapshot';
import Link from 'next/link';

interface RunStatusPollerProps {
  runId: string;
  onComplete?: () => void;
}

export function RunStatusPoller({ runId, onComplete }: RunStatusPollerProps) {
  const { run, pollState, pollCount, retry } = useRunPoller(runId);

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
        microExperiment={run.micro_experiment}
      />

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

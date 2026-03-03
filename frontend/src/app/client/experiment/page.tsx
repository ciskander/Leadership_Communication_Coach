'use client';

import Link from 'next/link';
import { useActiveExperiment } from '@/hooks/useActiveExperiment';
import { ExperimentTracker } from '@/components/ExperimentTracker';

export default function ExperimentPage() {
  const { data, loading, error, refetch } = useActiveExperiment();

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

  return (
    <div className="max-w-2xl mx-auto space-y-5 py-2">
      <div>
        <h1 className="text-2xl font-bold text-stone-900">My Experiment</h1>
        <p className="text-sm text-stone-500 mt-1">
          Track your progress on your current communication experiment.
        </p>
      </div>

      {!experiment ? (
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
      ) : (
        <>
          <ExperimentTracker
            experiment={experiment}
            events={events as Record<string, unknown>[]}
            onUpdate={refetch}
          />

          {(experiment.status === 'completed' || experiment.status === 'abandoned') && (
            <div className="bg-stone-50 rounded-2xl border border-stone-200 p-5 text-center space-y-3">
              <p className="text-sm font-medium text-stone-700">
                {experiment.status === 'completed'
                  ? '🎉 Experiment complete! Ready for your next challenge?'
                  : 'Moving on — ready to try something new?'}
              </p>
              <Link
                href="/client/analyze"
                className="inline-block px-5 py-2.5 bg-emerald-600 text-white rounded-xl text-sm font-medium hover:bg-emerald-700 transition-colors"
              >
                Analyse next meeting →
              </Link>
            </div>
          )}
        </>
      )}
    </div>
  );
}

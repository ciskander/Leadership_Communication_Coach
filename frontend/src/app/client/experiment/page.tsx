'use client';

import { useActiveExperiment } from '@/hooks/useActiveExperiment';
import { ExperimentTracker } from '@/components/ExperimentTracker';

export default function ExperimentPage() {
  const { data, loading, error, refetch } = useActiveExperiment();

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-indigo-600" />
      </div>
    );
  }

  if (error) return <p className="text-sm text-red-600">{error}</p>;

  const experiment = data?.experiment;
  const events = data?.recent_events ?? [];

  return (
    <div className="max-w-2xl mx-auto space-y-6">
      <h1 className="text-2xl font-bold text-gray-900">My Experiment</h1>

      {!experiment || experiment.status === 'none' ? (
        <div className="bg-gray-50 border border-gray-200 rounded-xl p-8 text-center">
          <p className="text-gray-500 text-sm">
            No active experiment. Complete a baseline pack or single-meeting analysis to get one.
          </p>
        </div>
      ) : (
        <ExperimentTracker
          experiment={experiment}
          events={events as Record<string, unknown>[]}
          onUpdate={refetch}
        />
      )}
    </div>
  );
}

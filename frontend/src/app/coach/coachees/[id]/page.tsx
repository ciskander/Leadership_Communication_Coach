'use client';

import { STRINGS } from '@/config/strings';
import { useEffect, useState } from 'react';
import { useParams } from 'next/navigation';
import Link from 'next/link';
import { api } from '@/lib/api';
import type { CoacheeSummary, Experiment } from '@/lib/types';
import { ExperimentTracker } from '@/components/ExperimentTracker';

function PatternLabel({ id }: { id: string }) {
  return (
    <span className="text-xs font-semibold text-stone-400 uppercase tracking-widest">
      {id.replace(/_/g, ' ')}
    </span>
  );
}

function ProposedExperimentRow({ experiment }: { experiment: Experiment }) {
  return (
    <div className="bg-white border border-stone-200 rounded-xl p-4 space-y-2">
      <div className="flex items-start justify-between gap-3">
        <div className="space-y-1 min-w-0">
          <PatternLabel id={experiment.pattern_id} />
          <p className="text-sm font-semibold text-stone-800 leading-snug">
            {experiment.title}
          </p>
        </div>
        <span className="text-xs px-2 py-0.5 rounded-full font-semibold bg-violet-100 text-violet-700 whitespace-nowrap shrink-0">
          {STRINGS.experimentStatus.proposed}
        </span>
      </div>
      <p className="text-xs text-stone-500 leading-relaxed line-clamp-2">
        {experiment.instruction}
      </p>
      <p className="text-xs text-stone-400">{experiment.experiment_id}</p>
    </div>
  );
}

export default function CoacheeDetailPage() {
  const { id } = useParams<{ id: string }>();
  const [data, setData] = useState<CoacheeSummary | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api.getCoacheeSummary(id).then(setData).finally(() => setLoading(false));
  }, [id]);

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-indigo-600" />
      </div>
    );
  }

  if (!data) return <p className="text-sm text-gray-500">{STRINGS.coacheeDetail.coacheeNotFound}</p>;

  const proposedExperiments = data.proposed_experiments ?? [];

  return (
    <div className="max-w-3xl mx-auto space-y-8">
      <div>
        <h1 className="text-2xl font-bold text-gray-900">
          {data.coachee.display_name ?? data.coachee.email}
        </h1>
        <p className="text-sm text-gray-500">{data.coachee.email}</p>
      </div>

      {/* Active Experiment */}
      {data.active_experiment ? (
        <section>
          <h2 className="text-sm font-semibold text-gray-700 uppercase tracking-wide mb-3">
            {STRINGS.coacheeDetail.activeExperiment}
          </h2>
          <ExperimentTracker
            experiment={data.active_experiment}
            events={[]}
          />
        </section>
      ) : (
        <section>
          <h2 className="text-sm font-semibold text-gray-700 uppercase tracking-wide mb-3">
            {STRINGS.coacheeDetail.activeExperiment}
          </h2>
          <div className="bg-white border border-gray-200 rounded-lg px-4 py-3">
            <p className="text-sm text-gray-400">{STRINGS.coacheeDetail.noActiveExperiment}</p>
          </div>
        </section>
      )}

      {/* Proposed Experiments */}
      {proposedExperiments.length > 0 && (
        <section>
          <div className="flex items-center justify-between mb-3">
            <h2 className="text-sm font-semibold text-gray-700 uppercase tracking-wide">
              {STRINGS.coacheeDetail.suggestedExperiments}
            </h2>
            <span className="text-xs text-stone-400">
              {STRINGS.coacheeDetail.inQueue(proposedExperiments.length)}
            </span>
          </div>
          <div className="space-y-2">
            {proposedExperiments.map((exp) => (
              <ProposedExperimentRow key={exp.experiment_record_id} experiment={exp} />
            ))}
          </div>
          <p className="text-xs text-stone-400 mt-2">
            {STRINGS.coacheeDetail.coacheeCanAccept}
          </p>
        </section>
      )}

      {/* Baseline */}
      {data.active_baseline_pack && (
        <section>
          <h2 className="text-sm font-semibold text-gray-700 uppercase tracking-wide mb-3">
            {STRINGS.coacheeDetail.baselinePack}
          </h2>
          <div className="bg-white border border-gray-200 rounded-lg px-4 py-3">
            <p className="text-sm text-gray-700 capitalize">
              {STRINGS.coacheeDetail.status}:{' '}
              {(data.active_baseline_pack as Record<string, unknown>).status as string}
            </p>
          </div>
        </section>
      )}

      {/* Recent Runs */}
      {data.recent_runs.length > 0 && (
        <section>
          <h2 className="text-sm font-semibold text-gray-700 uppercase tracking-wide mb-3">
            {STRINGS.coacheeDetail.recentRuns}
          </h2>
          <ul className="space-y-2">
            {data.recent_runs.map((run: Record<string, unknown>, i) => (
              <li key={(run.run_id as string) ?? i}>
                <Link
                  href={`/client/runs/${run.run_id ?? run.id}`}
                  className="block bg-white border border-gray-200 rounded-lg px-4 py-3 hover:border-indigo-300 transition-colors"
                >
                  <div className="flex justify-between">
                    <span className="text-sm text-gray-800">
                      {(run.meeting_type as string) ?? STRINGS.common.meeting}
                    </span>
                    <span className="text-xs text-gray-400">
                      {run.created_at
                        ? new Date(run.created_at as string).toLocaleDateString()
                        : ''}
                    </span>
                  </div>
                </Link>
              </li>
            ))}
          </ul>
        </section>
      )}
    </div>
  );
}

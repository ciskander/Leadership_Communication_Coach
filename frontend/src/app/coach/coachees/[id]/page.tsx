'use client';

import { useEffect, useState } from 'react';
import { useParams } from 'next/navigation';
import Link from 'next/link';
import { api } from '@/lib/api';
import type { CoacheeSummary } from '@/lib/types';
import { ExperimentTracker } from '@/components/ExperimentTracker';

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

  if (!data) return <p className="text-sm text-gray-500">Coachee not found.</p>;

  return (
    <div className="max-w-3xl mx-auto space-y-8">
      <div>
        <h1 className="text-2xl font-bold text-gray-900">
          {data.coachee.display_name ?? data.coachee.email}
        </h1>
        <p className="text-sm text-gray-500">{data.coachee.email}</p>
      </div>

      {/* Active Experiment */}
      {data.active_experiment && (
        <section>
          <h2 className="text-sm font-semibold text-gray-700 uppercase tracking-wide mb-3">
            Active Experiment
          </h2>
          <ExperimentTracker
            experiment={data.active_experiment}
            events={[]}
          />
        </section>
      )}

      {/* Baseline */}
      {data.active_baseline_pack && (
        <section>
          <h2 className="text-sm font-semibold text-gray-700 uppercase tracking-wide mb-3">
            Baseline Pack
          </h2>
          <div className="bg-white border border-gray-200 rounded-lg px-4 py-3">
            <p className="text-sm text-gray-700 capitalize">
              Status:{' '}
              {(data.active_baseline_pack as Record<string, unknown>).status as string}
            </p>
          </div>
        </section>
      )}

      {/* Recent Runs */}
      {data.recent_runs.length > 0 && (
        <section>
          <h2 className="text-sm font-semibold text-gray-700 uppercase tracking-wide mb-3">
            Recent Runs
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
                      {(run.meeting_type as string) ?? 'Meeting'}
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

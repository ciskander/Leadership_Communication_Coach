'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { api } from '@/lib/api';
import type { ClientSummary } from '@/lib/types';

export default function ClientDashboard() {
  const [summary, setSummary] = useState<ClientSummary | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api.clientSummary().then(setSummary).finally(() => setLoading(false));
  }, []);

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-indigo-600" />
      </div>
    );
  }

  const bpStatus = summary?.baseline_pack_status ?? 'none';
  const experiment = summary?.active_experiment;

  return (
    <div className="max-w-3xl mx-auto space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-gray-900">
          Welcome back{summary?.user.display_name ? `, ${summary.user.display_name}` : ''}
        </h1>
        <p className="text-gray-500 text-sm mt-1">Here's your coaching dashboard.</p>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        {/* Baseline Pack Card */}
        <div className="bg-white rounded-xl border border-gray-200 p-5 space-y-3">
          <div className="flex items-center justify-between">
            <h2 className="font-semibold text-gray-800">Baseline Pack</h2>
            <BaselineStatusBadge status={bpStatus} />
          </div>
          {bpStatus === 'none' && (
            <>
              <p className="text-sm text-gray-500">
                Build your baseline from 3 past meetings to unlock deep coaching.
              </p>
              <Link
                href="/client/baseline/new"
                className="inline-block text-sm px-4 py-2 bg-indigo-600 text-white rounded-md hover:bg-indigo-700"
              >
                Create Baseline Pack
              </Link>
            </>
          )}
          {(bpStatus === 'intake' || bpStatus === 'building') && (
            <p className="text-sm text-amber-600 flex items-center gap-2">
              <span className="animate-spin">⏳</span> Processing… check back soon.
            </p>
          )}
          {bpStatus === 'baseline_ready' && (
            <p className="text-sm text-green-600">Your baseline is ready!</p>
          )}
        </div>

        {/* Active Experiment Card */}
        <div className="bg-white rounded-xl border border-gray-200 p-5 space-y-3">
          <h2 className="font-semibold text-gray-800">Active Experiment</h2>
          {experiment ? (
            <>
              <p className="text-sm text-gray-700 font-medium">{experiment.title}</p>
              <p className="text-xs text-gray-500 capitalize">{experiment.status}</p>
              <Link
                href="/client/experiment"
                className="inline-block text-sm text-indigo-600 hover:underline"
              >
                View experiment →
              </Link>
            </>
          ) : (
            <p className="text-sm text-gray-500">No active experiment.</p>
          )}
        </div>
      </div>

      {/* CTA */}
      <div className="flex gap-3">
        <Link
          href="/client/analyze"
          className="px-5 py-2.5 bg-indigo-600 text-white rounded-lg text-sm font-medium hover:bg-indigo-700"
        >
          Analyze a Meeting
        </Link>
        {bpStatus === 'none' && (
          <Link
            href="/client/baseline/new"
            className="px-5 py-2.5 bg-white border border-gray-300 text-gray-700 rounded-lg text-sm font-medium hover:bg-gray-50"
          >
            Create Baseline Pack
          </Link>
        )}
      </div>

      {/* Recent Runs */}
      {summary && summary.recent_runs.length > 0 && (
        <section>
          <h2 className="text-sm font-semibold text-gray-700 uppercase tracking-wide mb-3">
            Recent Runs
          </h2>
          <ul className="space-y-2">
            {summary.recent_runs.map((run: Record<string, unknown>, i) => (
              <li key={(run.run_id as string) ?? i}>
                <Link
                  href={`/client/runs/${run.run_id ?? run.id}`}
                  className="block bg-white border border-gray-200 rounded-lg px-4 py-3 hover:border-indigo-300 transition-colors"
                >
                  <div className="flex items-center justify-between">
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

function BaselineStatusBadge({ status }: { status: string }) {
  const colors: Record<string, string> = {
    none: 'bg-gray-100 text-gray-600',
    intake: 'bg-blue-100 text-blue-700',
    building: 'bg-amber-100 text-amber-700',
    baseline_ready: 'bg-green-100 text-green-700',
  };
  return (
    <span
      className={`text-xs px-2 py-0.5 rounded-full capitalize font-medium ${
        colors[status] ?? 'bg-gray-100 text-gray-600'
      }`}
    >
      {status === 'none' ? 'Not started' : status.replace('_', ' ')}
    </span>
  );
}

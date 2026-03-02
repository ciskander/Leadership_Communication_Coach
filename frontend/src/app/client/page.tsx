'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { api } from '@/lib/api';
import type { ClientSummary } from '@/lib/types';

function getGreeting() {
  const h = new Date().getHours();
  if (h < 12) return 'Good morning';
  if (h < 17) return 'Good afternoon';
  return 'Good evening';
}

function JourneyStep({
  num, label, done, active,
}: { num: number; label: string; done: boolean; active: boolean }) {
  return (
    <div className="flex items-center gap-2">
      <div
        className={`w-7 h-7 rounded-full flex items-center justify-center text-xs font-bold border-2 transition-colors ${
          done
            ? 'bg-emerald-600 border-emerald-600 text-white'
            : active
            ? 'bg-white border-emerald-600 text-emerald-600'
            : 'bg-white border-stone-300 text-stone-400'
        }`}
      >
        {done ? '✓' : num}
      </div>
      <span
        className={`text-xs font-medium ${
          done ? 'text-emerald-700' : active ? 'text-stone-800' : 'text-stone-400'
        }`}
      >
        {label}
      </span>
    </div>
  );
}

function JourneyConnector({ done }: { done: boolean }) {
  return (
    <div className={`flex-1 h-0.5 mx-1 rounded-full ${done ? 'bg-emerald-500' : 'bg-stone-200'}`} />
  );
}

export default function ClientDashboard() {
  const [summary, setSummary] = useState<ClientSummary | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api.clientSummary().then(setSummary).finally(() => setLoading(false));
  }, []);

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-emerald-600" />
      </div>
    );
  }

  const bpStatus = summary?.baseline_pack_status ?? 'none';
  const experiment = summary?.active_experiment;
  const firstName = summary?.user.display_name?.split(' ')[0] ?? null;

  const hasBaseline = bpStatus === 'baseline_ready' || bpStatus === 'completed';
  const isBuilding = bpStatus === 'intake' || bpStatus === 'building';
  const hasExperiment = !!experiment && experiment.status !== 'none';
  const hasRuns = (summary?.recent_runs.length ?? 0) > 0;

  // Journey steps: baseline → first analysis → active experiment
  const step1Done = hasBaseline;
  const step2Done = hasRuns;
  const step3Done = hasExperiment;
  const currentStep = !step1Done ? 1 : !step2Done ? 2 : !step3Done ? 3 : 3;

  return (
    <div className="max-w-3xl mx-auto space-y-6 py-2">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold text-stone-900">
          {getGreeting()}{firstName ? `, ${firstName}` : ''} 👋
        </h1>
        <p className="text-stone-500 text-sm mt-1">
          Your communication growth dashboard.
        </p>
      </div>

      {/* Journey tracker */}
      <div className="bg-white rounded-2xl border border-stone-200 p-5">
        <p className="text-xs font-semibold text-stone-400 uppercase tracking-widest mb-4">
          Your Journey
        </p>
        <div className="flex items-center">
          <JourneyStep num={1} label="Baseline" done={step1Done} active={currentStep === 1} />
          <JourneyConnector done={step1Done} />
          <JourneyStep num={2} label="First Analysis" done={step2Done} active={currentStep === 2} />
          <JourneyConnector done={step2Done} />
          <JourneyStep num={3} label="Experiment" done={step3Done} active={currentStep === 3} />
          <JourneyConnector done={step3Done} />
          <JourneyStep num={4} label="Growth" done={false} active={false} />
        </div>
        {!hasBaseline && !isBuilding && (
          <div className="mt-4 pt-4 border-t border-stone-100 flex items-center justify-between">
            <p className="text-sm text-stone-600">
              Start by building your baseline from 3 past meetings.
            </p>
            <Link
              href="/client/baseline/new"
              className="text-sm px-4 py-1.5 bg-emerald-600 text-white rounded-lg font-medium hover:bg-emerald-700 transition-colors whitespace-nowrap"
            >
              Get started →
            </Link>
          </div>
        )}
        {isBuilding && (
          <div className="mt-4 pt-4 border-t border-stone-100 flex items-center gap-3">
            <div className="w-4 h-4 rounded-full border-2 border-amber-400 border-t-transparent animate-spin" />
            <p className="text-sm text-amber-700 font-medium">Building your baseline… check back in a few minutes.</p>
          </div>
        )}
        {hasBaseline && !hasExperiment && (
          <div className="mt-4 pt-4 border-t border-stone-100 flex items-center justify-between">
            <p className="text-sm text-stone-600">
              Baseline ready! Analyze a meeting to start your first experiment.
            </p>
            <Link
              href="/client/analyze"
              className="text-sm px-4 py-1.5 bg-emerald-600 text-white rounded-lg font-medium hover:bg-emerald-700 transition-colors whitespace-nowrap"
            >
              Analyze meeting →
            </Link>
          </div>
        )}
      </div>

      {/* Cards row */}
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        {/* Baseline Pack */}
        <div className="bg-white rounded-2xl border border-stone-200 p-5 space-y-3">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <span className="text-lg">◎</span>
              <h2 className="font-semibold text-stone-800 text-sm">Baseline Pack</h2>
            </div>
            <BaselineBadge status={bpStatus} />
          </div>
          {bpStatus === 'none' && (
            <p className="text-xs text-stone-500 leading-relaxed">
              Analyse 3 past meetings to unlock personalised coaching patterns.
            </p>
          )}
          {(hasBaseline) && (
            <p className="text-xs text-emerald-700 font-medium">
              ✓ Your communication patterns have been mapped.
            </p>
          )}
          {isBuilding && (
            <p className="text-xs text-amber-600">Analysis in progress…</p>
          )}
          {bpStatus === 'none' && (
            <Link
              href="/client/baseline/new"
              className="inline-block text-xs px-3 py-1.5 bg-stone-900 text-white rounded-lg font-medium hover:bg-stone-700 transition-colors"
            >
              Create baseline
            </Link>
          )}
        </div>

        {/* Active Experiment */}
        <div className="bg-white rounded-2xl border border-stone-200 p-5 space-y-3">
          <div className="flex items-center gap-2">
            <span className="text-lg">◈</span>
            <h2 className="font-semibold text-stone-800 text-sm">Active Experiment</h2>
          </div>
          {experiment && experiment.status !== 'none' ? (
            <>
              <div className="bg-emerald-50 rounded-lg p-3">
                <p className="text-sm font-semibold text-stone-800 leading-snug">
                  {experiment.title}
                </p>
                <p className="text-xs text-stone-500 mt-1 capitalize">{experiment.status}</p>
              </div>
              <Link
                href="/client/experiment"
                className="inline-block text-xs text-emerald-700 font-semibold hover:text-emerald-800"
              >
                Track progress →
              </Link>
            </>
          ) : (
            <p className="text-xs text-stone-500 leading-relaxed">
              Complete an analysis to receive your first personalised experiment.
            </p>
          )}
        </div>
      </div>

      {/* Quick actions */}
      <div className="flex gap-3">
        <Link
          href="/client/analyze"
          className="flex items-center gap-2 px-5 py-2.5 bg-emerald-600 text-white rounded-xl text-sm font-medium hover:bg-emerald-700 transition-colors shadow-sm"
        >
          <span>⊕</span> Analyze a Meeting
        </Link>
        {bpStatus === 'none' && (
          <Link
            href="/client/baseline/new"
            className="flex items-center gap-2 px-5 py-2.5 bg-white border border-stone-300 text-stone-700 rounded-xl text-sm font-medium hover:bg-stone-50 transition-colors"
          >
            <span>◎</span> Create Baseline
          </Link>
        )}
      </div>

      {/* Recent Runs */}
      {summary && summary.recent_runs.length > 0 && (
        <section>
          <h2 className="text-xs font-semibold text-stone-400 uppercase tracking-widest mb-3">
            Recent Analyses
          </h2>
          <ul className="space-y-2">
            {summary.recent_runs.map((run: Record<string, unknown>, i) => (
              <li key={(run.run_id as string) ?? i}>
                <Link
                  href={`/client/runs/${run.run_id ?? run.id}`}
                  className="flex items-center justify-between bg-white border border-stone-200 rounded-xl px-4 py-3 hover:border-emerald-300 hover:shadow-sm transition-all"
                >
                  <div className="flex items-center gap-3">
                    <div className={`w-2 h-2 rounded-full ${run.gate1_pass ? 'bg-emerald-500' : 'bg-rose-400'}`} />
                    <span className="text-sm text-stone-700 font-medium">
                      {(run.analysis_type as string) === 'baseline_pack'
                        ? 'Baseline Pack'
                        : (run.meeting_type as string) ?? 'Meeting Analysis'}
                    </span>
                  </div>
                  <span className="text-xs text-stone-400">
                    {run.created_at
                      ? new Date(run.created_at as string).toLocaleDateString('en-US', {
                          month: 'short', day: 'numeric',
                        })
                      : ''}
                  </span>
                </Link>
              </li>
            ))}
          </ul>
        </section>
      )}
    </div>
  );
}

function BaselineBadge({ status }: { status: string }) {
  const map: Record<string, { color: string; label: string }> = {
    none:           { color: 'bg-stone-100 text-stone-500', label: 'Not started' },
    intake:         { color: 'bg-blue-100 text-blue-700',   label: 'Uploading' },
    building:       { color: 'bg-amber-100 text-amber-700', label: 'Building' },
    baseline_ready: { color: 'bg-emerald-100 text-emerald-700', label: 'Ready' },
    completed:      { color: 'bg-emerald-100 text-emerald-700', label: 'Ready' },
    error:          { color: 'bg-rose-100 text-rose-700',   label: 'Error' },
  };
  const { color, label } = map[status] ?? map.none;
  return (
    <span className={`text-xs px-2 py-0.5 rounded-full font-semibold ${color}`}>
      {label}
    </span>
  );
}

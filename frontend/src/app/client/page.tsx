'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { api } from '@/lib/api';
import type { ClientSummary, Experiment } from '@/lib/types';

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

function PatternLabel({ id }: { id: string }) {
  return (
    <span className="text-xs font-semibold text-stone-400 uppercase tracking-widest">
      {id.replace(/_/g, ' ')}
    </span>
  );
}

function ProposedExperimentCard({
  experiment,
  hasActiveExperiment,
  onAccepted,
}: {
  experiment: Experiment;
  hasActiveExperiment: boolean;
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
      const msg = err instanceof Error ? err.message : 'Something went wrong.';
      setErrorMsg(msg);
      setState('error');
    }
  }

  return (
    <div className="bg-white rounded-2xl border border-stone-200 p-5 space-y-3">
      <div className="space-y-1">
        <PatternLabel id={experiment.pattern_id} />
        <p className="text-sm font-semibold text-stone-900 leading-snug">
          {experiment.title}
        </p>
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
      {errorMsg && (
        <p className="text-xs text-rose-600">{errorMsg}</p>
      )}
      <div className="flex items-center gap-3">
        {hasActiveExperiment ? (
          <div className="group relative">
            <button
              disabled
              className="px-4 py-2 bg-stone-100 text-stone-400 rounded-xl text-xs font-semibold cursor-not-allowed"
            >
              Accept
            </button>
            <div className="absolute bottom-full left-0 mb-1.5 hidden group-hover:block z-10">
              <div className="bg-stone-800 text-white text-xs rounded-lg px-3 py-1.5 whitespace-nowrap">
                Complete your current experiment first
              </div>
            </div>
          </div>
        ) : (
          <>
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
          </>
        )}
        <span className="text-xs text-stone-400 ml-auto">{experiment.experiment_id}</span>
      </div>
    </div>
  );
}

// ── Recent Analysis Card ───────────────────────────────────────────────────────

const ROLE_LABELS: Record<string, string> = {
  chair: 'Chair',
  presenter: 'Presenter',
  participant: 'Participant',
  manager_1to1: 'Manager (1:1)',
  report_1to1: 'Report (1:1)',
};

function fmtDate(dateStr: string | null | undefined): string {
  if (!dateStr) return '';
  try {
    return new Date(dateStr).toLocaleDateString('en-GB', {
      day: 'numeric', month: 'short', year: 'numeric',
    });
  } catch {
    return dateStr;
  }
}

function RecentRunCard({ run }: { run: Record<string, unknown> }) {
  const runId = (run.run_id ?? run.id) as string;
  const isBaseline = run.analysis_type === 'baseline_pack';
  const title = run.title as string | undefined;
  const transcriptId = run.transcript_id as string | undefined;
  const meetingDate = run.meeting_date as string | undefined;
  const meetingType = run.meeting_type as string | undefined;
  const targetRole = run.target_role as string | undefined;

  return (
    <Link
      href={`/client/runs/${runId}`}
      className="flex items-start justify-between bg-white border border-stone-200 rounded-xl px-4 py-3 hover:border-emerald-300 hover:shadow-sm transition-all gap-4"
    >
      <div className="flex items-start gap-3 min-w-0">
        <div
          className={`mt-1.5 w-2 h-2 rounded-full flex-shrink-0 ${
            run.gate1_pass ? 'bg-emerald-500' : 'bg-rose-400'
          }`}
        />
        <div className="min-w-0 space-y-0.5">
          {/* Title / type */}
          <p className="text-sm font-semibold text-stone-800 truncate">
            {title || (isBaseline ? 'Baseline Pack Analysis' : 'Meeting Analysis')}
          </p>
          {/* Meta row */}
          <div className="flex flex-wrap items-center gap-x-2 gap-y-0.5 text-xs text-stone-400">
            {transcriptId && (
              <span className="font-mono">{transcriptId}</span>
            )}
            {meetingType && (
              <>
                {transcriptId && <span>·</span>}
                <span>{meetingType}</span>
              </>
            )}
            {targetRole && (
              <>
                <span>·</span>
                <span>{ROLE_LABELS[targetRole] ?? targetRole}</span>
              </>
            )}
          </div>
        </div>
      </div>
      {/* Date */}
      <span className="text-xs text-stone-400 flex-shrink-0 mt-0.5">
        {fmtDate(meetingDate) || fmtDate(run.created_at as string)}
      </span>
    </Link>
  );
}

// ── Page ──────────────────────────────────────────────────────────────────────

export default function ClientDashboard() {
  const [summary, setSummary] = useState<ClientSummary | null>(null);
  const [loading, setLoading] = useState(true);

  function reload() {
    setLoading(true);
    api.clientSummary().then(setSummary).finally(() => setLoading(false));
  }

  useEffect(() => {
    reload();
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
  const proposedExperiments = summary?.proposed_experiments ?? [];
  const firstName = summary?.user.display_name?.split(' ')[0] ?? null;

  const hasBaseline = bpStatus === 'baseline_ready' || bpStatus === 'completed';
  const isBuilding = bpStatus === 'intake' || bpStatus === 'building';
  const hasExperiment = !!experiment && experiment.status === 'active';
  const hasRuns = (summary?.recent_runs.length ?? 0) > 0;

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
        {hasBaseline && !hasExperiment && proposedExperiments.length === 0 && (
          <div className="mt-4 pt-4 border-t border-stone-100 flex items-center justify-between">
            <p className="text-sm text-stone-600">
              Baseline ready! Analyze a meeting to receive your first experiment suggestion.
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
          {hasBaseline && (
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
          {experiment ? (
            <>
              <div className="bg-emerald-50 rounded-lg p-3 space-y-1">
                <PatternLabel id={experiment.pattern_id} />
                <p className="text-sm font-semibold text-stone-800 leading-snug">
                  {experiment.title}
                </p>
                {experiment.attempt_count != null && experiment.attempt_count > 0 && (
                  <p className="text-xs text-emerald-700 font-medium">
                    {experiment.attempt_count} meeting{experiment.attempt_count !== 1 ? 's' : ''} attempted
                  </p>
                )}
              </div>
              <Link
                href="/client/experiment"
                className="inline-block text-xs text-emerald-700 font-semibold hover:text-emerald-800"
              >
                Track progress →
              </Link>
            </>
          ) : proposedExperiments.length > 0 ? (
            <p className="text-xs text-stone-500 leading-relaxed">
              You have experiment suggestions waiting below — accept one to get started.
            </p>
          ) : (
            <p className="text-xs text-stone-500 leading-relaxed">
              Complete an analysis to receive your first personalised experiment.
            </p>
          )}
        </div>
      </div>

      {/* Suggested experiments queue */}
      {proposedExperiments.length > 0 && (
        <section>
          <div className="flex items-center justify-between mb-3">
            <h2 className="text-xs font-semibold text-stone-400 uppercase tracking-widest">
              Suggested Experiments
            </h2>
            <span className="text-xs text-stone-400">
              {proposedExperiments.length} suggestion{proposedExperiments.length !== 1 ? 's' : ''}
            </span>
          </div>
          <div className="space-y-3">
            {proposedExperiments.map((exp) => (
              <ProposedExperimentCard
                key={exp.experiment_record_id}
                experiment={exp}
                hasActiveExperiment={hasExperiment}
                onAccepted={reload}
              />
            ))}
          </div>
        </section>
      )}

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

      {/* Recent Analyses */}
      {summary && summary.recent_runs.length > 0 && (
        <section>
          <h2 className="text-xs font-semibold text-stone-400 uppercase tracking-widest mb-3">
            Recent Analyses
          </h2>
          <ul className="space-y-2">
            {summary.recent_runs.map((run: Record<string, unknown>, i) => (
              <li key={(run.run_id as string) ?? i}>
                <RecentRunCard run={run} />
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

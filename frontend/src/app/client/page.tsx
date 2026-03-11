'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { api } from '@/lib/api';
import { STRINGS } from '@/config/strings';
import type { ClientSummary, Experiment } from '@/lib/types';

function getGreeting() {
  const h = new Date().getHours();
  if (h < 12) return STRINGS.clientDashboard.greetingMorning;
  if (h < 17) return STRINGS.clientDashboard.greetingAfternoon;
  return STRINGS.clientDashboard.greetingEvening;
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
          <p className="text-xs font-semibold text-stone-400 uppercase tracking-widest mb-1">{STRINGS.common.whatToDo}</p>
          <p className="text-xs text-stone-600 leading-relaxed">{experiment.instruction}</p>
        </div>
        <div className="bg-stone-50 rounded-xl p-3">
          <p className="text-xs font-semibold text-stone-400 uppercase tracking-widest mb-1">{STRINGS.common.successLooksLike}</p>
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
              {STRINGS.clientDashboard.accept}
            </button>
            <div className="absolute bottom-full left-0 mb-1.5 hidden group-hover:block z-10">
              <div className="bg-stone-800 text-white text-xs rounded-lg px-3 py-1.5 whitespace-nowrap">
                {STRINGS.clientDashboard.completeCurrentFirst}
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
              {state === 'loading' ? STRINGS.common.accepting : STRINGS.common.acceptExperiment}
            </button>
            <Link
              href="/client"
              className="text-xs text-stone-500 hover:text-stone-700 transition-colors"
            >
              {STRINGS.common.decideLater}
            </Link>
          </>
        )}
        <span className="text-xs text-stone-400 ml-auto">{experiment.experiment_id}</span>
      </div>
    </div>
  );
}

// ── Helpers ───────────────────────────────────────────────────────────────────

const ROLE_LABELS = STRINGS.roles;

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

// ── Confirm Delete Modal ──────────────────────────────────────────────────────

function ConfirmDeleteModal({
  count,
  onConfirm,
  onCancel,
  deleting,
}: {
  count: number;
  onConfirm: () => void;
  onCancel: () => void;
  deleting: boolean;
}) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/40">
      <div className="bg-white rounded-2xl shadow-xl max-w-sm w-full p-6 space-y-4">
        <div className="flex items-start gap-3">
          <div className="w-9 h-9 rounded-full bg-rose-100 flex items-center justify-center flex-shrink-0">
            <svg className="w-5 h-5 text-rose-600" viewBox="0 0 20 20" fill="currentColor">
              <path fillRule="evenodd" d="M8.485 2.495c.673-1.167 2.357-1.167 3.03 0l6.28 10.875c.673 1.167-.17 2.625-1.516 2.625H3.72c-1.347 0-2.189-1.458-1.515-2.625L8.485 2.495zM10 5a.75.75 0 01.75.75v3.5a.75.75 0 01-1.5 0v-3.5A.75.75 0 0110 5zm0 9a1 1 0 100-2 1 1 0 000 2z" clipRule="evenodd" />
            </svg>
          </div>
          <div>
            <h3 className="font-semibold text-stone-900 text-sm">
              {STRINGS.clientDashboard.deleteModalTitle(count)}
            </h3>
            <p className="text-xs text-stone-500 mt-1 leading-relaxed">
              {STRINGS.clientDashboard.deleteModalDesc(count)}
            </p>
          </div>
        </div>
        <div className="flex gap-2 justify-end pt-1">
          <button
            onClick={onCancel}
            disabled={deleting}
            className="px-4 py-2 text-xs font-semibold text-stone-600 bg-stone-100 rounded-xl hover:bg-stone-200 transition-colors disabled:opacity-50"
          >
            {STRINGS.common.cancel}
          </button>
          <button
            onClick={onConfirm}
            disabled={deleting}
            className="px-4 py-2 text-xs font-semibold text-white bg-rose-600 rounded-xl hover:bg-rose-700 transition-colors disabled:opacity-50 flex items-center gap-1.5"
          >
            {deleting && (
              <svg className="w-3 h-3 animate-spin" viewBox="0 0 24 24" fill="none">
                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z" />
              </svg>
            )}
            {deleting ? STRINGS.common.deleting : STRINGS.common.delete}
          </button>
        </div>
      </div>
    </div>
  );
}

// ── Recent Run Card ───────────────────────────────────────────────────────────

function RecentRunCard({
  run,
  editMode,
  selected,
  onToggle,
}: {
  run: Record<string, unknown>;
  editMode: boolean;
  selected: boolean;
  onToggle: (runId: string) => void;
}) {
  const runId = (run.run_id ?? run.id) as string;
  const isBaseline = run.analysis_type === 'baseline_pack';
  const title = run.title as string | undefined;
  const transcriptId = run.transcript_id as string | undefined;
  const meetingDate = run.meeting_date as string | undefined;
  const meetingType = run.meeting_type as string | undefined;
  const targetRole = run.target_role as string | undefined;

  const metaContent = (
    <div className="flex items-start gap-3 min-w-0 flex-1">
      {/* Checkbox in edit mode */}
      {editMode && (
        <div className="mt-0.5 flex-shrink-0">
          {isBaseline ? (
            // Baseline packs: greyed-out, non-interactive checkbox
            <div
              className="w-4 h-4 rounded border border-stone-200 bg-stone-100"
              title={STRINGS.clientDashboard.baselineCannotDeleteTooltip}
            />
          ) : (
            <div
              className={`w-4 h-4 rounded border-2 flex items-center justify-center transition-colors ${
                selected ? 'bg-rose-600 border-rose-600' : 'border-stone-300 bg-white'
              }`}
            >
              {selected && (
                <svg className="w-2.5 h-2.5 text-white" viewBox="0 0 10 10" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M1.5 5.5l2.5 2.5 4.5-5" />
                </svg>
              )}
            </div>
          )}
        </div>
      )}

      {/* Status dot (normal mode only) */}
      {!editMode && (
        <div className={`mt-1.5 w-2 h-2 rounded-full flex-shrink-0 ${run.gate1_pass ? 'bg-emerald-500' : 'bg-rose-400'}`} />
      )}

      <div className="min-w-0 space-y-0.5">
        <p className="text-sm font-semibold text-stone-800 truncate">
          {isBaseline ? STRINGS.clientDashboard.baselinePackTitle : (title || STRINGS.common.meetingAnalysis)}
        </p>
        <div className="flex flex-wrap items-center gap-x-2 gap-y-0.5 text-xs text-stone-400">
          {isBaseline ? (
            <span className="inline-flex items-center bg-blue-50 text-blue-600 text-xs px-1.5 py-0.5 rounded font-medium">
              {STRINGS.clientDashboard.baselinePackTitle}
            </span>
          ) : (
            <>
              {transcriptId && <span className="font-mono">{transcriptId}</span>}
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
            </>
          )}
        </div>
      </div>
    </div>
  );

  const dateLabel = (
    <span className="text-xs text-stone-400 flex-shrink-0 mt-0.5">
      {fmtDate(meetingDate) || fmtDate(run.created_at as string)}
    </span>
  );

  if (editMode) {
    return (
      <div
        onClick={() => !isBaseline && onToggle(runId)}
        className={`flex items-start justify-between px-4 py-3 rounded-xl border gap-4 transition-all select-none ${
          isBaseline
            ? 'bg-stone-50 border-stone-200 cursor-default opacity-60'
            : selected
            ? 'bg-rose-50 border-rose-300 cursor-pointer'
            : 'bg-white border-stone-200 cursor-pointer hover:border-stone-300'
        }`}
      >
        {metaContent}
        {dateLabel}
      </div>
    );
  }

  return (
    <Link
      href={isBaseline ? `/client/baseline/${run.baseline_pack_id as string}` : `/client/runs/${runId}`}
      className="flex items-start justify-between bg-white border border-stone-200 rounded-xl px-4 py-3 hover:border-emerald-300 hover:shadow-sm transition-all gap-4"
    >
      {metaContent}
      {dateLabel}
    </Link>
  );
}

// ── Page ──────────────────────────────────────────────────────────────────────

export default function ClientDashboard() {
  const [summary, setSummary] = useState<ClientSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [editMode, setEditMode] = useState(false);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [showConfirm, setShowConfirm] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [deleteError, setDeleteError] = useState<string | null>(null);

  function reload() {
    setLoading(true);
    api.clientSummary().then(setSummary).finally(() => setLoading(false));
  }

  useEffect(() => { reload(); }, []);

  function toggleEditMode() {
    setEditMode((v) => !v);
    setSelected(new Set());
    setDeleteError(null);
  }

  function toggleSelect(runId: string) {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(runId)) next.delete(runId);
      else next.add(runId);
      return next;
    });
  }

  async function handleDeleteConfirmed() {
    setDeleting(true);
    setDeleteError(null);
    const ids = Array.from(selected);
    const failed: string[] = [];
    for (const id of ids) {
      try {
        await api.deleteRun(id);
      } catch {
        failed.push(id);
      }
    }
    setDeleting(false);
    setShowConfirm(false);
    if (failed.length > 0) {
      setDeleteError(`${failed.length} deletion${failed.length > 1 ? 's' : ''} failed. Please try again.`);
    }
    setSelected(new Set());
    setEditMode(false);
    reload();
  }

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
  const parkedCount = summary?.parked_experiment_count ?? 0;
  const firstName = summary?.user.display_name?.split(' ')[0] ?? null;

  const hasBaseline = bpStatus === 'baseline_ready' || bpStatus === 'completed';
  const isBuilding = bpStatus === 'intake' || bpStatus === 'building';
  const hasExperiment = !!experiment && experiment.status === 'active';
  const hasRuns = (summary?.recent_runs.length ?? 0) > 0;
  const hasExperimentOptions = proposedExperiments.length > 0 || parkedCount > 0;

  const step1Done = hasBaseline;
  const step2Done = hasRuns;
  const step3Done = hasExperiment;
  const currentStep = !step1Done ? 1 : !step2Done ? 2 : !step3Done ? 3 : 3;

  const deletableRunCount = (summary?.recent_runs ?? []).filter(
    (r: Record<string, unknown>) => r.analysis_type !== 'baseline_pack'
  ).length;

  return (
    <div className="max-w-3xl mx-auto space-y-6 py-2">

      {showConfirm && (
        <ConfirmDeleteModal
          count={selected.size}
          onConfirm={handleDeleteConfirmed}
          onCancel={() => setShowConfirm(false)}
          deleting={deleting}
        />
      )}

      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold text-stone-900">
          {getGreeting()}{firstName ? `, ${firstName}` : ''} 👋
        </h1>
        <p className="text-stone-500 text-sm mt-1">
          {STRINGS.clientDashboard.subtitle}
        </p>
      </div>

      {/* Journey tracker */}
      <div className="bg-white rounded-2xl border border-stone-200 p-5">
        <p className="text-xs font-semibold text-stone-400 uppercase tracking-widest mb-4">
          {STRINGS.clientDashboard.yourJourney}
        </p>
        <div className="flex items-center">
          <JourneyStep num={1} label={STRINGS.clientDashboard.journeyBaseline} done={step1Done} active={currentStep === 1} />
          <JourneyConnector done={step1Done} />
          <JourneyStep num={2} label={STRINGS.clientDashboard.journeyFirstAnalysis} done={step2Done} active={currentStep === 2} />
          <JourneyConnector done={step2Done} />
          <JourneyStep num={3} label={STRINGS.clientDashboard.journeyExperiment} done={step3Done} active={currentStep === 3} />
          <JourneyConnector done={step3Done} />
          <JourneyStep num={4} label={STRINGS.clientDashboard.journeyGrowth} done={false} active={false} />
        </div>
        {!hasBaseline && !isBuilding && (
          <div className="mt-4 pt-4 border-t border-stone-100 flex items-center justify-between">
            <p className="text-sm text-stone-600">{STRINGS.clientDashboard.startBaseline}</p>
            <Link href="/client/baseline/new" className="text-sm px-4 py-1.5 bg-emerald-600 text-white rounded-lg font-medium hover:bg-emerald-700 transition-colors whitespace-nowrap">
              {STRINGS.clientDashboard.getStarted}
            </Link>
          </div>
        )}
        {isBuilding && (
          <div className="mt-4 pt-4 border-t border-stone-100 flex items-center gap-3">
            <div className="w-4 h-4 rounded-full border-2 border-amber-400 border-t-transparent animate-spin" />
            <p className="text-sm text-amber-700 font-medium">{STRINGS.clientDashboard.buildingBaseline}</p>
          </div>
        )}
        {hasBaseline && !hasExperiment && hasExperimentOptions && (
          <div className="mt-4 pt-4 border-t border-stone-100 flex items-center justify-between">
            <p className="text-sm text-stone-600">{STRINGS.clientDashboard.experimentOptionsWaiting}</p>
            <Link href="/client/experiment" className="text-sm px-4 py-1.5 bg-emerald-600 text-white rounded-lg font-medium hover:bg-emerald-700 transition-colors whitespace-nowrap">
              {STRINGS.clientDashboard.chooseExperiment}
            </Link>
          </div>
        )}
        {hasBaseline && !hasExperiment && !hasExperimentOptions && (
          <div className="mt-4 pt-4 border-t border-stone-100 flex items-center justify-between">
            <p className="text-sm text-stone-600">{STRINGS.clientDashboard.baselineReadyAnalyze}</p>
            <Link href="/client/analyze" className="text-sm px-4 py-1.5 bg-blue-600 text-white rounded-lg font-medium hover:bg-blue-700 transition-colors whitespace-nowrap">
              {STRINGS.clientDashboard.analyzeMeetingArrow}
            </Link>
          </div>
        )}
      </div>

      {/* Cards row */}
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        <div className="bg-white rounded-2xl border border-stone-200 p-5 space-y-3">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <span className="text-lg">📚</span>
              <h2 className="font-semibold text-stone-800 text-sm">{STRINGS.clientDashboard.baselinePackTitle}</h2>
            </div>
            <BaselineBadge status={bpStatus} />
          </div>
          {bpStatus === 'none' && <p className="text-xs text-stone-500 leading-relaxed">{STRINGS.clientDashboard.baselinePackCta}</p>}
          {hasBaseline && <p className="text-xs text-emerald-700 font-medium">{STRINGS.clientDashboard.baselinePackDone}</p>}
          {isBuilding && <p className="text-xs text-amber-600">{STRINGS.clientDashboard.analysisInProgress}</p>}
          {bpStatus === 'none' && (
            <Link href="/client/baseline/new" className="inline-block text-xs px-3 py-1.5 bg-stone-900 text-white rounded-lg font-medium hover:bg-stone-700 transition-colors">
              {STRINGS.clientDashboard.createBaseline}
            </Link>
          )}
        </div>

        <div className="bg-white rounded-2xl border border-stone-200 p-5 space-y-3">
          <div className="flex items-center gap-2">
            <span className="text-lg">🧪</span>
            <h2 className="font-semibold text-stone-800 text-sm">{STRINGS.clientDashboard.activeExperimentTitle}</h2>
          </div>
          {experiment ? (
            <>
              <div className="bg-emerald-50 rounded-lg p-3 space-y-1">
                <PatternLabel id={experiment.pattern_id} />
                <p className="text-sm font-semibold text-stone-800 leading-snug">{experiment.title}</p>
                {experiment.attempt_count != null && experiment.attempt_count > 0 && (
                  <p className="text-xs text-emerald-700 font-medium">
                    {experiment.attempt_count} attempt{experiment.attempt_count !== 1 ? 's' : ''}{experiment.meeting_count != null && experiment.meeting_count > 0 ? ` across ${experiment.meeting_count} meeting${experiment.meeting_count !== 1 ? 's' : ''}` : ''}
                  </p>
                )}
              </div>
              <Link href="/client/experiment" className="inline-block text-xs text-emerald-700 font-semibold hover:text-emerald-800">
                {STRINGS.clientDashboard.trackProgress}
              </Link>
            </>
          ) : hasExperimentOptions ? (
            <p className="text-xs text-stone-500 leading-relaxed">
              {STRINGS.clientDashboard.experimentOptionsWaitingShort}{' '}
              <Link href="/client/experiment" className="text-emerald-700 font-semibold hover:text-emerald-800">
                {STRINGS.clientDashboard.experimentOptionsChoose}
              </Link>
            </p>
          ) : (
            <p className="text-xs text-stone-500 leading-relaxed">{STRINGS.clientDashboard.completeAnalysisForExperiment}</p>
          )}
        </div>
      </div>

      {/* Suggested experiments */}
      {proposedExperiments.length > 0 && (
        <section>
          <div className="flex items-center justify-between mb-3">
            <h2 className="text-xs font-semibold text-stone-400 uppercase tracking-widest">{STRINGS.clientDashboard.suggestedExperiments}</h2>
            <span className="text-xs text-stone-400">{STRINGS.clientDashboard.suggestions(proposedExperiments.length)}</span>
          </div>
          <div className="space-y-3">
            {proposedExperiments.map((exp) => (
              <ProposedExperimentCard key={exp.experiment_record_id} experiment={exp} hasActiveExperiment={hasExperiment} onAccepted={reload} />
            ))}
          </div>
        </section>
      )}

      {/* Quick actions */}
      <div className="flex gap-3">
        <Link href="/client/analyze" className="flex items-center gap-2 px-5 py-2.5 bg-blue-600 text-white rounded-xl text-sm font-medium hover:bg-blue-700 transition-colors shadow-sm">
          <span>✨</span> {STRINGS.clientDashboard.analyzeMeetingBtn}
        </Link>
        {bpStatus === 'none' && (
          <Link href="/client/baseline/new" className="flex items-center gap-2 px-5 py-2.5 bg-white border border-stone-300 text-stone-700 rounded-xl text-sm font-medium hover:bg-stone-50 transition-colors">
            <span>📚</span> {STRINGS.clientDashboard.createBaselineBtn}
          </Link>
        )}
      </div>

      {/* Recent Analyses */}
      {summary && summary.recent_runs.length > 0 && (
        <section>
          <div className="flex items-center justify-between mb-3">
            <h2 className="text-xs font-semibold text-stone-400 uppercase tracking-widest">{STRINGS.clientDashboard.recentAnalyses}</h2>
            <div className="flex items-center gap-2">
              {editMode && selected.size > 0 && (
                <button
                  onClick={() => setShowConfirm(true)}
                  className="text-xs font-semibold text-white bg-rose-600 hover:bg-rose-700 px-3 py-1.5 rounded-lg transition-colors"
                >
                  {STRINGS.clientDashboard.deleteSelected(selected.size)}
                </button>
              )}
              {deletableRunCount > 0 && (
                <button
                  onClick={toggleEditMode}
                  className="text-xs font-medium text-stone-500 hover:text-stone-700 transition-colors"
                >
                  {editMode ? STRINGS.clientDashboard.done : STRINGS.clientDashboard.edit}
                </button>
              )}
            </div>
          </div>

          {deleteError && (
            <div className="mb-2 text-xs text-rose-600 bg-rose-50 border border-rose-200 rounded-lg px-3 py-2">
              {deleteError}
            </div>
          )}

          {editMode && (
            <p className="text-xs text-stone-400 mb-2">
              {STRINGS.clientDashboard.editModeHelp}
            </p>
          )}

          <ul className="space-y-2">
            {summary.recent_runs.map((run: Record<string, unknown>, i: number) => {
              const runId = (run.run_id ?? run.id) as string;
              return (
                <li key={runId ?? i}>
                  <RecentRunCard
                    run={run}
                    editMode={editMode}
                    selected={selected.has(runId)}
                    onToggle={toggleSelect}
                  />
                </li>
              );
            })}
          </ul>
        </section>
      )}
    </div>
  );
}

function BaselineBadge({ status }: { status: string }) {
  const colorMap: Record<string, string> = {
    none:           'bg-stone-100 text-stone-500',
    intake:         'bg-blue-100 text-blue-700',
    building:       'bg-amber-100 text-amber-700',
    baseline_ready: 'bg-emerald-100 text-emerald-700',
    completed:      'bg-emerald-100 text-emerald-700',
    error:          'bg-rose-100 text-rose-700',
  };
  const color = colorMap[status] ?? colorMap.none;
  const label = STRINGS.baselineStatus[status] ?? STRINGS.baselineStatus.none;
  return <span className={`text-xs px-2 py-0.5 rounded-full font-semibold ${color}`}>{label}</span>;
}

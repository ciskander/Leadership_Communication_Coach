'use client';

import { useEffect, useState } from 'react';
import { useParams } from 'next/navigation';
import Link from 'next/link';
import { api } from '@/lib/api';
import type { BaselinePack, BaselinePackMeeting, CoachingItem, Experiment, ActiveExperiment, PatternSnapshotItem } from '@/lib/types';
import { CoachingCard } from '@/components/CoachingCard';
import { PatternSnapshot } from '@/components/PatternSnapshot';
import { ExperimentTracker } from '@/components/ExperimentTracker';

const POLL_TIMEOUT_MS = 5 * 60 * 1000;

// ── Helpers ───────────────────────────────────────────────────────────────────

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

function PatternLabel({ id }: { id: string }) {
  return (
    <span className="text-xs font-semibold text-stone-400 uppercase tracking-widest">
      {id.replace(/_/g, ' ')}
    </span>
  );
}

// ── Accepted Experiment Panel ─────────────────────────────────────────────────

function AcceptedExperimentPanel({ experiment }: { experiment: Experiment }) {
  return (
    <div className="bg-emerald-50 border border-emerald-200 rounded-2xl p-5 space-y-3">
      <div className="flex items-center gap-2">
        <span className="text-emerald-600">✦</span>
        <span className="text-sm font-semibold text-emerald-800">Experiment accepted</span>
      </div>
      <div className="space-y-1">
        <PatternLabel id={experiment.pattern_id} />
        <p className="text-sm font-semibold text-stone-900 leading-snug">{experiment.title}</p>
      </div>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
        <div className="bg-white rounded-xl p-3 border border-emerald-100">
          <p className="text-xs font-semibold text-stone-400 uppercase tracking-widest mb-1">What to do</p>
          <p className="text-xs text-stone-600 leading-relaxed">{experiment.instruction}</p>
        </div>
        <div className="bg-white rounded-xl p-3 border border-emerald-100">
          <p className="text-xs font-semibold text-stone-400 uppercase tracking-widest mb-1">Success looks like</p>
          <p className="text-xs text-stone-600 leading-relaxed">{experiment.success_marker}</p>
        </div>
      </div>
      <Link
        href="/client/experiment"
        className="inline-flex items-center text-sm text-emerald-700 font-medium hover:text-emerald-900 transition-colors"
      >
        Track progress on My Experiment →
      </Link>
    </div>
  );
}

// ── Proposed Experiment Card ──────────────────────────────────────────────────

function ProposedExperimentCard({
  experiment,
  onAccepted,
}: {
  experiment: Experiment;
  onAccepted: (exp: Experiment) => void;
}) {
  const [state, setState] = useState<'idle' | 'loading' | 'error'>('idle');
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  async function handleAccept() {
    if (state !== 'idle') return;
    setState('loading');
    setErrorMsg(null);
    try {
      await api.acceptExperiment(experiment.experiment_record_id);
      onAccepted(experiment);
    } catch (err: unknown) {
      setErrorMsg(err instanceof Error ? err.message : 'Something went wrong.');
      setState('error');
    }
  }

  return (
    <div className="bg-white rounded-2xl border border-stone-200 p-5 space-y-3">
      <div className="space-y-1">
        <PatternLabel id={experiment.pattern_id} />
        <p className="text-sm font-semibold text-stone-900 leading-snug">{experiment.title}</p>
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
      {errorMsg && <p className="text-xs text-rose-600">{errorMsg}</p>}
      <div className="flex items-center gap-3">
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
        <span className="text-xs text-stone-400 ml-auto">{experiment.experiment_id}</span>
      </div>
    </div>
  );
}

// ── Experiment Section ────────────────────────────────────────────────────────

function ExperimentSection() {
  const [proposed, setProposed] = useState<Experiment[]>([]);
  const [activeExpData, setActiveExpData] = useState<ActiveExperiment | null>(null);
  const [loading, setLoading] = useState(true);
  const [accepted, setAccepted] = useState<Experiment | null>(null);

  useEffect(() => {
    Promise.all([
      api.getProposedExperiments().catch(() => [] as Experiment[]),
      api.getActiveExperiment().catch(() => null),
    ]).then(([proposedResult, activeResult]) => {
      setProposed(proposedResult);
      setActiveExpData(activeResult);
    }).finally(() => setLoading(false));
  }, []);

  if (loading) {
    return (
      <div className="flex items-center gap-2 py-2">
        <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-stone-400 flex-shrink-0" />
        <span className="text-xs text-stone-400">Loading your experiment…</span>
      </div>
    );
  }

  if (accepted) {
    return <AcceptedExperimentPanel experiment={accepted} />;
  }

  if (proposed.length > 0) {
    return (
      <section className="space-y-3">
        <h2 className="text-xs font-semibold text-stone-400 uppercase tracking-widest">
          Your experiment is ready
        </h2>
        {proposed.map((exp) => (
          <ProposedExperimentCard
            key={exp.experiment_record_id}
            experiment={exp}
            onAccepted={(e) => setAccepted(e)}
          />
        ))}
      </section>
    );
  }

  if (activeExpData?.experiment) {
    return (
      <ExperimentTracker
        experiment={activeExpData.experiment}
        events={activeExpData.recent_events}
      />
    );
  }

  return null;
}

// ── Sub-run Pattern Snapshot ──────────────────────────────────────────────────

function SubRunPatternSnapshot({ patterns }: { patterns: Record<string, unknown>[] }) {
  return (
    <div className="mt-1">
      <p className="text-xs font-semibold text-stone-400 uppercase tracking-widest mb-2">
        Pattern scores
      </p>
      <div className="opacity-80">
        <PatternSnapshot patterns={patterns as unknown as PatternSnapshotItem[]} />
      </div>
    </div>
  );
}

// ── Meeting Accordion Card ────────────────────────────────────────────────────

function MeetingAccordionCard({
  meeting,
  index,
  open,
  onToggle,
}: {
  meeting: BaselinePackMeeting;
  index: number;
  open: boolean;
  onToggle: () => void;
}) {
  const title = meeting.title || 'Untitled meeting';
  const date = fmtDate(meeting.meeting_date);
  const role = meeting.target_role ? (ROLE_LABELS[meeting.target_role] ?? meeting.target_role) : null;
  const meta = [date, meeting.meeting_type, role].filter(Boolean).join(' · ');

  const hasSubRunData = !!(
    meeting.sub_run_strengths?.length ||
    meeting.sub_run_focus ||
    meeting.sub_run_pattern_snapshot?.length
  );

  return (
    <div className={`bg-white border rounded-xl overflow-hidden transition-all ${open ? 'border-stone-300 shadow-sm' : 'border-stone-200'}`}>
      {/* Header */}
      <button
        onClick={onToggle}
        className="w-full flex items-start justify-between gap-3 px-4 py-3 text-left hover:bg-stone-50 transition-colors"
      >
        <div className="flex items-start gap-3 min-w-0">
          <div className="w-6 h-6 rounded-full bg-stone-100 text-stone-500 flex items-center justify-center text-xs font-bold flex-shrink-0 mt-0.5">
            {index + 1}
          </div>
          <div className="min-w-0">
            <p className="text-sm font-semibold text-stone-800 truncate">{title}</p>
            {meta && <p className="text-xs text-stone-400 mt-0.5">{meta}</p>}
          </div>
        </div>
        <span className="text-stone-400 flex-shrink-0 mt-0.5 text-xs font-medium">
          {open ? '▲ Collapse' : '▼ Expand'}
        </span>
      </button>

      {/* Expanded content */}
      {open && (
        <div className="border-t border-stone-100 px-4 pb-5 pt-4 space-y-5">
          {meeting.run_id && hasSubRunData ? (
            <>
              {(meeting.sub_run_strengths?.length || meeting.sub_run_focus) && (
                <div>
                  <p className="text-xs font-semibold text-stone-400 uppercase tracking-widest mb-3">
                    Coaching output
                  </p>
                  <CoachingCard
                    strengths={(meeting.sub_run_strengths ?? []) as CoachingItem[]}
                    focus={(meeting.sub_run_focus ?? null) as CoachingItem | null}
                    microExperiment={null}
                  />
                </div>
              )}
              {meeting.sub_run_pattern_snapshot && meeting.sub_run_pattern_snapshot.length > 0 && (
                <SubRunPatternSnapshot patterns={meeting.sub_run_pattern_snapshot} />
              )}
            </>
          ) : (
            <p className="text-xs text-stone-400">
              {meeting.run_id
                ? 'Analysis data is not available for this meeting.'
                : 'This meeting has not been analysed yet.'}
            </p>
          )}
        </div>
      )}
    </div>
  );
}

// ── Page ──────────────────────────────────────────────────────────────────────

export default function BaselineDetailPage() {
  const { id } = useParams<{ id: string }>();
  const [pack, setPack] = useState<BaselinePack | null>(null);
  const [loading, setLoading] = useState(true);
  const [timedOut, setTimedOut] = useState(false);
  const [pollStart] = useState(() => Date.now());
  const [openMeeting, setOpenMeeting] = useState<number | null>(null);

  const fetchPack = () => {
    api.getBaselinePack(id).then(setPack).finally(() => setLoading(false));
  };

  useEffect(() => {
    fetchPack();
  }, [id]);

  useEffect(() => {
    if (pack && (pack.status === 'draft' || pack.status === 'building' || pack.status === 'intake')) {
      if (Date.now() - pollStart > POLL_TIMEOUT_MS) {
        setTimedOut(true);
        return;
      }
      const t = setTimeout(fetchPack, 5000);
      return () => clearTimeout(t);
    }
  }, [pack]);

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-emerald-600" />
      </div>
    );
  }

  if (!pack) {
    return (
      <div className="max-w-xl mx-auto py-12 text-center">
        <p className="text-sm text-stone-500">Baseline pack not found.</p>
      </div>
    );
  }

  const isBuilding = pack.status === 'draft' || pack.status === 'building' || pack.status === 'intake';
  const isReady = pack.status === 'baseline_ready' || pack.status === 'completed';
  const isError = pack.status === 'error' || timedOut;
  const meetings = pack.meetings ?? [];

  return (
    <div className="max-w-2xl mx-auto space-y-6 py-2">

      {/* Header */}
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold text-stone-900">Baseline Pack</h1>
        <Link
          href="/client"
          className="text-sm text-stone-500 hover:text-stone-700 transition-colors"
        >
          ← Dashboard
        </Link>
      </div>

      {/* Building state */}
      {isBuilding && !timedOut && (
        <div className="bg-white rounded-2xl border border-blue-200 p-8 text-center space-y-4">
          <div className="relative mx-auto w-14 h-14">
            <div className="w-14 h-14 rounded-full border-2 border-stone-100" />
            <div className="absolute inset-0 w-14 h-14 rounded-full border-2 border-blue-500 border-t-transparent animate-spin" />
          </div>
          <div>
            <p className="text-sm font-semibold text-stone-800">Building your baseline…</p>
            <p className="text-xs text-stone-400 mt-1">This usually takes 2–5 minutes. This page will update automatically.</p>
          </div>
        </div>
      )}

      {/* Error state */}
      {isError && (
        <div className="bg-white rounded-2xl border border-rose-200 p-6 space-y-3">
          <p className="text-sm font-semibold text-rose-700">
            {timedOut ? 'Build is taking longer than expected' : 'Baseline build failed'}
          </p>
          <p className="text-sm text-stone-500">
            {timedOut
              ? 'The analysis is still running in the background. Check back in a few minutes, or try creating a new baseline pack.'
              : 'Something went wrong during analysis. Please try creating a new baseline pack.'}
          </p>
          <div className="flex gap-2">
            {timedOut && (
              <button
                onClick={() => { setTimedOut(false); fetchPack(); }}
                className="inline-block text-sm px-4 py-2 bg-stone-100 text-stone-700 rounded-xl font-medium hover:bg-stone-200 transition-colors"
              >
                Check again
              </button>
            )}
            <Link
              href="/client/baseline/new"
              className="inline-block text-sm px-4 py-2 bg-emerald-600 text-white rounded-xl font-medium hover:bg-emerald-700 transition-colors"
            >
              Try again
            </Link>
          </div>
        </div>
      )}

      {/* Ready state */}
      {isReady && (
        <>
          {/* Success banner */}
          <div className="bg-emerald-50 border border-emerald-200 rounded-2xl px-5 py-3.5 flex items-center gap-3">
            <span className="text-emerald-600 text-lg">✦</span>
            <div>
              <p className="text-sm font-semibold text-emerald-800">Baseline complete</p>
              <p className="text-xs text-emerald-600">Your communication patterns have been mapped across 3 meetings</p>
            </div>
          </div>

          {/* Aggregate coaching output — micro_experiment suppressed */}
          <CoachingCard
            strengths={pack.strengths ?? []}
            focus={pack.focus ?? null}
            microExperiment={null}
          />

          {/* Experiment section */}
          <ExperimentSection />

          {/* Aggregate pattern snapshot */}
          {pack.pattern_snapshot && pack.pattern_snapshot.length > 0 && (
            <section>
              <h2 className="text-xs font-semibold text-stone-400 uppercase tracking-widest mb-3">
                Your communication baseline
              </h2>
              <PatternSnapshot patterns={pack.pattern_snapshot as unknown as PatternSnapshotItem[]} />
            </section>
          )}

          {/* Constituent meetings as accordions */}
          {meetings.length > 0 && (
            <section>
              <h2 className="text-xs font-semibold text-stone-400 uppercase tracking-widest mb-3">
                Meetings in this baseline
              </h2>
              <div className="space-y-2">
                {meetings.map((meeting, i) => (
                  <MeetingAccordionCard
                    key={meeting.run_id ?? i}
                    meeting={meeting}
                    index={i}
                    open={openMeeting === i}
                    onToggle={() => setOpenMeeting(openMeeting === i ? null : i)}
                  />
                ))}
              </div>
            </section>
          )}

          {/* Bottom CTA */}
          <div>
            <Link
              href="/client/analyze"
              className="inline-block px-5 py-3 bg-blue-600 text-white rounded-xl text-sm font-medium hover:bg-blue-700 transition-colors"
            >
              ✨ Analyze Meeting
            </Link>
          </div>
        </>
      )}
    </div>
  );
}

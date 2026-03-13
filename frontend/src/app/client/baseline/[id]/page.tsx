'use client';

import { useEffect, useState } from 'react';
import { useParams } from 'next/navigation';
import Link from 'next/link';
import { api } from '@/lib/api';
import type {
  BaselinePack,
  BaselinePackMeeting,
  CoachingItem,
  Experiment,
  ActiveExperiment,
  PatternSnapshotItem,
} from '@/lib/types';
import { CoachingCard } from '@/components/CoachingCard';
import { PatternSnapshot } from '@/components/PatternSnapshot';
import { ExperimentTracker } from '@/components/ExperimentTracker';
import { STRINGS } from '@/config/strings';

// ─── Constants ────────────────────────────────────────────────────────────────

const POLL_TIMEOUT_MS = 5 * 60 * 1000;
const ROLE_LABELS = STRINGS.roles;

// ─── Helpers ──────────────────────────────────────────────────────────────────

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
    <span className="text-2xs font-medium text-cv-stone-400 uppercase tracking-widest">
      {id.replace(/_/g, ' ')}
    </span>
  );
}

// ─── Accepted Experiment Panel ────────────────────────────────────────────────

function AcceptedExperimentPanel({ experiment }: { experiment: Experiment }) {
  return (
    <div className="bg-cv-teal-50 border border-cv-teal-100 rounded-xl p-5 space-y-4">
      <div className="flex items-center gap-2">
        <div className="w-1.5 h-4 rounded-full bg-cv-teal-400 flex-shrink-0" />
        <span className="text-sm font-medium text-cv-teal-800">
          {STRINGS.baselineDetail.experimentAccepted}
        </span>
      </div>
      <div className="space-y-1">
        <PatternLabel id={experiment.pattern_id} />
        <p className="text-sm font-medium text-cv-stone-900 leading-snug mt-1">
          {experiment.title}
        </p>
      </div>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
        <div className="bg-white rounded-lg p-3 border border-cv-teal-100">
          <p className="text-2xs font-medium text-cv-stone-400 uppercase tracking-widest mb-1.5">
            {STRINGS.common.whatToDo}
          </p>
          <p className="text-xs text-cv-stone-600 font-light leading-relaxed">
            {experiment.instruction}
          </p>
        </div>
        <div className="bg-white rounded-lg p-3 border border-cv-teal-100">
          <p className="text-2xs font-medium text-cv-stone-400 uppercase tracking-widest mb-1.5">
            {STRINGS.common.successLooksLike}
          </p>
          <p className="text-xs text-cv-stone-600 font-light leading-relaxed">
            {experiment.success_marker}
          </p>
        </div>
      </div>
      <Link
        href="/client/experiment"
        className="inline-flex items-center text-sm text-cv-teal-600 font-medium hover:text-cv-teal-800 transition-colors"
      >
        {STRINGS.baselineDetail.trackExperiment} →
      </Link>
    </div>
  );
}

// ─── Proposed Experiment Card ─────────────────────────────────────────────────

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
    <div className="bg-white rounded-xl border border-cv-warm-200 p-5 space-y-4">
      <div className="space-y-1">
        <PatternLabel id={experiment.pattern_id} />
        <p className="text-sm font-medium text-cv-stone-900 leading-snug mt-1">
          {experiment.title}
        </p>
      </div>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
        <div className="bg-cv-warm-100 rounded-lg p-3">
          <p className="text-2xs font-medium text-cv-stone-400 uppercase tracking-widest mb-1.5">
            {STRINGS.common.whatToDo}
          </p>
          <p className="text-xs text-cv-stone-600 font-light leading-relaxed">
            {experiment.instruction}
          </p>
        </div>
        <div className="bg-cv-warm-100 rounded-lg p-3">
          <p className="text-2xs font-medium text-cv-stone-400 uppercase tracking-widest mb-1.5">
            {STRINGS.common.successLooksLike}
          </p>
          <p className="text-xs text-cv-stone-600 font-light leading-relaxed">
            {experiment.success_marker}
          </p>
        </div>
      </div>
      {errorMsg && (
        <p className="text-xs text-cv-red-600">{errorMsg}</p>
      )}
      <div className="flex items-center gap-3">
        <button
          onClick={handleAccept}
          disabled={state === 'loading'}
          className="px-4 py-2 bg-cv-teal-600 text-cv-teal-50 rounded-lg text-xs font-medium hover:bg-cv-teal-800 transition-colors disabled:opacity-50"
        >
          {state === 'loading' ? STRINGS.common.accepting : STRINGS.common.acceptExperiment}
        </button>
        <Link
          href="/client/experiment?expand=1"
          className="text-xs text-cv-stone-400 hover:text-cv-stone-600 transition-colors"
        >
          {STRINGS.experimentPage.seeMoreOptions}
        </Link>
        <span className="text-2xs text-cv-stone-400 ml-auto tracking-wide">
          {experiment.experiment_id}
        </span>
      </div>
    </div>
  );
}

// ─── Experiment Section ───────────────────────────────────────────────────────

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
      <div className="flex items-center gap-2.5 py-2">
        <div className="w-4 h-4 border-2 border-cv-teal-600 border-t-transparent rounded-full animate-spin flex-shrink-0" />
        <span className="text-xs text-cv-stone-400 font-light">
          {STRINGS.baselineDetail.loadingExperiment}
        </span>
      </div>
    );
  }

  if (accepted) {
    return <AcceptedExperimentPanel experiment={accepted} />;
  }

  if (proposed.length > 0) {
    return (
      <section className="space-y-3">
        <p className="text-2xs font-medium text-cv-stone-400 uppercase tracking-widest">
          {STRINGS.baselineDetail.experimentReady}
        </p>
        <ProposedExperimentCard
          experiment={proposed[0]}
          onAccepted={(e) => setAccepted(e)}
        />
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

// ─── Sub-run Pattern Snapshot ─────────────────────────────────────────────────

function SubRunPatternSnapshot({ patterns }: { patterns: Record<string, unknown>[] }) {
  return (
    <div className="mt-1">
      <p className="text-2xs font-medium text-cv-stone-400 uppercase tracking-widest mb-3">
        {STRINGS.baselineDetail.patternScores}
      </p>
      <div className="opacity-90">
        <PatternSnapshot patterns={patterns as unknown as PatternSnapshotItem[]} />
      </div>
    </div>
  );
}

// ─── Meeting Accordion Card ───────────────────────────────────────────────────

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
  const role = meeting.target_role
    ? (ROLE_LABELS[meeting.target_role] ?? meeting.target_role)
    : null;
  const meta = [date, meeting.meeting_type, role].filter(Boolean).join(' · ');

  const hasSubRunData = !!(
    meeting.sub_run_strengths?.length ||
    meeting.sub_run_focus ||
    meeting.sub_run_pattern_snapshot?.length
  );

  return (
    <div className={`bg-white border rounded-xl overflow-hidden transition-colors ${
      open ? 'border-cv-stone-100' : 'border-cv-warm-200'
    }`}>
      {/* Header */}
      <button
        onClick={onToggle}
        className="w-full flex items-start justify-between gap-3 px-5 py-4 text-left hover:bg-cv-warm-100 transition-colors"
      >
        <div className="flex items-start gap-3 min-w-0">
          <div className="w-6 h-6 rounded-full bg-cv-warm-200 text-cv-stone-600 flex items-center justify-center text-2xs font-semibold flex-shrink-0 mt-0.5">
            {index + 1}
          </div>
          <div className="min-w-0">
            <p className="text-sm font-medium text-cv-stone-900 truncate">{title}</p>
            {meta && (
              <p className="text-xs text-cv-stone-400 font-light mt-0.5">{meta}</p>
            )}
          </div>
        </div>
        <svg
          viewBox="0 0 16 16"
          fill="none"
          className={`w-4 h-4 text-cv-stone-400 flex-shrink-0 mt-0.5 transition-transform duration-200 ${open ? 'rotate-180' : ''}`}
          aria-hidden="true"
        >
          <path d="M4 6l4 4 4-4" stroke="currentColor" strokeWidth={1.5} strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      </button>

      {/* Expanded content */}
      {open && (
        <div className="border-t border-cv-warm-200 px-5 pb-6 pt-5 space-y-6">
          {meeting.run_id && hasSubRunData ? (
            <>
              {(meeting.sub_run_strengths?.length || meeting.sub_run_focus) && (
                <div>
                  <p className="text-2xs font-medium text-cv-stone-400 uppercase tracking-widest mb-4">
                    {STRINGS.baselineDetail.coachingOutput}
                  </p>
                  <CoachingCard
                    strengths={(meeting.sub_run_strengths ?? []) as CoachingItem[]}
                    focus={(meeting.sub_run_focus ?? null) as CoachingItem | null}
                    microExperiment={null}
                  />
                </div>
              )}
              {meeting.sub_run_pattern_snapshot &&
                meeting.sub_run_pattern_snapshot.length > 0 && (
                  <SubRunPatternSnapshot patterns={meeting.sub_run_pattern_snapshot} />
                )}
            </>
          ) : (
            <p className="text-xs text-cv-stone-400 font-light">
              {meeting.run_id
                ? STRINGS.baselineDetail.noAnalysisData
                : STRINGS.baselineDetail.notAnalysedYet}
            </p>
          )}
        </div>
      )}
    </div>
  );
}

// ─── Page ─────────────────────────────────────────────────────────────────────

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

  // ── Loading ────────────────────────────────────────────────────────────────

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="w-6 h-6 border-2 border-cv-teal-600 border-t-transparent rounded-full animate-spin" />
      </div>
    );
  }

  // ── Not found ──────────────────────────────────────────────────────────────

  if (!pack) {
    return (
      <div className="max-w-xl mx-auto py-12 text-center">
        <p className="text-sm text-cv-stone-400 font-light">{STRINGS.baselineDetail.notFound}</p>
      </div>
    );
  }

  const isBuilding = pack.status === 'draft' || pack.status === 'building' || pack.status === 'intake';
  const isReady = pack.status === 'baseline_ready' || pack.status === 'completed';
  const isError = pack.status === 'error' || timedOut;
  const meetings = pack.meetings ?? [];

  return (
    <div className="max-w-2xl mx-auto space-y-6 py-2">

      {/* Page header */}
      <div className="flex items-center justify-between">
        <h1 className="font-serif text-2xl text-cv-stone-900">
          {STRINGS.baselineDetail.heading}
        </h1>
        <Link
          href="/client"
          className="text-xs text-cv-stone-400 tracking-widest uppercase hover:text-cv-stone-600 transition-colors"
        >
          ← {STRINGS.nav.dashboard}
        </Link>
      </div>

      {/* ── Building state ─────────────────────────────────────────────────── */}
      {isBuilding && !timedOut && (
        <div className="bg-white rounded-xl border border-cv-warm-200 p-10 text-center space-y-5">
          <div className="relative mx-auto w-12 h-12">
            <div className="w-12 h-12 rounded-full border-2 border-cv-stone-100" />
            <div className="absolute inset-0 w-12 h-12 rounded-full border-2 border-cv-teal-600 border-t-transparent animate-spin" />
          </div>
          <div>
            <p className="text-sm font-medium text-cv-stone-900">
              {STRINGS.baselineDetail.buildingTitle}
            </p>
            <p className="text-xs text-cv-stone-400 font-light mt-1">
              {STRINGS.baselineDetail.buildingDesc}
            </p>
          </div>
        </div>
      )}

      {/* ── Error state ────────────────────────────────────────────────────── */}
      {isError && (
        <div className="bg-white rounded-xl border border-cv-red-100 p-6 space-y-4">
          <p className="text-sm font-medium text-cv-red-600">
            {timedOut ? STRINGS.baselineDetail.timeoutTitle : STRINGS.baselineDetail.errorTitle}
          </p>
          <p className="text-sm text-cv-stone-400 font-light">
            {timedOut ? STRINGS.baselineDetail.timeoutDesc : STRINGS.baselineDetail.errorDesc}
          </p>
          <div className="flex gap-2">
            {timedOut && (
              <button
                onClick={() => { setTimedOut(false); fetchPack(); }}
                className="text-sm px-4 py-2 bg-cv-warm-100 text-cv-stone-600 rounded-lg font-medium hover:bg-cv-warm-200 transition-colors"
              >
                {STRINGS.runStatusPoller.checkAgain}
              </button>
            )}
            <Link
              href="/client/baseline/new"
              className="text-sm px-4 py-2 bg-cv-teal-600 text-cv-teal-50 rounded-lg font-medium hover:bg-cv-teal-800 transition-colors"
            >
              {STRINGS.baselineDetail.tryAgain}
            </Link>
          </div>
        </div>
      )}

      {/* ── Ready state ────────────────────────────────────────────────────── */}
      {isReady && (
        <>
          {/* Success banner */}
          <div className="bg-cv-teal-50 border border-cv-teal-100 rounded-xl px-5 py-4 flex items-center gap-3">
            <div className="w-1.5 h-8 rounded-full bg-cv-teal-400 flex-shrink-0" />
            <div>
              <p className="text-sm font-medium text-cv-teal-800">
                {STRINGS.baselineDetail.completeTitle}
              </p>
              <p className="text-sm text-cv-teal-400 font-light mt-0.5">
                {STRINGS.baselineDetail.completeSubtitle}
              </p>
            </div>
          </div>

          {/* Aggregate coaching — micro_experiment suppressed at baseline */}
          {/* NOTE: CoachingCard needs its own design pass — see implementation notes */}
          <CoachingCard
            strengths={pack.strengths ?? []}
            focus={pack.focus ?? null}
            microExperiment={null}
          />

          {/* Hint to check individual meeting sections */}
          {meetings.length > 0 && (
            <div className="bg-blue-50 border border-blue-100 rounded-xl px-4 py-3 flex items-start gap-2.5">
              <svg viewBox="0 0 16 16" fill="none" className="w-4 h-4 text-blue-500 shrink-0 mt-0.5" aria-hidden="true">
                <circle cx="8" cy="8" r="6.5" stroke="currentColor" strokeWidth={1.4} />
                <path d="M8 7v4.5" stroke="currentColor" strokeWidth={1.6} strokeLinecap="round" />
                <circle cx="8" cy="4.5" r="0.75" fill="currentColor" />
              </svg>
              <p className="text-sm text-blue-800 leading-relaxed">
                {STRINGS.baselineDetail.aggregateCoachingNote}
              </p>
            </div>
          )}

          {/* Experiment section */}
          <ExperimentSection />

          {/* Aggregate pattern snapshot */}
          {pack.pattern_snapshot && pack.pattern_snapshot.length > 0 && (
            <section>
              <p className="text-2xs font-medium text-cv-stone-400 uppercase tracking-widest mb-4">
                {STRINGS.baselineDetail.yourBaseline}
              </p>
              {/* NOTE: PatternSnapshot needs its own design pass — see implementation notes */}
              <PatternSnapshot patterns={pack.pattern_snapshot as unknown as PatternSnapshotItem[]} />
            </section>
          )}

          {/* Individual meetings as accordions */}
          {meetings.length > 0 && (
            <section>
              <p className="text-2xs font-medium text-cv-stone-400 uppercase tracking-widest mb-4">
                {STRINGS.baselineDetail.meetingsInBaseline}
              </p>
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
          <div className="pb-4">
            <Link
              href="/client/analyze"
              className="inline-flex items-center gap-2 px-5 py-3 bg-cv-teal-600 text-cv-teal-50 rounded-lg text-sm font-medium hover:bg-cv-teal-800 transition-colors"
            >
              {STRINGS.experimentTracker.analyzeMeeting}
            </Link>
          </div>
        </>
      )}
    </div>
  );
}

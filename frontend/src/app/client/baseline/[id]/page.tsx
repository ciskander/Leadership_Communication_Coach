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

const POLL_TIMEOUT_MS = 15 * 60 * 1000;
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
    <div className="bg-cv-teal-50 border border-cv-teal-100 rounded p-5 space-y-4">
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
        <div className="bg-white rounded p-3 border border-cv-teal-100">
          <p className="text-2xs font-medium text-cv-stone-400 uppercase tracking-widest mb-1.5">
            {STRINGS.common.whatToDo}
          </p>
          <p className="text-xs text-cv-stone-600 font-light leading-relaxed">
            {experiment.instruction}
          </p>
        </div>
        <div className="bg-white rounded p-3 border border-cv-teal-100">
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
    <div className="bg-white rounded border border-cv-warm-300 p-5 space-y-4">
      <div className="space-y-1">
        <PatternLabel id={experiment.pattern_id} />
        <p className="text-sm font-medium text-cv-stone-900 leading-snug mt-1">
          {experiment.title}
        </p>
      </div>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
        <div className="bg-cv-warm-100 rounded p-3">
          <p className="text-2xs font-medium text-cv-stone-400 uppercase tracking-widest mb-1.5">
            {STRINGS.common.whatToDo}
          </p>
          <p className="text-xs text-cv-stone-600 font-light leading-relaxed">
            {experiment.instruction}
          </p>
        </div>
        <div className="bg-cv-warm-100 rounded p-3">
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
          className="px-4 py-2 bg-cv-teal-600 text-cv-teal-50 rounded text-xs font-medium hover:bg-cv-teal-800 transition-colors disabled:opacity-50"
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

function SubRunPatternSnapshot({ patterns, targetSpeaker, excludePatternIds }: { patterns: Record<string, unknown>[]; targetSpeaker?: string | null; excludePatternIds?: string[] }) {
  return (
    <div className="mt-1">
      <p className="text-2xs font-medium text-cv-stone-400 uppercase tracking-widest mb-3">
        {STRINGS.baselineDetail.otherPatterns}
      </p>
      <div className="opacity-90">
        <PatternSnapshot patterns={patterns as unknown as PatternSnapshotItem[]} targetSpeaker={targetSpeaker} excludePatternIds={excludePatternIds} />
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
  targetSpeaker,
}: {
  meeting: BaselinePackMeeting;
  index: number;
  open: boolean;
  onToggle: () => void;
  targetSpeaker?: string | null;
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
    <div className={`bg-white border rounded overflow-hidden transition-colors ${
      open ? 'border-cv-stone-100' : 'border-cv-warm-300'
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
        <div className="border-t border-cv-warm-300 px-5 pb-6 pt-5 space-y-6">
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
                    targetSpeaker={targetSpeaker}
                    patternSnapshot={meeting.sub_run_pattern_snapshot as unknown as PatternSnapshotItem[]}
                  />
                </div>
              )}
              {meeting.sub_run_pattern_snapshot &&
                meeting.sub_run_pattern_snapshot.length > 0 && (() => {
                  const subUsedIds = [
                    ...((meeting.sub_run_strengths ?? []) as CoachingItem[]).map((s) => s.pattern_id),
                    ...((meeting.sub_run_focus as CoachingItem | null)?.pattern_id ? [(meeting.sub_run_focus as CoachingItem).pattern_id] : []),
                  ];
                  return (
                    <SubRunPatternSnapshot
                      patterns={meeting.sub_run_pattern_snapshot}
                      targetSpeaker={targetSpeaker}
                      excludePatternIds={subUsedIds}
                    />
                  );
                })()}
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
  const meetings = [...(pack.meetings ?? [])].sort((a, b) => {
    if (!a.meeting_date && !b.meeting_date) return 0;
    if (!a.meeting_date) return 1;
    if (!b.meeting_date) return -1;
    return new Date(a.meeting_date).getTime() - new Date(b.meeting_date).getTime();
  });

  return (
    <div className="max-w-5xl mx-auto space-y-6 py-2">

      {/* Page header */}
      <div className="flex items-center justify-between">
        <h1 className="font-serif text-2xl text-cv-stone-900">
          {STRINGS.baselineDetail.heading}
        </h1>
        <Link
          href="/client"
          className="text-sm text-cv-stone-400 hover:text-cv-stone-700 transition-colors shrink-0"
        >
          {STRINGS.nav.dashboard}
        </Link>
      </div>

      {/* ── Building state ─────────────────────────────────────────────────── */}
      {isBuilding && !timedOut && (
        <div className="bg-white rounded border border-cv-warm-300 p-10 text-center space-y-5">
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
        <div className="bg-white rounded border border-cv-red-100 p-6 space-y-4">
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
                className="text-sm px-4 py-2 bg-cv-warm-100 text-cv-stone-600 rounded font-medium hover:bg-cv-warm-200 transition-colors"
              >
                {STRINGS.runStatusPoller.checkAgain}
              </button>
            )}
            <Link
              href="/client/baseline/new"
              className="text-sm px-4 py-2 bg-cv-teal-600 text-cv-teal-50 rounded font-medium hover:bg-cv-teal-800 transition-colors"
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
          <div className="bg-cv-teal-50 border border-cv-teal-700 rounded px-5 py-4 flex items-center gap-3">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.7} strokeLinecap="round" strokeLinejoin="round" className="w-5 h-5 shrink-0 text-cv-teal-700" aria-hidden="true">
              <path d="M12 2L3 7L12 12L21 7L12 2Z" />
              <path d="M3 12L12 17L21 12" />
              <path d="M3 17L12 22L21 17" />
            </svg>
            <div>
              <p className="text-sm font-semibold text-cv-teal-800">
                {STRINGS.baselineDetail.completeTitle}
              </p>
              <p className="text-sm text-cv-teal-400 font-light mt-0.5">
                {STRINGS.baselineDetail.completeSubtitle}
              </p>
            </div>
          </div>

          {/* Executive summary */}
          {pack.executive_summary && (
            <section className="bg-white rounded border border-cv-stone-500 overflow-hidden">
              <div className="flex items-center gap-2.5 px-5 py-3.5 border-b border-cv-warm-300 bg-cv-stone-500">
                <svg viewBox="0 0 20 20" fill="currentColor" className="w-4 h-4 text-cv-stone-50 shrink-0" aria-hidden="true">
                  <path fillRule="evenodd" d="M4.5 2A1.5 1.5 0 003 3.5v13A1.5 1.5 0 004.5 18h11a1.5 1.5 0 001.5-1.5V7.621a1.5 1.5 0 00-.44-1.06l-4.12-4.122A1.5 1.5 0 0011.378 2H4.5zm2.25 8.5a.75.75 0 000 1.5h6.5a.75.75 0 000-1.5h-6.5zm0 3a.75.75 0 000 1.5h6.5a.75.75 0 000-1.5h-6.5z" clipRule="evenodd" />
                </svg>
                <h3 className="text-sm font-semibold text-cv-stone-50">{STRINGS.runStatusPoller.summaryHeading}</h3>
              </div>
              <div className="px-5 py-4">
                <p className="text-sm text-cv-stone-700 leading-relaxed">{pack.executive_summary}</p>
              </div>
            </section>
          )}

          {/* Aggregate coaching — micro_experiment suppressed at baseline */}
          <CoachingCard
            strengths={pack.strengths ?? []}
            focus={pack.focus ?? null}
            microExperiment={null}
            targetSpeaker={pack.target_speaker_label}
            patternSnapshot={pack.pattern_snapshot as unknown as PatternSnapshotItem[]}
          />

          {/* Hint to check individual meeting sections */}
          {meetings.length > 0 && (
            <div className="bg-cv-blue-50 border border-cv-blue-100 rounded px-4 py-3 flex items-start gap-2.5">
              <svg viewBox="0 0 16 16" fill="none" className="w-4 h-4 text-cv-navy-600 shrink-0 mt-0.5" aria-hidden="true">
                <circle cx="8" cy="8" r="6.5" stroke="currentColor" strokeWidth={1.4} />
                <path d="M8 7v4.5" stroke="currentColor" strokeWidth={1.6} strokeLinecap="round" />
                <circle cx="8" cy="4.5" r="0.75" fill="currentColor" />
              </svg>
              <p className="text-sm text-cv-navy-600 leading-relaxed">
                {STRINGS.baselineDetail.aggregateCoachingNote}
              </p>
            </div>
          )}

          {/* Experiment section */}
          <section className="bg-white rounded border border-cv-rose-700 overflow-hidden">
            <div className="flex items-center gap-2.5 px-5 py-3.5 border-b border-cv-warm-300 bg-cv-rose-700">
              <svg viewBox="0 0 20 20" fill="currentColor" className="w-4 h-4 text-cv-rose-50 shrink-0" aria-hidden="true">
                <path fillRule="evenodd" d="M8.5 3.528v4.644c0 .479-.239.927-.644 1.190L6.24 10.484A3.501 3.501 0 008 17h4a3.5 3.5 0 001.76-6.516l-1.616-1.122A1.419 1.419 0 0011.5 8.172V3.528a16.989 16.989 0 00-3 0z" clipRule="evenodd" />
              </svg>
              <h3 className="text-sm font-semibold text-cv-rose-50">{STRINGS.runStatusPoller.experimentSectionHeading}</h3>
            </div>
            <div className="px-5 py-4">
              <ExperimentSection />
            </div>
          </section>

          {/* Aggregate pattern snapshot — grouped by cluster */}
          {pack.pattern_snapshot && pack.pattern_snapshot.length > 0 && (
            <section className="bg-white rounded border border-cv-blue-700 overflow-hidden">
              <div className="flex items-center gap-2.5 px-5 py-3.5 border-b border-cv-warm-300 bg-cv-blue-700">
                <svg viewBox="0 0 20 20" fill="currentColor" className="w-4 h-4 text-cv-blue-50 shrink-0" aria-hidden="true">
                  <path fillRule="evenodd" d="M6 3a2 2 0 00-2 2v1.161l-.33.275a2 2 0 00-.67 1.49V16a2 2 0 002 2h10a2 2 0 002-2V7.926a2 2 0 00-.67-1.49L16 6.161V5a2 2 0 00-2-2H6zm8 3.21V5H6v1.21l-1 .834V16h10V7.044l-1-.834zM9 9a1 1 0 011-1h.01a1 1 0 110 2H10a1 1 0 01-1-1zm0 4a1 1 0 011-1h.01a1 1 0 110 2H10a1 1 0 01-1-1z" clipRule="evenodd" />
                </svg>
                <h3 className="text-sm font-semibold text-cv-blue-50">{STRINGS.runStatusPoller.patternSnapshot}</h3>
              </div>
              <div className="px-5 py-4">
                <PatternSnapshot
                  patterns={pack.pattern_snapshot as unknown as PatternSnapshotItem[]}
                  targetSpeaker={pack.target_speaker_label}
                  groupByCluster
                  strengthPatternIds={(pack.strengths ?? []).map((s: CoachingItem) => s.pattern_id)}
                  focusPatternId={pack.focus?.pattern_id ?? null}
                />
              </div>
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
                    targetSpeaker={pack.target_speaker_label}
                  />
                ))}
              </div>
            </section>
          )}

          {/* Bottom CTA */}
          <div className="pb-4">
            <Link
              href="/client/analyze"
              className="inline-flex items-center gap-2 px-5 py-3 bg-cv-navy-600 text-white rounded text-sm font-medium hover:bg-cv-navy-700 transition-colors"
            >
              <svg viewBox="0 0 24 24" fill="none" className="w-4 h-4 shrink-0" aria-hidden="true"><path d="M9 3L10.5 7.5L15 9L10.5 10.5L9 15L7.5 10.5L3 9L7.5 7.5L9 3Z" stroke="currentColor" strokeWidth={1.7} strokeLinecap="round" strokeLinejoin="round"/><path d="M19 13L19.75 15.25L22 16L19.75 16.75L19 19L18.25 16.75L16 16L18.25 15.25L19 13Z" stroke="currentColor" strokeWidth={1.7} strokeLinecap="round" strokeLinejoin="round"/></svg>
              {STRINGS.experimentTracker.analyzeMeeting}
            </Link>
          </div>
        </>
      )}
    </div>
  );
}

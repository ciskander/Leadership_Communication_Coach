'use client';

import { useEffect, useState } from 'react';
import { useParams } from 'next/navigation';
import Link from 'next/link';
import { api } from '@/lib/api';
import type { BaselinePack, BaselinePackMeeting } from '@/lib/types';
import { CoachingCard } from '@/components/CoachingCard';

const POLL_TIMEOUT_MS = 5 * 60 * 1000; // 5 minutes

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

// ── Meeting card ──────────────────────────────────────────────────────────────

function MeetingCard({ meeting, index }: { meeting: BaselinePackMeeting; index: number }) {
  const title = meeting.title || 'Untitled meeting';
  const date = fmtDate(meeting.meeting_date);
  const role = meeting.target_role ? (ROLE_LABELS[meeting.target_role] ?? meeting.target_role) : null;

  const meta = [date, meeting.meeting_type, role].filter(Boolean).join(' · ');

  const inner = (
    <div className="flex items-start justify-between gap-3">
      <div className="flex items-start gap-3 min-w-0">
        <div className="w-6 h-6 rounded-full bg-stone-100 text-stone-500 flex items-center justify-center text-xs font-bold flex-shrink-0 mt-0.5">
          {index + 1}
        </div>
        <div className="min-w-0">
          <p className="text-sm font-semibold text-stone-800 truncate">{title}</p>
          {meta && <p className="text-xs text-stone-400 mt-0.5">{meta}</p>}
        </div>
      </div>
      {meeting.run_id && (
        <span className="text-xs text-emerald-700 font-medium flex-shrink-0 mt-0.5">
          View analysis →
        </span>
      )}
    </div>
  );

  if (meeting.run_id) {
    return (
      <Link
        href={`/client/runs/${meeting.run_id}`}
        className="block bg-white border border-stone-200 rounded-xl px-4 py-3 hover:border-emerald-300 hover:shadow-sm transition-all"
      >
        {inner}
      </Link>
    );
  }

  return (
    <div className="bg-white border border-stone-200 rounded-xl px-4 py-3 opacity-60">
      {inner}
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

          {/* Coaching output */}
          <CoachingCard
            strengths={pack.strengths ?? []}
            focus={pack.focus ?? null}
            microExperiment={pack.micro_experiment ?? null}
          />

          {/* Constituent meetings */}
          {meetings.length > 0 && (
            <section>
              <h2 className="text-xs font-semibold text-stone-400 uppercase tracking-widest mb-3">
                Meetings in this baseline
              </h2>
              <div className="space-y-2">
                {meetings.map((meeting, i) => (
                  <MeetingCard key={meeting.run_id ?? i} meeting={meeting} index={i} />
                ))}
              </div>
            </section>
          )}

          {/* Actions */}
          <div className="flex gap-3">
            <Link
              href="/client/experiment"
              className="flex-1 text-center py-3 bg-emerald-600 text-white rounded-xl text-sm font-semibold hover:bg-emerald-700 transition-colors shadow-sm"
            >
              View my experiment →
            </Link>
            <Link
              href="/client/analyze"
              className="px-5 py-3 bg-white border border-stone-300 text-stone-700 rounded-xl text-sm font-medium hover:bg-stone-50 transition-colors"
            >
              Analyse a meeting
            </Link>
          </div>
        </>
      )}
    </div>
  );
}

'use client';

import type { Experiment } from '@/lib/types';
import { api } from '@/lib/api';
import { useState } from 'react';
import Link from 'next/link';
import { STRINGS } from '@/config/strings';

// ─── Types ────────────────────────────────────────────────────────────────────

interface Event {
  id?: string;
  event_id?: string;
  attempt?: string;
  run_id?: string;
  meeting_date?: string;
  created_at?: string;
  human_confirmed?: string;
  notes?: string;
}

interface ExperimentTrackerProps {
  experiment: Experiment;
  events: Event[];
  onUpdate?: () => void;
  onComplete?: () => void;
  onPark?: () => void;
  /** @deprecated Use onPark instead */
  onAbandon?: () => void;
}

// ─── Config maps ──────────────────────────────────────────────────────────────

const ATTEMPT_CONFIG: Record<string, { color: string; label: string; dot: string; bg: string }> = {
  yes:     { color: 'text-cv-teal-700',   label: STRINGS.attemptLabels.yes,     dot: 'bg-cv-teal-500',   bg: 'bg-cv-teal-50'  },
  partial: { color: 'text-cv-amber-700',  label: STRINGS.attemptLabels.partial, dot: 'bg-cv-amber-400',  bg: 'bg-cv-amber-50' },
  no:      { color: 'text-cv-stone-500',  label: STRINGS.attemptLabels.no,      dot: 'bg-cv-stone-300',  bg: 'bg-cv-warm-100' },
};

const HUMAN_PILL_CONFIG: Record<string, { label: string; color: string; border: string }> = {
  confirmed_attempt:    { label: STRINGS.humanConfirmation.confirmed_attempt,    color: 'text-cv-teal-700',  border: 'border-cv-teal-300'  },
  confirmed_no_attempt: { label: STRINGS.humanConfirmation.confirmed_no_attempt, color: 'text-cv-stone-500', border: 'border-cv-stone-300' },
};

const STATUS_CONFIG: Record<string, { bg: string; text: string; label: string }> = {
  proposed:  { bg: 'bg-cv-warm-100',   text: 'text-cv-stone-600',  label: STRINGS.experimentStatus.proposed  },
  active:    { bg: 'bg-cv-teal-100',   text: 'text-cv-teal-700',   label: STRINGS.experimentStatus.active    },
  completed: { bg: 'bg-cv-warm-200',   text: 'text-cv-stone-600',  label: STRINGS.experimentStatus.completed },
  parked:    { bg: 'bg-cv-amber-100',  text: 'text-cv-amber-700',  label: STRINGS.experimentStatus.parked    },
  abandoned: { bg: 'bg-cv-red-100',    text: 'text-cv-red-700',    label: STRINGS.experimentStatus.abandoned },
};

// ─── Component ────────────────────────────────────────────────────────────────

export function ExperimentTracker({
  experiment,
  events,
  onUpdate,
  onComplete,
  onPark,
  onAbandon,
}: ExperimentTrackerProps) {
  const [actionState, setActionState] = useState<'idle' | 'confirm-park' | 'loading'>('idle');

  const isActive   = experiment.status === 'active';
  const statusCfg  = STATUS_CONFIG[experiment.status] ?? STATUS_CONFIG.active;

  // Sort most-recent first, cap at 10
  const sortedEvents = [...events]
    .sort((a, b) => {
      const da = a.meeting_date || a.created_at || '';
      const db = b.meeting_date || b.created_at || '';
      return db.localeCompare(da);
    })
    .slice(0, 10);

  const successCount    = events.filter((e) => e.attempt === 'yes').length;
  const partialCount    = events.filter((e) => e.attempt === 'partial').length;
  const totalAttempted  = successCount + partialCount;
  const meetingsAnalysed = events.length;

  async function handleComplete() {
    if (actionState !== 'idle') return;
    setActionState('loading');
    try {
      await api.completeExperiment(experiment.experiment_record_id);
      onComplete ? onComplete() : onUpdate?.();
    } catch {
      setActionState('idle');
    }
  }

  async function handlePark() {
    if (actionState === 'loading') return;
    setActionState('loading');
    try {
      await api.parkExperiment(experiment.experiment_record_id);
      (onPark ?? onAbandon) ? (onPark ?? onAbandon)!() : onUpdate?.();
    } catch {
      setActionState('idle');
    }
  }

  // ── Analyze-CTA nudge ──────────────────────────────────────────────────────
  function AnalyzeNudge({ message }: { message: string }) {
    return (
      <div className="bg-cv-teal-50 border border-cv-teal-200 rounded-xl px-4 py-3 flex items-center justify-between gap-4">
        <p className="text-sm text-cv-teal-800">{message}</p>
        <Link
          href="/client/analyze"
          className="shrink-0 flex items-center gap-2 text-xs px-3 py-1.5 bg-[#1E3A5F] text-white rounded-lg font-semibold hover:bg-[#162D4A] transition-colors"
        >
          <span className="shrink-0"><svg viewBox="0 0 16 16" fill="none" className="w-4 h-4 shrink-0" aria-hidden="true"><path d="M8 1v3M8 12v3M1 8h3M12 8h3M3.05 3.05l2.12 2.12M10.83 10.83l2.12 2.12M3.05 12.95l2.12-2.12M10.83 5.17l2.12-2.12" stroke="currentColor" strokeWidth={1.4} strokeLinecap="round"/></svg></span>
          {STRINGS.experimentTracker.analyzeMeeting}
        </Link>
      </div>
    );
  }

  function ProgressNudge() {
    if (!isActive) return null;
    if (meetingsAnalysed === 0) {
      return <AnalyzeNudge message={STRINGS.experimentTracker.analyzeToStart} />;
    }
    if (totalAttempted === 0) {
      return (
        <div className="space-y-2">
          <div className="bg-cv-warm-50 border border-cv-warm-200 rounded-xl px-4 py-3">
            <p className="text-sm text-cv-stone-600">
              {STRINGS.experimentTracker.noAttemptsYet(meetingsAnalysed)}
            </p>
          </div>
          <AnalyzeNudge message={STRINGS.experimentTracker.analyzeToContinue} />
        </div>
      );
    }
    return (
      <div className="space-y-2">
        <p className="text-xs text-cv-stone-400">
          {STRINGS.experimentTracker.attemptsDetected(totalAttempted, meetingsAnalysed)}
        </p>
        <AnalyzeNudge message={STRINGS.experimentTracker.analyzeToContinue} />
      </div>
    );
  }

  // ── Render ─────────────────────────────────────────────────────────────────
  return (
    <div className="bg-white rounded-2xl border border-cv-warm-200 overflow-hidden">

      {/* Header */}
      <div className="px-5 py-4 border-b border-cv-warm-100 flex items-start justify-between gap-4">
        <div className="space-y-0.5 min-w-0">
          <h3 className="font-semibold text-cv-stone-900 leading-snug font-serif">
            {experiment.title}
          </h3>
          <p className="text-2xs text-cv-stone-400 tabular-nums">{experiment.experiment_id}</p>
        </div>
        <span className={`text-2xs font-semibold px-2.5 py-1 rounded-full whitespace-nowrap ${statusCfg.bg} ${statusCfg.text}`}>
          {statusCfg.label}
        </span>
      </div>

      {/* Body */}
      <div className="px-5 py-4 space-y-4">

        {/* Instruction + Success marker */}
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          <div className="bg-cv-warm-50 border border-cv-warm-200 rounded-xl p-3.5">
            <p className="text-2xs font-semibold uppercase tracking-[0.14em] text-cv-stone-400 mb-1.5">
              {STRINGS.common.whatToDo}
            </p>
            <p className="text-sm text-cv-stone-700 leading-relaxed">{experiment.instruction}</p>
          </div>
          <div className="bg-cv-warm-50 border border-cv-warm-200 rounded-xl p-3.5">
            <p className="text-2xs font-semibold uppercase tracking-[0.14em] text-cv-stone-400 mb-1.5">
              {STRINGS.common.successLooksLike}
            </p>
            <p className="text-sm text-cv-stone-700 leading-relaxed">{experiment.success_marker}</p>
          </div>
        </div>

        {/* Stats headline */}
        {meetingsAnalysed > 0 && (
          <div className="grid grid-cols-3 gap-3">
            <div className="bg-cv-teal-50 rounded-xl p-3 text-center">
              <p className="text-2xl font-bold text-cv-teal-600">{successCount}</p>
              <p className="text-xs text-cv-stone-500 mt-0.5">{STRINGS.experimentTracker.fullAttempts}</p>
            </div>
            <div className="bg-cv-amber-50 rounded-xl p-3 text-center">
              <p className="text-2xl font-bold text-cv-amber-500">{partialCount}</p>
              <p className="text-xs text-cv-stone-500 mt-0.5">{STRINGS.experimentTracker.partial}</p>
            </div>
            <div className="bg-cv-warm-100 rounded-xl p-3 text-center">
              <p className="text-2xl font-bold text-cv-stone-400">{meetingsAnalysed}</p>
              <p className="text-xs text-cv-stone-500 mt-0.5">{STRINGS.experimentTracker.meetings}</p>
            </div>
          </div>
        )}

        {/* Timeline */}
        {sortedEvents.length > 0 && (
          <div>
            <p className="text-2xs font-semibold uppercase tracking-[0.14em] text-cv-stone-400 mb-2.5">
              {STRINGS.experimentTracker.attemptHistory}
            </p>
            <ul className="space-y-1.5">
              {sortedEvents.map((ev, i) => {
                const cfg       = ATTEMPT_CONFIG[ev.attempt ?? 'no'] ?? ATTEMPT_CONFIG.no;
                const humanCfg  = ev.human_confirmed ? HUMAN_PILL_CONFIG[ev.human_confirmed] : undefined;
                const displayDate = ev.meeting_date || ev.created_at;

                return (
                  <li
                    key={ev.event_id ?? ev.id ?? i}
                    className={`flex items-center gap-2 rounded-lg px-3 py-2 ${cfg.bg}`}
                  >
                    <span className={`w-2 h-2 rounded-full shrink-0 ${cfg.dot}`} />
                    <span className={`text-xs font-semibold ${cfg.color}`}>{cfg.label}</span>

                    {humanCfg && (
                      <span
                        className={`text-xs font-medium px-2 py-0.5 rounded-full bg-white border ${humanCfg.border} ${humanCfg.color}`}
                        title={STRINGS.humanConfirmation.tooltip}
                      >
                        {humanCfg.label}
                      </span>
                    )}

                    {displayDate && (
                      <span className="text-xs text-cv-stone-400 ml-auto shrink-0 tabular-nums">
                        {new Date(displayDate).toLocaleDateString('en-US', {
                          month: 'short',
                          day: 'numeric',
                        })}
                      </span>
                    )}
                  </li>
                );
              })}
            </ul>
          </div>
        )}

        {/* Analyze nudge */}
        <ProgressNudge />

        {/* Actions */}
        {isActive && (
          <div className="pt-1 space-y-2">
            {actionState === 'confirm-park' ? (
              <div className="bg-cv-amber-50 border border-cv-amber-200 rounded-xl p-4 space-y-3">
                <p className="text-sm font-semibold text-cv-amber-800">{STRINGS.experimentTracker.parkConfirmTitle}</p>
                <p className="text-xs text-cv-amber-700 leading-relaxed">
                  {STRINGS.experimentTracker.parkConfirmDesc}
                </p>
                <div className="flex gap-2">
                  <button
                    onClick={handlePark}
                    className="px-4 py-2 bg-cv-amber-600 text-white rounded-xl text-xs font-semibold hover:bg-cv-amber-700 transition-colors"
                  >
                    {STRINGS.experimentTracker.yesParkIt}
                  </button>
                  <button
                    onClick={() => setActionState('idle')}
                    className="px-4 py-2 bg-white border border-cv-warm-300 text-cv-stone-600 rounded-xl text-xs font-semibold hover:bg-cv-warm-50 transition-colors"
                  >
                    {STRINGS.experimentTracker.keepGoing}
                  </button>
                </div>
              </div>
            ) : (
              <div className="flex gap-2">
                <button
                  onClick={handleComplete}
                  disabled={actionState === 'loading'}
                  className="flex-1 py-2.5 bg-cv-teal-600 text-white rounded-xl text-sm font-medium hover:bg-cv-teal-700 disabled:opacity-50 transition-colors"
                >
                  {actionState === 'loading' ? STRINGS.common.saving : STRINGS.experimentTracker.markComplete}
                </button>
                <button
                  onClick={() => setActionState('confirm-park')}
                  disabled={actionState === 'loading'}
                  className="flex items-center gap-2 px-4 py-2.5 bg-white border border-cv-warm-300 text-cv-stone-600 rounded-xl text-sm font-medium hover:bg-cv-warm-50 disabled:opacity-50 transition-colors"
                >
                  <svg viewBox="0 0 16 16" fill="none" className="w-4 h-4 shrink-0" aria-hidden="true"><rect x="3.5" y="2.5" width="3" height="11" rx="1" fill="currentColor"/><rect x="9.5" y="2.5" width="3" height="11" rx="1" fill="currentColor"/></svg>
                  {STRINGS.experimentTracker.parkForNow}
                </button>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

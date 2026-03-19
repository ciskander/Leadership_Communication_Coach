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
  onPark?: (experimentRecordId?: string) => void;
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
  const [historyOpen, setHistoryOpen] = useState(false);

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
      onPark ? onPark(experiment.experiment_record_id) : onAbandon ? onAbandon() : onUpdate?.();
    } catch {
      setActionState('idle');
    }
  }

  // ── Summary text ────────────────────────────────────────────────────────────
  function summaryText(): string {
    if (meetingsAnalysed === 0) {
      return STRINGS.experimentTracker.analyzeToStart;
    }
    if (totalAttempted === 0) {
      return STRINGS.experimentTracker.noAttemptsYet(meetingsAnalysed);
    }
    return STRINGS.experimentTracker.attemptsDetected(totalAttempted, meetingsAnalysed);
  }

  // ── Render ─────────────────────────────────────────────────────────────────
  return (
    <div className="bg-white rounded border border-cv-stone-400 overflow-hidden">

      {/* Header */}
      <div className="px-5 py-4 border-b border-cv-warm-300 flex items-start justify-between gap-4">
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
          <div className="bg-cv-warm-50 border border-cv-warm-300 rounded p-3.5">
            <p className="text-2xs font-semibold uppercase tracking-[0.14em] text-cv-stone-400 mb-1.5">
              {STRINGS.common.whatToDo}
            </p>
            <p className="text-sm text-cv-stone-700 leading-relaxed">{experiment.instruction}</p>
          </div>
          <div className="bg-cv-warm-50 border border-cv-warm-300 rounded p-3.5">
            <p className="text-2xs font-semibold uppercase tracking-[0.14em] text-cv-stone-400 mb-1.5">
              {STRINGS.common.successLooksLike}
            </p>
            <p className="text-sm text-cv-stone-700 leading-relaxed">{experiment.success_marker}</p>
          </div>
        </div>

        {/* Attempt history */}
        <div>
          <p className="text-2xs font-semibold uppercase tracking-[0.14em] text-cv-stone-400 mb-1.5">
            {STRINGS.experimentTracker.attemptHistory}
          </p>

          {sortedEvents.length > 0 ? (
            <>
              <button
                onClick={() => setHistoryOpen(!historyOpen)}
                className="w-full flex items-center justify-between gap-2 text-sm text-cv-stone-600 leading-relaxed hover:text-cv-stone-800 transition-colors"
              >
                <span>{summaryText()}</span>
                <svg
                  viewBox="0 0 16 16"
                  fill="none"
                  className={`w-3.5 h-3.5 shrink-0 text-cv-stone-400 transition-transform duration-200 ${historyOpen ? 'rotate-180' : ''}`}
                  aria-hidden="true"
                >
                  <path d="M4 6l4 4 4-4" stroke="currentColor" strokeWidth={1.5} strokeLinecap="round" strokeLinejoin="round" />
                </svg>
              </button>

              {historyOpen && (
                <ul className="space-y-1.5 mt-2">
                  {sortedEvents.map((ev, i) => {
                    const cfg       = ATTEMPT_CONFIG[ev.attempt ?? 'no'] ?? ATTEMPT_CONFIG.no;
                    const humanCfg  = ev.human_confirmed ? HUMAN_PILL_CONFIG[ev.human_confirmed] : undefined;
                    const displayDate = ev.meeting_date || ev.created_at;

                    return (
                      <li
                        key={ev.event_id ?? ev.id ?? i}
                        className={`flex items-center gap-2 rounded px-3 py-2 ${cfg.bg}`}
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
              )}
            </>
          ) : (
            <p className="text-sm text-cv-stone-600 leading-relaxed">
              {summaryText()}
            </p>
          )}
        </div>

        {/* CTA buttons */}
        {isActive && (
          <div className="pt-1 space-y-2">
            {actionState === 'confirm-park' ? (
              <div className="bg-cv-amber-50 border border-cv-amber-200 rounded p-4 space-y-3">
                <p className="text-sm font-semibold text-cv-amber-800">{STRINGS.experimentTracker.parkConfirmTitle}</p>
                <p className="text-xs text-cv-amber-700 leading-relaxed">
                  {STRINGS.experimentTracker.parkConfirmDesc}
                </p>
                <div className="flex gap-2">
                  <button
                    onClick={handlePark}
                    className="px-4 py-2 bg-cv-amber-600 text-white rounded text-xs font-semibold hover:bg-cv-amber-700 transition-colors"
                  >
                    {STRINGS.experimentTracker.yesParkIt}
                  </button>
                  <button
                    onClick={() => setActionState('idle')}
                    className="px-4 py-2 bg-white border border-cv-warm-300 text-cv-stone-600 rounded text-xs font-semibold hover:bg-cv-warm-50 transition-colors"
                  >
                    {STRINGS.experimentTracker.keepGoing}
                  </button>
                </div>
              </div>
            ) : (
              <div className="flex gap-2 flex-wrap">
                <Link
                  href="/client/analyze"
                  className="flex items-center gap-2 px-4 py-2.5 bg-cv-navy-600 text-white rounded text-sm font-medium hover:bg-cv-navy-700 transition-colors"
                >
                  <svg viewBox="0 0 24 24" fill="none" className="w-4 h-4 shrink-0" aria-hidden="true"><path d="M9 3L10.5 7.5L15 9L10.5 10.5L9 15L7.5 10.5L3 9L7.5 7.5L9 3Z" stroke="currentColor" strokeWidth={1.7} strokeLinecap="round" strokeLinejoin="round"/><path d="M19 13L19.75 15.25L22 16L19.75 16.75L19 19L18.25 16.75L16 16L18.25 15.25L19 13Z" stroke="currentColor" strokeWidth={1.7} strokeLinecap="round" strokeLinejoin="round"/></svg>
                  {STRINGS.experimentTracker.analyzeMeeting}
                </Link>
                <button
                  onClick={handleComplete}
                  disabled={actionState === 'loading'}
                  className="flex-1 py-2.5 bg-cv-teal-600 text-white rounded text-sm font-medium hover:bg-cv-teal-700 disabled:opacity-50 transition-colors"
                >
                  {actionState === 'loading' ? STRINGS.common.saving : STRINGS.experimentTracker.markComplete}
                </button>
                <button
                  onClick={() => setActionState('confirm-park')}
                  disabled={actionState === 'loading'}
                  className="flex items-center gap-2 px-4 py-2.5 bg-white border border-cv-warm-300 text-cv-stone-600 rounded text-sm font-medium hover:bg-cv-warm-50 disabled:opacity-50 transition-colors"
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

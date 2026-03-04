'use client';

import type { Experiment } from '@/lib/types';
import { api } from '@/lib/api';
import { useState } from 'react';
import Link from 'next/link';

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
  onAbandon?: () => void;
}

const ATTEMPT_CONFIG: Record<string, { color: string; label: string; dot: string; bg: string }> = {
  yes:     { color: 'text-emerald-700', label: 'Attempted',       dot: 'bg-emerald-500', bg: 'bg-emerald-50' },
  partial: { color: 'text-amber-700',   label: 'Partial attempt', dot: 'bg-amber-400',   bg: 'bg-amber-50' },
  no:      { color: 'text-stone-500',   label: 'Not attempted',   dot: 'bg-stone-300',   bg: 'bg-stone-50' },
};

const STATUS_CONFIG: Record<string, { bg: string; text: string; label: string }> = {
  proposed:  { bg: 'bg-violet-100',  text: 'text-violet-700',  label: 'Proposed' },
  active:    { bg: 'bg-emerald-100', text: 'text-emerald-700', label: 'Active' },
  completed: { bg: 'bg-stone-100',   text: 'text-stone-600',   label: 'Completed' },
  abandoned: { bg: 'bg-rose-100',    text: 'text-rose-700',    label: 'Abandoned' },
};

// Human confirmation override indicator
function ConfirmedBadge({ value }: { value?: string }) {
  if (!value || value === 'not_reviewed') return null;
  if (value === 'confirmed_attempt') {
    return (
      <span className="text-xs text-emerald-600 font-medium ml-1" title="You confirmed this attempt">
        · you confirmed ✓
      </span>
    );
  }
  if (value === 'confirmed_no_attempt') {
    return (
      <span className="text-xs text-stone-400 font-medium ml-1" title="You said no attempt was made">
        · you said no
      </span>
    );
  }
  return null;
}

export function ExperimentTracker({ experiment, events, onUpdate, onComplete, onAbandon }: ExperimentTrackerProps) {
  const [actionState, setActionState] = useState<'idle' | 'confirm-abandon' | 'loading'>('idle');

  const isActive = experiment.status === 'active';
  const statusCfg = STATUS_CONFIG[experiment.status] ?? STATUS_CONFIG.active;

  const totalAttempted = experiment.attempt_count ?? 0;
  const successCount = events.filter((e) => e.attempt === 'yes').length;
  const partialCount = events.filter((e) => e.attempt === 'partial').length;
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

  async function handleAbandon() {
    if (actionState !== 'loading') {
      setActionState('loading');
      try {
        await api.abandonExperiment(experiment.experiment_record_id);
        onAbandon ? onAbandon() : onUpdate?.();
      } catch {
        setActionState('idle');
      }
    }
  }

  // Context-aware empty / progress nudge message
  function ProgressNudge() {
    if (!isActive) return null;
    if (meetingsAnalysed === 0) {
      return (
        <div className="bg-blue-50 rounded-xl px-4 py-3 flex items-center justify-between gap-4">
          <p className="text-sm text-blue-700">
            Analyse your next meeting to start tracking this experiment.
          </p>
          <Link
            href="/client/analyze"
            className="shrink-0 text-xs px-3 py-1.5 bg-blue-600 text-white rounded-lg font-semibold hover:bg-blue-700 transition-colors"
          >
            Analyse meeting
          </Link>
        </div>
      );
    }
    if (totalAttempted === 0) {
      return (
        <div className="bg-stone-50 rounded-xl px-4 py-3 flex items-center justify-between gap-4">
          <p className="text-sm text-stone-600">
            No attempts detected yet across {meetingsAnalysed} meeting{meetingsAnalysed !== 1 ? 's' : ''}. Keep going — it takes a few tries to build the habit.
          </p>
          <Link
            href="/client/analyze"
            className="shrink-0 text-xs px-3 py-1.5 bg-stone-800 text-white rounded-lg font-semibold hover:bg-stone-700 transition-colors"
          >
            Analyse meeting
          </Link>
        </div>
      );
    }
    return (
      <div className="flex items-center justify-between gap-4">
        <p className="text-xs text-stone-400">
          {totalAttempted} attempt{totalAttempted !== 1 ? 's' : ''} detected across {meetingsAnalysed} meeting{meetingsAnalysed !== 1 ? 's' : ''} analysed.
        </p>
        <Link
          href="/client/analyze"
          className="shrink-0 text-xs px-3 py-1.5 bg-stone-100 text-stone-700 rounded-lg font-semibold hover:bg-stone-200 transition-colors"
        >
          Analyse meeting
        </Link>
      </div>
    );
  }

  return (
    <div className="bg-white rounded-2xl border border-stone-200 overflow-hidden">
      {/* Header */}
      <div className="px-5 py-4 border-b border-stone-100 flex items-start justify-between gap-4">
        <div className="space-y-0.5 min-w-0">
          <h3 className="font-semibold text-stone-900 leading-snug">{experiment.title}</h3>
          <p className="text-xs text-stone-400">{experiment.experiment_id}</p>
        </div>
        <span className={`text-xs font-semibold px-2.5 py-1 rounded-full whitespace-nowrap ${statusCfg.bg} ${statusCfg.text}`}>
          {statusCfg.label}
        </span>
      </div>

      {/* Body */}
      <div className="px-5 py-4 space-y-4">

        {/* Instruction + Success marker */}
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          <div className="bg-stone-50 rounded-xl p-3.5">
            <p className="text-xs font-semibold text-stone-400 uppercase tracking-widest mb-1.5">
              What to do
            </p>
            <p className="text-sm text-stone-700 leading-relaxed">{experiment.instruction}</p>
          </div>
          <div className="bg-stone-50 rounded-xl p-3.5">
            <p className="text-xs font-semibold text-stone-400 uppercase tracking-widest mb-1.5">
              Success looks like
            </p>
            <p className="text-sm text-stone-700 leading-relaxed">{experiment.success_marker}</p>
          </div>
        </div>

        {/* Progress summary — only shown once there's data */}
        {meetingsAnalysed > 0 && (
          <div className="grid grid-cols-3 gap-3 py-1">
            <div className="bg-emerald-50 rounded-xl p-3 text-center">
              <p className="text-2xl font-bold text-emerald-600">{successCount}</p>
              <p className="text-xs text-stone-500 mt-0.5">Full attempts</p>
            </div>
            <div className="bg-amber-50 rounded-xl p-3 text-center">
              <p className="text-2xl font-bold text-amber-500">{partialCount}</p>
              <p className="text-xs text-stone-500 mt-0.5">Partial</p>
            </div>
            <div className="bg-stone-50 rounded-xl p-3 text-center">
              <p className="text-2xl font-bold text-stone-400">{meetingsAnalysed}</p>
              <p className="text-xs text-stone-500 mt-0.5">Meetings</p>
            </div>
          </div>
        )}

        {/* Attempt history timeline */}
        {meetingsAnalysed > 0 && (
          <div>
            <p className="text-xs font-semibold text-stone-400 uppercase tracking-widest mb-2.5">
              Attempt history
            </p>
            <ul className="space-y-1.5">
              {events.map((ev, i) => {
                const cfg = ATTEMPT_CONFIG[ev.attempt ?? 'no'] ?? ATTEMPT_CONFIG.no;
                const displayDate = ev.meeting_date || ev.created_at;
                return (
                  <li
                    key={ev.event_id ?? ev.id ?? i}
                    className={`flex items-center gap-3 rounded-lg px-3 py-2 ${cfg.bg}`}
                  >
                    <span className={`w-2 h-2 rounded-full flex-shrink-0 ${cfg.dot}`} />
                    <span className={`text-sm font-medium ${cfg.color}`}>
                      {cfg.label}
                      <ConfirmedBadge value={ev.human_confirmed} />
                    </span>
                    {displayDate && (
                      <span className="text-xs text-stone-400 ml-auto">
                        {new Date(displayDate).toLocaleDateString('en-US', {
                          month: 'short', day: 'numeric',
                        })}
                      </span>
                    )}
                  </li>
                );
              })}
            </ul>
          </div>
        )}

        {/* Context-aware nudge / Analyse button */}
        <ProgressNudge />

        {/* Actions */}
        {isActive && (
          <div className="pt-1 space-y-2">
            {actionState === 'confirm-abandon' ? (
              <div className="bg-rose-50 border border-rose-200 rounded-xl p-4 space-y-3">
                <p className="text-sm font-medium text-rose-800">Abandon this experiment?</p>
                <p className="text-xs text-rose-700 leading-relaxed">
                  It will be removed from your active experiments. Any progress recorded so far will be saved.
                </p>
                <div className="flex gap-2">
                  <button
                    onClick={handleAbandon}
                    className="px-4 py-2 bg-rose-600 text-white rounded-xl text-xs font-semibold hover:bg-rose-700 transition-colors"
                  >
                    Yes, abandon it
                  </button>
                  <button
                    onClick={() => setActionState('idle')}
                    className="px-4 py-2 bg-white border border-stone-300 text-stone-600 rounded-xl text-xs font-semibold hover:bg-stone-50 transition-colors"
                  >
                    Keep going
                  </button>
                </div>
              </div>
            ) : (
              <div className="flex gap-2">
                <button
                  onClick={handleComplete}
                  disabled={actionState === 'loading'}
                  className="flex-1 py-2.5 bg-emerald-600 text-white rounded-xl text-sm font-medium hover:bg-emerald-700 disabled:opacity-50 transition-colors"
                >
                  {actionState === 'loading' ? 'Saving…' : 'Mark complete ✓'}
                </button>
                <button
                  onClick={() => setActionState('confirm-abandon')}
                  disabled={actionState === 'loading'}
                  className="px-4 py-2.5 bg-white border border-stone-300 text-stone-600 rounded-xl text-sm font-medium hover:bg-stone-50 disabled:opacity-50 transition-colors"
                >
                  Abandon experiment
                </button>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

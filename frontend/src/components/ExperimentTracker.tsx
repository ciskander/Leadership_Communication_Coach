'use client';

import type { Experiment } from '@/lib/types';
import { api } from '@/lib/api';
import { useState } from 'react';

interface Event {
  id?: string;
  attempt?: string;
  run_id?: string;
  created_at?: string;
  notes?: string;
}

interface ExperimentTrackerProps {
  experiment: Experiment;
  events: Event[];
  onUpdate?: () => void;
}

const ATTEMPT_CONFIG: Record<string, { color: string; label: string; dot: string }> = {
  yes:     { color: 'text-emerald-700', label: 'Attempted',         dot: 'bg-emerald-500' },
  partial: { color: 'text-amber-700',   label: 'Partially tried',   dot: 'bg-amber-400' },
  no:      { color: 'text-stone-500',   label: 'Not attempted',     dot: 'bg-stone-300' },
};

const STATUS_CONFIG: Record<string, { bg: string; text: string; label: string }> = {
  assigned:  { bg: 'bg-blue-100',    text: 'text-blue-700',    label: 'Assigned' },
  active:    { bg: 'bg-emerald-100', text: 'text-emerald-700', label: 'Active' },
  completed: { bg: 'bg-stone-100',   text: 'text-stone-600',   label: 'Completed' },
  abandoned: { bg: 'bg-rose-100',    text: 'text-rose-700',    label: 'Abandoned' },
};

export function ExperimentTracker({ experiment, events, onUpdate }: ExperimentTrackerProps) {
  const [loading, setLoading] = useState(false);

  const handleAction = async (action: 'complete' | 'abandon') => {
    setLoading(true);
    try {
      await api.updateExperiment(experiment.experiment_record_id, action);
      onUpdate?.();
    } finally {
      setLoading(false);
    }
  };

  const isActive = experiment.status === 'assigned' || experiment.status === 'active';
  const statusCfg = STATUS_CONFIG[experiment.status] ?? STATUS_CONFIG.assigned;

  const successCount = events.filter((e) => e.attempt === 'yes').length;
  const partialCount = events.filter((e) => e.attempt === 'partial').length;

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

        {/* Progress summary */}
        {events.length > 0 && (
          <div className="flex items-center gap-4 py-2">
            <div className="text-center">
              <p className="text-2xl font-bold text-emerald-600">{successCount}</p>
              <p className="text-xs text-stone-400">Full attempts</p>
            </div>
            <div className="text-center">
              <p className="text-2xl font-bold text-amber-500">{partialCount}</p>
              <p className="text-xs text-stone-400">Partial</p>
            </div>
            <div className="text-center">
              <p className="text-2xl font-bold text-stone-400">{events.length}</p>
              <p className="text-xs text-stone-400">Meetings</p>
            </div>
          </div>
        )}

        {/* Timeline */}
        {events.length > 0 && (
          <div>
            <p className="text-xs font-semibold text-stone-400 uppercase tracking-widest mb-2.5">
              Attempt history
            </p>
            <ul className="space-y-2">
              {events.map((ev, i) => {
                const cfg = ATTEMPT_CONFIG[ev.attempt ?? 'no'] ?? ATTEMPT_CONFIG.no;
                return (
                  <li key={ev.id ?? i} className="flex items-center gap-3">
                    <span className={`w-2 h-2 rounded-full flex-shrink-0 ${cfg.dot}`} />
                    <span className={`text-sm font-medium ${cfg.color}`}>{cfg.label}</span>
                    {ev.created_at && (
                      <span className="text-xs text-stone-400 ml-auto">
                        {new Date(ev.created_at).toLocaleDateString('en-US', {
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

        {events.length === 0 && isActive && (
          <div className="bg-blue-50 rounded-xl px-4 py-3">
            <p className="text-sm text-blue-700">
              Upload your next meeting transcript to track your first attempt at this experiment.
            </p>
          </div>
        )}

        {/* Actions */}
        {isActive && (
          <div className="flex gap-2 pt-1">
            <button
              onClick={() => handleAction('complete')}
              disabled={loading}
              className="flex-1 py-2.5 bg-emerald-600 text-white rounded-xl text-sm font-medium hover:bg-emerald-700 disabled:opacity-50 transition-colors"
            >
              Mark complete ✓
            </button>
            <button
              onClick={() => handleAction('abandon')}
              disabled={loading}
              className="px-4 py-2.5 bg-white border border-stone-300 text-stone-600 rounded-xl text-sm font-medium hover:bg-stone-50 disabled:opacity-50 transition-colors"
            >
              Move on
            </button>
          </div>
        )}
      </div>
    </div>
  );
}

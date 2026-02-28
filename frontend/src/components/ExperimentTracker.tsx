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

const STATUS_COLORS: Record<string, string> = {
  assigned: 'bg-blue-100 text-blue-700',
  active: 'bg-green-100 text-green-700',
  completed: 'bg-gray-100 text-gray-700',
  abandoned: 'bg-red-100 text-red-700',
};

export function ExperimentTracker({
  experiment,
  events,
  onUpdate,
}: ExperimentTrackerProps) {
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

  const isActive =
    experiment.status === 'assigned' || experiment.status === 'active';

  return (
    <div className="bg-white border border-gray-200 rounded-xl p-5 space-y-4">
      <div className="flex items-start justify-between">
        <div>
          <h3 className="font-semibold text-gray-900">{experiment.title}</h3>
          <p className="text-xs text-gray-500">{experiment.experiment_id}</p>
        </div>
        <span
          className={`text-xs font-medium px-2 py-1 rounded-full capitalize ${
            STATUS_COLORS[experiment.status] ?? 'bg-gray-100 text-gray-600'
          }`}
        >
          {experiment.status}
        </span>
      </div>

      <div className="space-y-2">
        <div>
          <p className="text-xs font-medium text-gray-500 uppercase mb-0.5">Instruction</p>
          <p className="text-sm text-gray-700">{experiment.instruction}</p>
        </div>
        <div>
          <p className="text-xs font-medium text-gray-500 uppercase mb-0.5">Success Marker</p>
          <p className="text-sm text-gray-700">{experiment.success_marker}</p>
        </div>
      </div>

      {/* Timeline */}
      {events.length > 0 && (
        <div>
          <p className="text-xs font-medium text-gray-500 uppercase mb-2">Attempt History</p>
          <ul className="space-y-1">
            {events.map((ev, i) => (
              <li key={ev.id ?? i} className="flex items-center gap-2 text-xs text-gray-600">
                <span
                  className={`w-2 h-2 rounded-full flex-shrink-0 ${
                    ev.attempt === 'yes'
                      ? 'bg-green-500'
                      : ev.attempt === 'partial'
                      ? 'bg-amber-400'
                      : 'bg-gray-300'
                  }`}
                />
                <span className="capitalize">{ev.attempt ?? 'no attempt'}</span>
                {ev.created_at && (
                  <span className="text-gray-400">
                    {new Date(ev.created_at).toLocaleDateString()}
                  </span>
                )}
              </li>
            ))}
          </ul>
        </div>
      )}

      {isActive && (
        <div className="flex gap-2 pt-2">
          <button
            onClick={() => handleAction('complete')}
            disabled={loading}
            className="text-sm px-3 py-1.5 bg-green-600 text-white rounded-md hover:bg-green-700 disabled:opacity-50"
          >
            Mark Complete
          </button>
          <button
            onClick={() => handleAction('abandon')}
            disabled={loading}
            className="text-sm px-3 py-1.5 bg-white border border-gray-300 text-gray-700 rounded-md hover:bg-gray-50 disabled:opacity-50"
          >
            Abandon / Move On
          </button>
        </div>
      )}
    </div>
  );
}

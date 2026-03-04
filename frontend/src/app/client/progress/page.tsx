'use client';

import { useEffect, useState, useRef } from 'react';
import { api } from '@/lib/api';
import type { ClientProgress, RunHistoryPoint, PastExperiment } from '@/lib/types';
import {
  LineChart,
  Line,
  BarChart,
  Bar,
  Cell,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
  ReferenceDot,
} from 'recharts';

// ─── Pattern explanations ─────────────────────────────────────────────────────

const PATTERN_EXPLANATIONS: Record<string, string> = {
  agenda_clarity:
    'How consistently you open meetings with a clear agenda and stated objectives.',
  objective_signaling:
    "How often you make the meeting's purpose explicit when transitioning between topics.",
  turn_allocation:
    'How equitably you distribute speaking opportunities across participants.',
  facilitative_inclusion:
    'How actively you draw in quieter voices and prevent dominant speakers from taking over.',
  decision_closure:
    'How reliably you bring discussions to a clear decision with an owner before moving on.',
  owner_timeframe_specification:
    'How consistently action items are assigned with a named owner and a deadline.',
  summary_checkback:
    'How often you summarise key points and check for alignment before closing a topic.',
  question_quality:
    'How often your questions are tied to a specific decision or outcome rather than open-ended exploration.',
  listener_response_quality:
    'How well you acknowledge and build on what others have said before responding.',
  conversational_balance:
    'Whether speaking time is distributed appropriately given your role in the meeting.',
};

const PATTERN_LABELS: Record<string, string> = {
  agenda_clarity: 'Agenda Clarity',
  objective_signaling: 'Objective Signaling',
  turn_allocation: 'Turn Allocation',
  facilitative_inclusion: 'Facilitative Inclusion',
  decision_closure: 'Decision Closure',
  owner_timeframe_specification: 'Owner & Timeframe',
  summary_checkback: 'Summary Checkback',
  question_quality: 'Question Quality',
  listener_response_quality: 'Listener Response',
  conversational_balance: 'Conversational Balance',
};

const LINE_COLORS = [
  '#2563eb', '#16a34a', '#dc2626', '#d97706', '#7c3aed',
  '#0891b2', '#db2777', '#65a30d', '#ea580c', '#6b7280',
];

// ─── Popover ──────────────────────────────────────────────────────────────────

function InfoPopover({ patternId }: { patternId: string }) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const handler = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, [open]);

  return (
    <span className="relative inline-block" ref={ref}>
      <button
        onClick={() => setOpen((v) => !v)}
        className="ml-1 text-gray-400 hover:text-blue-600 transition-colors align-middle leading-none"
        aria-label="Pattern explanation"
        type="button"
      >
        <svg className="w-4 h-4 inline" viewBox="0 0 20 20" fill="currentColor">
          <path
            fillRule="evenodd"
            d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7-4a1 1 0 11-2 0 1 1 0 012 0zM9 9a1 1 0 000 2v3a1 1 0 001 1h1a1 1 0 100-2v-3a1 1 0 00-1-1H9z"
            clipRule="evenodd"
          />
        </svg>
      </button>
      {open && (
        <div className="absolute z-50 left-5 top-0 w-64 bg-white border border-gray-200 rounded-lg shadow-lg p-3 text-sm text-gray-700 leading-snug">
          {PATTERN_EXPLANATIONS[patternId] ?? 'No explanation available.'}
        </div>
      )}
    </span>
  );
}

// ─── Date formatter ───────────────────────────────────────────────────────────

function fmtDate(dateStr: string | null | undefined): string {
  if (!dateStr) return '—';
  try {
    return new Date(dateStr).toLocaleDateString('en-GB', {
      day: 'numeric',
      month: 'short',
      year: 'numeric',
    });
  } catch {
    return dateStr;
  }
}

// ─── Chart section ────────────────────────────────────────────────────────────

interface ChartPoint {
  date: string;
  label: string;
  isBaseline: boolean;
  [patternId: string]: string | number | boolean | null;
}

function buildChartData(
  history: RunHistoryPoint[],
  visiblePatterns: string[]
): ChartPoint[] {
  return history.map((run) => {
    const point: ChartPoint = {
      date: run.meeting_date ?? '',
      label: run.meeting_date ? fmtDate(run.meeting_date) : 'Unknown',
      isBaseline: run.is_baseline,
    };
    for (const p of run.patterns) {
      if (visiblePatterns.includes(p.pattern_id)) {
        point[p.pattern_id] = Math.round(p.ratio * 100);
      }
    }
    return point;
  });
}

function PatternTrendsChart({ history }: { history: RunHistoryPoint[] }) {
  const [showAll, setShowAll] = useState(false);

  // Count post-baseline meetings
  const baselineIdx = history.findIndex((r) => r.is_baseline);
  const postBaselineCount = baselineIdx >= 0 ? history.length - baselineIdx - 1 : history.length;
  const showLineChart = postBaselineCount >= 3;

  // Aggregate opportunity counts across all runs to pick top patterns
  const oppCounts: Record<string, number> = {};
  for (const run of history) {
    for (const p of run.patterns) {
      oppCounts[p.pattern_id] = (oppCounts[p.pattern_id] ?? 0) + p.opportunity_count;
    }
  }
  const allPatterns = Object.keys(oppCounts).sort((a, b) => oppCounts[b] - oppCounts[a]);
  const topPatterns = allPatterns.slice(0, 5);
  const visiblePatterns = showAll ? allPatterns : topPatterns;

  const chartData = buildChartData(history, visiblePatterns);
  const baselinePoint = chartData.find((p) => p.isBaseline);

  // Custom tooltip
  const CustomTooltip = ({ active, payload, label }: any) => {
    if (!active || !payload?.length) return null;
    return (
      <div className="bg-white border border-gray-200 rounded-lg shadow-lg p-3 text-sm min-w-[160px]">
        <p className="font-semibold text-gray-700 mb-1">{label}</p>
        {payload.map((entry: any) => (
          <div key={entry.dataKey} className="flex justify-between gap-4">
            <span style={{ color: entry.color }}>{PATTERN_LABELS[entry.dataKey] ?? entry.dataKey}</span>
            <span className="font-medium">{entry.value}%</span>
          </div>
        ))}
      </div>
    );
  };

  if (history.length === 0) {
    return (
      <div className="flex items-center justify-center h-48 text-gray-400 text-sm">
        No run data yet. Analyse a meeting to see your trends.
      </div>
    );
  }

  return (
    <div>
      {/* Pattern legend with ⓘ */}
      <div className="flex flex-wrap gap-3 mb-4">
        {visiblePatterns.map((pid, i) => (
          <span key={pid} className="flex items-center text-sm text-gray-700">
            <span
              className="inline-block w-3 h-3 rounded-full mr-1.5 flex-shrink-0"
              style={{ background: LINE_COLORS[i % LINE_COLORS.length] }}
            />
            {PATTERN_LABELS[pid] ?? pid}
            <InfoPopover patternId={pid} />
          </span>
        ))}
      </div>

      {/* Chart */}
      {showLineChart ? (
        <>
          {postBaselineCount < history.length && (
            <p className="text-xs text-gray-400 mb-2">
              ● Baseline anchor shown as dashed line marker
            </p>
          )}
          <ResponsiveContainer width="100%" height={280}>
            <LineChart data={chartData} margin={{ top: 8, right: 16, left: 0, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
              <XAxis
                dataKey="label"
                tick={{ fontSize: 11, fill: '#9ca3af' }}
                tickLine={false}
              />
              <YAxis
                domain={[0, 100]}
                tickFormatter={(v) => `${v}%`}
                tick={{ fontSize: 11, fill: '#9ca3af' }}
                tickLine={false}
                axisLine={false}
              />
              <Tooltip content={<CustomTooltip />} />
              {visiblePatterns.map((pid, i) => (
                <Line
                  key={pid}
                  type="monotone"
                  dataKey={pid}
                  stroke={LINE_COLORS[i % LINE_COLORS.length]}
                  strokeWidth={2}
                  dot={{ r: 3, fill: LINE_COLORS[i % LINE_COLORS.length] }}
                  activeDot={{ r: 5 }}
                  connectNulls
                />
              ))}
              {/* Baseline marker */}
              {baselinePoint && visiblePatterns[0] && (
                <ReferenceDot
                  x={baselinePoint.label}
                  y={Number(baselinePoint[visiblePatterns[0]]) || 0}
                  r={0}
                  label={{ value: 'Baseline', position: 'top', fontSize: 10, fill: '#6b7280' }}
                />
              )}
            </LineChart>
          </ResponsiveContainer>
        </>
      ) : (
        <>
          {/* Bar chart snapshot */}
          {(() => {
            const latest = [...history].reverse().find((r) => !r.is_baseline) ?? history[history.length - 1];
            const barData = visiblePatterns.map((pid) => {
              const p = latest.patterns.find((x) => x.pattern_id === pid);
              return {
                name: PATTERN_LABELS[pid] ?? pid,
                score: p ? Math.round(p.ratio * 100) : 0,
                pid,
              };
            });
            const meetingsUntil = 3 - postBaselineCount;
            return (
              <>
                <div className="mb-3 inline-flex items-center gap-2 bg-blue-50 text-blue-700 text-xs font-medium px-3 py-1.5 rounded-full">
                  <svg className="w-3.5 h-3.5" viewBox="0 0 20 20" fill="currentColor">
                    <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm1-12a1 1 0 10-2 0v4a1 1 0 00.293.707l2.828 2.829a1 1 0 101.415-1.415L11 9.586V6z" clipRule="evenodd" />
                  </svg>
                  {meetingsUntil} more meeting{meetingsUntil !== 1 ? 's' : ''} until trends appear
                </div>
                <ResponsiveContainer width="100%" height={240}>
                  <BarChart data={barData} margin={{ top: 4, right: 16, left: 0, bottom: 40 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" vertical={false} />
                    <XAxis
                      dataKey="name"
                      tick={{ fontSize: 10, fill: '#9ca3af' }}
                      tickLine={false}
                      angle={-30}
                      textAnchor="end"
                      interval={0}
                    />
                    <YAxis
                      domain={[0, 100]}
                      tickFormatter={(v) => `${v}%`}
                      tick={{ fontSize: 11, fill: '#9ca3af' }}
                      tickLine={false}
                      axisLine={false}
                    />
                    <Tooltip
                      formatter={(v: number | undefined) => [`${v ?? 0}%`, 'Score']}
                      cursor={{ fill: '#f9fafb' }}
                    />
                    <Bar dataKey="score" radius={[4, 4, 0, 0]} maxBarSize={48}>
                      {barData.map((entry, index) => (
                        <Cell key={entry.pid} fill={LINE_COLORS[visiblePatterns.indexOf(entry.pid) % LINE_COLORS.length]} />
                      ))}
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              </>
            );
          })()}
        </>
      )}

      {/* Show all toggle */}
      {allPatterns.length > 5 && (
        <button
          onClick={() => setShowAll((v) => !v)}
          className="mt-3 text-sm text-blue-600 hover:text-blue-800 font-medium transition-colors"
        >
          {showAll ? '← Show top patterns only' : `Show all ${allPatterns.length} patterns →`}
        </button>
      )}
    </div>
  );
}

// ─── Past experiments section ─────────────────────────────────────────────────

function PastExperimentCard({ exp }: { exp: PastExperiment }) {
  const [open, setOpen] = useState(false);

  const statusColor =
    exp.status === 'completed'
      ? 'bg-green-100 text-green-700'
      : 'bg-amber-100 text-amber-700';

  const dateRange =
    exp.started_at || exp.ended_at
      ? `${fmtDate(exp.started_at)} – ${fmtDate(exp.ended_at)}`
      : null;

  return (
    <div className="border border-gray-200 rounded-xl overflow-hidden">
      <button
        onClick={() => setOpen((v) => !v)}
        className="w-full flex items-center justify-between px-5 py-4 bg-white hover:bg-gray-50 transition-colors text-left"
        type="button"
      >
        <div className="flex items-center gap-3 min-w-0">
          <span className={`text-xs font-semibold px-2 py-0.5 rounded-full flex-shrink-0 ${statusColor}`}>
            {exp.status === 'completed' ? 'Completed' : 'Abandoned'}
          </span>
          <span className="font-medium text-gray-800 truncate">{exp.title}</span>
        </div>
        <svg
          className={`w-4 h-4 text-gray-400 flex-shrink-0 transition-transform ${open ? 'rotate-180' : ''}`}
          viewBox="0 0 20 20"
          fill="currentColor"
        >
          <path fillRule="evenodd" d="M5.293 7.293a1 1 0 011.414 0L10 10.586l3.293-3.293a1 1 0 111.414 1.414l-4 4a1 1 0 01-1.414 0l-4-4a1 1 0 010-1.414z" clipRule="evenodd" />
        </svg>
      </button>

      {open && (
        <div className="px-5 py-4 bg-gray-50 border-t border-gray-200 grid grid-cols-2 gap-3 text-sm">
          <div>
            <span className="text-xs text-gray-500 uppercase tracking-wide">Pattern</span>
            <p className="font-medium text-gray-800 mt-0.5 flex items-center">
              {PATTERN_LABELS[exp.pattern_id] ?? exp.pattern_id}
              <InfoPopover patternId={exp.pattern_id} />
            </p>
          </div>
          {dateRange && (
            <div>
              <span className="text-xs text-gray-500 uppercase tracking-wide">Date range</span>
              <p className="font-medium text-gray-800 mt-0.5">{dateRange}</p>
            </div>
          )}
          {exp.attempt_count != null && (
            <div>
              <span className="text-xs text-gray-500 uppercase tracking-wide">Attempts</span>
              <p className="font-medium text-gray-800 mt-0.5">{exp.attempt_count}</p>
            </div>
          )}
          <div>
            <span className="text-xs text-gray-500 uppercase tracking-wide">ID</span>
            <p className="font-mono text-xs text-gray-500 mt-0.5">{exp.experiment_id}</p>
          </div>
        </div>
      )}
    </div>
  );
}

// ─── Page ─────────────────────────────────────────────────────────────────────

export default function ProgressPage() {
  const [data, setData] = useState<ClientProgress | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .getClientProgress()
      .then(setData)
      .catch((e) => setError(e?.message ?? 'Failed to load progress data.'))
      .finally(() => setLoading(false));
  }, []);

  return (
    <div className="max-w-4xl mx-auto space-y-8">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold text-gray-900">Your Progress</h1>
        <p className="text-gray-500 mt-1 text-sm">
          Pattern trends over time and your experiment history.
        </p>
      </div>

      {loading && (
        <div className="flex items-center gap-2 text-gray-400 text-sm py-12 justify-center">
          <svg className="w-4 h-4 animate-spin" viewBox="0 0 24 24" fill="none">
            <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
            <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z" />
          </svg>
          Loading your progress…
        </div>
      )}

      {error && (
        <div className="bg-red-50 border border-red-200 text-red-700 rounded-xl px-5 py-4 text-sm">
          {error}
        </div>
      )}

      {data && (
        <>
          {/* Pattern Trends */}
          <section className="bg-white rounded-2xl border border-gray-200 shadow-sm p-6">
            <h2 className="text-lg font-semibold text-gray-900 mb-5">Pattern Trends</h2>
            <PatternTrendsChart history={data.pattern_history} />
          </section>

          {/* Past Experiments */}
          <section className="bg-white rounded-2xl border border-gray-200 shadow-sm p-6">
            <h2 className="text-lg font-semibold text-gray-900 mb-5">Past Experiments</h2>
            {data.past_experiments.length === 0 ? (
              <p className="text-gray-400 text-sm">No completed or abandoned experiments yet.</p>
            ) : (
              <div className="space-y-3">
                {data.past_experiments.map((exp) => (
                  <PastExperimentCard key={exp.experiment_record_id} exp={exp} />
                ))}
              </div>
            )}
          </section>
        </>
      )}
    </div>
  );
}

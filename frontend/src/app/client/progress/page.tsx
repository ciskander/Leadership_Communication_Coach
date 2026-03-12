'use client';

import { useEffect, useState, useRef, useMemo, useCallback } from 'react';
import { api } from '@/lib/api';
import type { ClientProgress, RunHistoryPoint, PastExperiment } from '@/lib/types';
import { useActiveExperiment } from '@/hooks/useActiveExperiment';
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
  ReferenceLine,
} from 'recharts';
import { STRINGS } from '@/config/strings';
import { OnboardingTip } from '@/components/OnboardingTip';

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
          {STRINGS.patternExplanations[patternId] ?? STRINGS.common.noExplanationAvailable}
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

/** Raw data key for a pattern (faded dots). */
const rawKey = (pid: string) => `${pid}_raw`;

function buildChartData(
  history: RunHistoryPoint[],
  visiblePatterns: string[],
  windowSize: number,
): ChartPoint[] {
  // Pre-extract per-run data for each visible pattern
  const runData = history.map((run) => {
    const map: Record<string, { num: number; den: number; ratio: number }> = {};
    for (const p of run.patterns) {
      if (visiblePatterns.includes(p.pattern_id)) {
        const den = p.opportunity_count ?? 0;
        const num = den > 0 ? Math.round(p.ratio * den) : 0;
        map[p.pattern_id] = { num, den, ratio: p.ratio };
      }
    }
    return map;
  });

  return history.map((run, idx) => {
    const point: ChartPoint = {
      date: run.meeting_date ?? '',
      label: run.meeting_date ? fmtDate(run.meeting_date) : 'Unknown',
      isBaseline: run.is_baseline,
    };

    for (const pid of visiblePatterns) {
      // Raw value for this meeting
      const cur = runData[idx][pid];
      if (cur) {
        point[rawKey(pid)] = cur.den > 0
          ? Math.round((cur.num / cur.den) * 100)
          : Math.round(cur.ratio * 100);
      }

      // Rolling cumulative ratio over the trailing window
      let totalNum = 0;
      let totalDen = 0;
      let ratioSum = 0;
      let ratioCount = 0;
      const start = Math.max(0, idx - windowSize + 1);
      for (let j = start; j <= idx; j++) {
        const d = runData[j][pid];
        if (d) {
          totalNum += d.num;
          totalDen += d.den;
          ratioSum += d.ratio;
          ratioCount += 1;
        }
      }
      // Prefer denominator-weighted average; fall back to simple ratio average
      point[pid] = totalDen > 0
        ? Math.round((totalNum / totalDen) * 100)
        : ratioCount > 0
          ? Math.round((ratioSum / ratioCount) * 100)
          : null;
    }

    return point;
  });
}

type ViewMode = 'focus' | 'top5' | 'all';

function PatternTrendsChart({
  history,
  trendWindowSize = 3,
  experimentPatternId,
  viewMode,
}: {
  history: RunHistoryPoint[];
  trendWindowSize?: number;
  experimentPatternId?: string | null;
  viewMode: ViewMode;
}) {
  // Count post-baseline meetings — count non-baseline runs directly rather than
  // relying on sort position, so a missing/failed baseline run can't inflate the count.
  const hasBaseline = history.some((r) => r.is_baseline);
  const postBaselineCount = history.filter((r) => !r.is_baseline).length;
  const showLineChart = hasBaseline && postBaselineCount >= 3;

  // Aggregate opportunity counts across all runs to pick top patterns
  const { allPatterns, topPatterns } = useMemo(() => {
    const oppCounts: Record<string, number> = {};
    for (const run of history) {
      for (const p of run.patterns) {
        oppCounts[p.pattern_id] = (oppCounts[p.pattern_id] ?? 0) + p.opportunity_count;
      }
    }
    const all = Object.keys(oppCounts).sort((a, b) => oppCounts[b] - oppCounts[a]);
    return { allPatterns: all, topPatterns: all.slice(0, 5) };
  }, [history]);

  // Determine visible patterns based on view mode
  const hasExpPattern = experimentPatternId && allPatterns.includes(experimentPatternId);
  const visiblePatterns = useMemo(() => {
    if (viewMode === 'focus' && hasExpPattern) {
      return [experimentPatternId!];
    } else if (viewMode === 'all') {
      return allPatterns;
    } else {
      if (hasExpPattern && !topPatterns.includes(experimentPatternId!)) {
        return [...topPatterns, experimentPatternId!];
      }
      return topPatterns;
    }
  }, [viewMode, hasExpPattern, experimentPatternId, allPatterns, topPatterns]);

  // Stable color mapping: always based on position in allPatterns so colors
  // don't shift when filtering to experiment-only view.
  const patternColor = useCallback(
    (pid: string) => LINE_COLORS[allPatterns.indexOf(pid) % LINE_COLORS.length],
    [allPatterns],
  );

  const chartData = useMemo(() => buildChartData(history, allPatterns, trendWindowSize), [history, allPatterns, trendWindowSize]);
  const baselinePoint = useMemo(() => chartData.find((p) => p.isBaseline), [chartData]);

  // Custom tooltip — show trend line values; raw dots are hidden from tooltip
  const renderCustomTooltip = useCallback(({ active, payload, label }: any) => {
    if (!active || !payload?.length) return null;
    // Only show trend lines (not raw dot series)
    const trendEntries = payload.filter((e: any) => !e.dataKey.endsWith('_raw'));
    if (!trendEntries.length) return null;
    return (
      <div className="bg-white border border-gray-200 rounded-lg shadow-lg p-3 text-sm min-w-[200px]">
        <p className="font-semibold text-gray-700 mb-1">{label}</p>
        {trendEntries.map((entry: any) => {
          const rawEntry = payload.find((e: any) => e.dataKey === rawKey(entry.dataKey));
          const rawVal = rawEntry?.value;
          return (
            <div key={entry.dataKey} className="flex justify-between gap-4">
              <span style={{ color: entry.color }}>{STRINGS.patternLabels[entry.dataKey] ?? entry.dataKey}</span>
              <span className="font-medium">
                {entry.value != null ? `${entry.value}%` : '—'}
                {rawVal != null && rawVal !== entry.value && (
                  <span className="text-gray-400 font-normal ml-1">({rawVal}%)</span>
                )}
              </span>
            </div>
          );
        })}
      </div>
    );
  }, []);

  if (history.length === 0) {
    return (
      <div className="flex items-center justify-center h-48 text-gray-400 text-sm">
        {STRINGS.progressPage.noRunData}
      </div>
    );
  }

  return (
    <div>
      {/* Chart */}
      {showLineChart ? (
        <>
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
              <Tooltip content={renderCustomTooltip} />
              {visiblePatterns.map((pid) => {
                const color = patternColor(pid);
                const isExp = pid === experimentPatternId;
                return [
                  /* Faded raw dots — no connecting line */
                  <Line
                    key={`${pid}_raw`}
                    type="monotone"
                    dataKey={rawKey(pid)}
                    stroke="none"
                    dot={{ r: isExp ? 3.5 : 2.5, fill: color, opacity: isExp ? 0.5 : 0.3 }}
                    activeDot={false}
                    connectNulls={false}
                    legendType="none"
                    isAnimationActive={false}
                  />,
                  /* Bold trend line — thicker for experiment pattern */
                  <Line
                    key={pid}
                    type="monotone"
                    dataKey={pid}
                    stroke={color}
                    strokeWidth={isExp ? 3.5 : 2}
                    dot={false}
                    activeDot={{ r: isExp ? 7 : 5, fill: color }}
                    connectNulls
                    isAnimationActive={false}
                  />,
                ];
              })}
              {/* Vertical dashed line separating baseline from post-baseline */}
              {baselinePoint && (
                <ReferenceLine
                  x={baselinePoint.label}
                  stroke="#9ca3af"
                  strokeDasharray="4 4"
                  label={{ value: STRINGS.progressPage.baseline, position: 'insideTopRight', fontSize: 10, fill: '#6b7280' }}
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
                name: STRINGS.patternLabels[pid] ?? pid,
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
                  {STRINGS.progressPage.meetingsUntilTrends(meetingsUntil)}
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
                      formatter={(v: number | undefined) => [`${v ?? 0}%`, STRINGS.progressPage.score]}
                      cursor={{ fill: '#f9fafb' }}
                    />
                    <Bar dataKey="score" radius={[4, 4, 0, 0]} maxBarSize={48}>
                      {barData.map((entry) => {
                        const isExp = entry.pid === experimentPatternId;
                        const color = patternColor(entry.pid);
                        return (
                          <Cell
                            key={entry.pid}
                            fill={color}
                            stroke={isExp ? color : undefined}
                            strokeWidth={isExp ? 2 : 0}
                            opacity={isExp ? 1 : 0.75}
                          />
                        );
                      })}
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              </>
            );
          })()}
        </>
      )}

      {/* Pattern legend with ⓘ */}
      <div className="flex flex-wrap gap-3 mt-4">
        {visiblePatterns.map((pid) => {
          const isExp = pid === experimentPatternId;
          return (
            <span key={pid} className={`flex items-center text-sm ${isExp ? 'font-semibold text-gray-900' : 'text-gray-700'}`}>
              <span
                className={`inline-block rounded-full mr-1.5 flex-shrink-0 ${isExp ? 'w-3.5 h-3.5 ring-2 ring-offset-1 ring-current' : 'w-3 h-3'}`}
                style={{ background: patternColor(pid) }}
              />
              {STRINGS.patternLabels[pid] ?? pid}
              {isExp && (
                <span className="ml-1.5 text-[10px] font-semibold uppercase tracking-wide bg-indigo-100 text-indigo-700 px-1.5 py-0.5 rounded-full leading-none">
                  {STRINGS.progressPage.experimentBadge}
                </span>
              )}
              <InfoPopover patternId={pid} />
            </span>
          );
        })}
      </div>
    </div>
  );
}

// ─── Past experiments section ─────────────────────────────────────────────────

function PastExperimentCard({
  exp,
  patternHistory,
  trendWindowSize,
}: {
  exp: PastExperiment;
  patternHistory: RunHistoryPoint[];
  trendWindowSize: number;
}) {
  const [open, setOpen] = useState(false);

  const statusColor =
    exp.status === 'completed'
      ? 'bg-green-100 text-green-700'
      : exp.status === 'parked'
        ? 'bg-amber-100 text-amber-700'
        : 'bg-rose-100 text-rose-700';

  const dateRange =
    exp.started_at || exp.ended_at
      ? `${fmtDate(exp.started_at)} – ${fmtDate(exp.ended_at)}`
      : null;

  // Filter history to runs within the experiment's date range
  const expHistory = patternHistory.filter((run) => {
    if (!run.meeting_date) return false;
    if (exp.started_at && run.meeting_date < exp.started_at) return false;
    if (exp.ended_at && run.meeting_date > exp.ended_at) return false;
    return run.patterns.some((p) => p.pattern_id === exp.pattern_id);
  });

  const pid = exp.pattern_id;
  const color = '#2563eb';
  const chartData = expHistory.length > 0 ? buildChartData(expHistory, [pid], trendWindowSize) : [];

  return (
    <div className="border border-gray-200 rounded-xl overflow-hidden">
      <button
        onClick={() => setOpen((v) => !v)}
        className="w-full flex items-center justify-between px-5 py-4 bg-white hover:bg-gray-50 transition-colors text-left"
        type="button"
      >
        <div className="flex items-center gap-3 min-w-0">
          <span className={`text-xs font-semibold px-2 py-0.5 rounded-full flex-shrink-0 ${statusColor}`}>
            {exp.status === 'completed' ? STRINGS.experimentStatus.completed : exp.status === 'parked' ? STRINGS.experimentStatus.parked : STRINGS.experimentStatus.abandoned}
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
        <div className="px-5 py-4 bg-gray-50 border-t border-gray-200 space-y-4">
          <div className="grid grid-cols-2 gap-3 text-sm">
            <div>
              <span className="text-xs text-gray-500 uppercase tracking-wide">{STRINGS.progressPage.pattern}</span>
              <p className="font-medium text-gray-800 mt-0.5 flex items-center">
                {STRINGS.patternLabels[pid] ?? pid}
                <InfoPopover patternId={pid} />
              </p>
            </div>
            {dateRange && (
              <div>
                <span className="text-xs text-gray-500 uppercase tracking-wide">{STRINGS.progressPage.dateRange}</span>
                <p className="font-medium text-gray-800 mt-0.5">{dateRange}</p>
              </div>
            )}
            {exp.attempt_count != null && (
              <div>
                <span className="text-xs text-gray-500 uppercase tracking-wide">{STRINGS.progressPage.attempts}</span>
                <p className="font-medium text-gray-800 mt-0.5">
                  {STRINGS.progressPage.attemptsAcross(exp.attempt_count!, exp.meeting_count ?? 0)}
                </p>
              </div>
            )}
            <div>
              <span className="text-xs text-gray-500 uppercase tracking-wide">{STRINGS.progressPage.id}</span>
              <p className="font-mono text-xs text-gray-500 mt-0.5">{exp.experiment_id}</p>
            </div>
          </div>

          {/* Mini trend chart for this experiment's pattern */}
          {chartData.length >= 2 ? (
            <div>
              <p className="text-xs text-gray-500 uppercase tracking-wide mb-2">
                {STRINGS.progressPage.duringExperiment(STRINGS.patternLabels[pid] ?? pid)}
              </p>
              <ResponsiveContainer width="100%" height={160}>
                <LineChart data={chartData} margin={{ top: 4, right: 12, left: 0, bottom: 0 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
                  <XAxis dataKey="label" tick={{ fontSize: 10, fill: '#9ca3af' }} tickLine={false} />
                  <YAxis
                    domain={[0, 100]}
                    tickFormatter={(v) => `${v}%`}
                    tick={{ fontSize: 10, fill: '#9ca3af' }}
                    tickLine={false}
                    axisLine={false}
                  />
                  <Tooltip
                    formatter={(v: any) => [v != null ? `${v}%` : '—', STRINGS.patternLabels[pid] ?? pid]}
                    labelStyle={{ fontSize: 11 }}
                  />
                  <Line
                    type="monotone"
                    dataKey={rawKey(pid)}
                    stroke="none"
                    dot={{ r: 2, fill: color, opacity: 0.3 }}
                    activeDot={false}
                    connectNulls={false}
                    legendType="none"
                    isAnimationActive={false}
                  />
                  <Line
                    type="monotone"
                    dataKey={pid}
                    stroke={color}
                    strokeWidth={2}
                    dot={false}
                    activeDot={{ r: 4, fill: color }}
                    connectNulls
                  />
                </LineChart>
              </ResponsiveContainer>
            </div>
          ) : chartData.length === 1 ? (
            <div>
              <p className="text-xs text-gray-500 uppercase tracking-wide mb-1">
                {STRINGS.progressPage.duringExperiment(STRINGS.patternLabels[pid] ?? pid)}
              </p>
              <p className="text-sm font-medium text-gray-800">
                {chartData[0][pid] != null ? `${chartData[0][pid]}%` : '—'}
                <span className="text-gray-400 font-normal ml-1">{STRINGS.progressPage.oneMeeting}</span>
              </p>
            </div>
          ) : null}
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
  const [viewMode, setViewMode] = useState<ViewMode>('top5');
  const { data: activeExp } = useActiveExperiment();

  const experimentPatternId = activeExp?.experiment?.pattern_id ?? null;
  const hasExpPattern = !!experimentPatternId;

  useEffect(() => {
    api
      .getClientProgress()
      .then(setData)
      .catch((e) => setError(e?.message ?? STRINGS.progressPage.errorFallback))
      .finally(() => setLoading(false));
  }, []);

  // Fall back to top5 if focus is selected but there's no active experiment
  const effectiveViewMode = viewMode === 'focus' && !hasExpPattern ? 'top5' : viewMode;

  const viewOptions: { key: ViewMode; label: string; disabled?: boolean }[] = [
    { key: 'focus', label: STRINGS.progressPage.focusPatternOnly, disabled: !hasExpPattern },
    { key: 'top5', label: STRINGS.progressPage.top5Patterns },
    { key: 'all', label: STRINGS.progressPage.allPatterns },
  ];

  return (
    <div className="max-w-4xl mx-auto space-y-8">
      <OnboardingTip tipId="progress" message={STRINGS.onboarding.tipProgress} />
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold text-gray-900">{STRINGS.progressPage.heading}</h1>
        <p className="text-gray-500 mt-1 text-sm">
          {STRINGS.progressPage.subtitle}
        </p>
      </div>

      {loading && (
        <div className="flex items-center gap-2 text-gray-400 text-sm py-12 justify-center">
          <svg className="w-4 h-4 animate-spin" viewBox="0 0 24 24" fill="none">
            <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
            <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z" />
          </svg>
          {STRINGS.progressPage.loading}
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
            <div className="flex items-center justify-between mb-5">
              <h2 className="text-lg font-semibold text-gray-900">{STRINGS.progressPage.patternTrends}</h2>
              <div className="inline-flex rounded-lg border border-gray-200 overflow-hidden">
                {viewOptions.map(({ key, label, disabled }) => (
                  <button
                    key={key}
                    onClick={() => setViewMode(key)}
                    disabled={disabled}
                    className={`px-3 py-1.5 text-xs font-medium transition-colors border-r last:border-r-0 border-gray-200 ${
                      effectiveViewMode === key
                        ? 'bg-gray-900 text-white'
                        : disabled
                          ? 'bg-white text-gray-300 cursor-not-allowed'
                          : 'bg-white text-gray-600 hover:bg-gray-50'
                    }`}
                  >
                    {label}
                  </button>
                ))}
              </div>
            </div>
            <PatternTrendsChart history={data.pattern_history} trendWindowSize={data.trend_window_size} experimentPatternId={experimentPatternId} viewMode={effectiveViewMode} />
          </section>

          {/* Past Experiments */}
          <section className="bg-white rounded-2xl border border-gray-200 shadow-sm p-6">
            <h2 className="text-lg font-semibold text-gray-900 mb-5">{STRINGS.progressPage.pastExperiments}</h2>
            {data.past_experiments.length === 0 ? (
              <p className="text-gray-400 text-sm">{STRINGS.progressPage.noPastExperiments}</p>
            ) : (
              <div className="space-y-3">
                {data.past_experiments.map((exp) => (
                  <PastExperimentCard key={exp.experiment_record_id} exp={exp} patternHistory={data.pattern_history} trendWindowSize={data.trend_window_size} />
                ))}
              </div>
            )}
          </section>
        </>
      )}
    </div>
  );
}

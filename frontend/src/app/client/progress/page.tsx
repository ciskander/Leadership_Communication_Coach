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
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  ReferenceLine,
} from 'recharts';
import { STRINGS } from '@/config/strings';
import { S, CHART_COLORS } from '@/config/styles';
import { OnboardingTip } from '@/components/OnboardingTip';

// ─── Chart color palette — cv-aligned ────────────────────────────────────────

const LINE_COLORS = CHART_COLORS;

// ─── Helpers ──────────────────────────────────────────────────────────────────

function fmtDate(dateStr: string | null | undefined): string {
  if (!dateStr) return '—';
  try {
    return new Date(dateStr).toLocaleDateString('en-GB', {
      day: 'numeric', month: 'short', year: 'numeric',
    });
  } catch {
    return dateStr;
  }
}

const rawKey = (pid: string) => `${pid}_raw`;

// ─── Info popover ─────────────────────────────────────────────────────────────

const HOVER_DELAY_MS = 400;

function InfoPopover({ patternId, hoverColor }: { patternId: string; hoverColor?: string }) {
  const [open, setOpen] = useState(false);
  const [pinned, setPinned] = useState(false);
  const [hovered, setHovered] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  const hoverTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const leaveTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    if (!open) return;
    const handler = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) {
        setOpen(false);
        setPinned(false);
      }
    };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, [open]);

  const handleMouseEnter = () => {
    setHovered(true);
    if (leaveTimer.current) { clearTimeout(leaveTimer.current); leaveTimer.current = null; }
    hoverTimer.current = setTimeout(() => setOpen(true), HOVER_DELAY_MS);
  };

  const handleMouseLeave = () => {
    setHovered(false);
    if (hoverTimer.current) { clearTimeout(hoverTimer.current); hoverTimer.current = null; }
    if (!pinned) {
      leaveTimer.current = setTimeout(() => setOpen(false), 200);
    }
  };

  useEffect(() => {
    return () => {
      if (hoverTimer.current) clearTimeout(hoverTimer.current);
      if (leaveTimer.current) clearTimeout(leaveTimer.current);
    };
  }, []);

  return (
    <span className="relative inline-block" ref={ref}>
      <button
        onClick={() => { setPinned((v) => !v); setOpen((v) => !v); }}
        onMouseEnter={handleMouseEnter}
        onMouseLeave={handleMouseLeave}
        className="ml-1 text-cv-stone-400 transition-colors align-middle leading-none"
        style={hovered && hoverColor ? { color: hoverColor } : undefined}
        aria-label="Pattern explanation"
        type="button"
      >
        <svg className="w-3.5 h-3.5 inline" viewBox="0 0 20 20" fill="currentColor" aria-hidden="true">
          <path fillRule="evenodd" d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7-4a1 1 0 11-2 0 1 1 0 012 0zM9 9a1 1 0 000 2v3a1 1 0 001 1h1a1 1 0 100-2v-3a1 1 0 00-1-1H9z" clipRule="evenodd" />
        </svg>
      </button>
      {open && (
        <div
          className="absolute z-50 left-5 top-0 w-64 bg-white border border-cv-warm-300 rounded shadow-lg p-3 text-sm text-cv-stone-700 leading-snug"
          onMouseEnter={() => { if (leaveTimer.current) { clearTimeout(leaveTimer.current); leaveTimer.current = null; } }}
          onMouseLeave={() => { if (!pinned) { leaveTimer.current = setTimeout(() => setOpen(false), 200); } }}
        >
          {STRINGS.patternExplanations[patternId] ?? STRINGS.common.noExplanationAvailable}
        </div>
      )}
    </span>
  );
}

// ─── Chart data builder ───────────────────────────────────────────────────────

interface ChartPoint {
  date: string;
  label: string;
  isBaseline: boolean;
  [patternId: string]: string | number | boolean | null;
}

function buildChartData(
  history: RunHistoryPoint[],
  visiblePatterns: string[],
  windowSize: number,
): ChartPoint[] {
  const runData = history.map((run) => {
    const map: Record<string, { num: number; den: number; score: number }> = {};
    for (const p of run.patterns) {
      if (visiblePatterns.includes(p.pattern_id)) {
        const den = p.opportunity_count ?? 0;
        const num = den > 0 ? p.score * den : 0;
        map[p.pattern_id] = { num, den, score: p.score };
      }
    }
    return map;
  });

  return history.map((run, idx) => {
    const point: ChartPoint = {
      date:       run.meeting_date ?? '',
      label:      run.is_baseline
                    ? STRINGS.progressPage.baseline
                    : run.meeting_date ? fmtDate(run.meeting_date) : 'Unknown',
      isBaseline: run.is_baseline,
    };

    for (const pid of visiblePatterns) {
      const cur = runData[idx][pid];
      if (cur) {
        point[rawKey(pid)] = cur.den > 0
          ? Math.round((cur.num / cur.den) * 100)
          : Math.round(cur.score * 100);
      }

      let totalNum = 0, totalDen = 0, scoreSum = 0, scoreCount = 0;
      const start = Math.max(0, idx - windowSize + 1);
      for (let j = start; j <= idx; j++) {
        const d = runData[j][pid];
        if (d) { totalNum += d.num; totalDen += d.den; scoreSum += d.score; scoreCount++; }
      }
      point[pid] = totalDen > 0
        ? Math.round((totalNum / totalDen) * 100)
        : scoreCount > 0
          ? Math.round((scoreSum / scoreCount) * 100)
          : null;
    }

    return point;
  });
}

// ─── Pattern trends chart ─────────────────────────────────────────────────────

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
  const hasBaseline       = history.some((r) => r.is_baseline);
  const postBaselineCount = history.filter((r) => !r.is_baseline).length;
  const showLineChart     = hasBaseline && postBaselineCount >= 3;

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

  const hasExpPattern     = experimentPatternId && allPatterns.includes(experimentPatternId);
  const visiblePatterns   = useMemo(() => {
    if (viewMode === 'focus' && hasExpPattern) return [experimentPatternId!];
    if (viewMode === 'all') return allPatterns;
    if (hasExpPattern && !topPatterns.includes(experimentPatternId!)) return [...topPatterns, experimentPatternId!];
    return topPatterns;
  }, [viewMode, hasExpPattern, experimentPatternId, allPatterns, topPatterns]);

  const patternColor = useCallback(
    (pid: string) => LINE_COLORS[allPatterns.indexOf(pid) % LINE_COLORS.length],
    [allPatterns],
  );

  const chartData     = useMemo(() => buildChartData(history, allPatterns, trendWindowSize), [history, allPatterns, trendWindowSize]);
  const baselinePoint = useMemo(() => chartData.find((p) => p.isBaseline), [chartData]);

  // Custom tooltip — works for both line chart (trend + raw entries) and bar chart (raw-only)
  const renderCustomTooltip = useCallback(({ active, payload, label }: any) => {
    if (!active || !payload?.length) return null;
    const trendEntries = payload.filter((e: any) => !e.dataKey.endsWith('_raw'));
    const rawOnlyEntries = payload.filter((e: any) => e.dataKey.endsWith('_raw'));
    // Bar chart: only _raw entries; line chart: trend entries with optional raw detail
    const entries = trendEntries.length > 0 ? trendEntries : rawOnlyEntries;
    if (!entries.length) return null;
    return (
      <div className="bg-white border border-cv-warm-300 rounded shadow-lg p-3 text-sm min-w-[200px]">
        <p className="font-semibold text-cv-stone-700 mb-1.5">{label}</p>
        {entries.map((entry: any) => {
          const patternId = entry.dataKey.replace(/_raw$/, '');
          const rawEntry = trendEntries.length > 0
            ? payload.find((e: any) => e.dataKey === rawKey(patternId))
            : null;
          const rawVal = rawEntry?.value;
          return (
            <div key={entry.dataKey} className="flex justify-between gap-4">
              <span style={{ color: entry.color }} className="text-xs">{STRINGS.patternLabels[patternId] ?? patternId}</span>
              <span className="text-xs font-medium tabular-nums">
                {entry.value != null ? `${entry.value}%` : '—'}
                {rawVal != null && rawVal !== entry.value && (
                  <span className="text-cv-stone-400 font-normal ml-1">({rawVal}%)</span>
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
      <div className="flex items-center justify-center h-48 text-cv-stone-400 text-sm">
        {STRINGS.progressPage.noRunData}
      </div>
    );
  }

  const axisStyle = { fontSize: 11, fill: S.chartAxisFill };

  return (
    <div>
      {showLineChart ? (
        <ResponsiveContainer width="100%" height={280}>
          <LineChart data={chartData} margin={{ top: 8, right: 16, left: 0, bottom: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke={S.chartGrid} />
            <XAxis dataKey="label" tick={axisStyle} tickLine={false} />
            <YAxis domain={[0, 100]} tickFormatter={(v) => `${v}%`} tick={axisStyle} tickLine={false} axisLine={false} />
            <Tooltip content={renderCustomTooltip} />
            {visiblePatterns.map((pid) => {
              const color = patternColor(pid);
              const isExp = pid === experimentPatternId;
              return [
                <Line key={`${pid}_raw`} type="monotone" dataKey={rawKey(pid)} stroke="none"
                  dot={{ r: isExp ? 3.5 : 2.5, fill: color, opacity: isExp ? 0.5 : 0.3 }}
                  activeDot={false} connectNulls={false} legendType="none" isAnimationActive={false}
                />,
                <Line key={pid} type="monotone" dataKey={pid} stroke={color}
                  strokeWidth={isExp ? 3.5 : 2} dot={false}
                  activeDot={{ r: isExp ? 7 : 5, fill: color }}
                  connectNulls isAnimationActive={false}
                />,
              ];
            })}
            {baselinePoint && (
              <ReferenceLine
                x={baselinePoint.label}
                stroke={S.chartAxisFill}
                strokeDasharray="4 4"
                label={{ value: STRINGS.progressPage.baseline, position: 'insideTopRight', fontSize: 10, fill: '#78716C' }} /* cv-stone-500 */
              />
            )}
          </LineChart>
        </ResponsiveContainer>
      ) : (
        <>
          {(() => {
            const meetingsUntil = 3 - postBaselineCount;

            // Build pattern-grouped data: one row per pattern, one column per run
            const RUN_COLORS = [S.chartAxisFill, S.chartTeal, S.chartAmber, CHART_COLORS[2]]; // baseline=stone, then teal/amber/blue
            const runLabels = chartData.map((p) => p.label as string);
            const patternBarData = visiblePatterns.map((pid) => {
              const row: Record<string, string | number | null> = {
                pattern: STRINGS.patternLabels[pid] ?? pid,
                pid,
              };
              for (const cp of chartData) {
                row[cp.label as string] = (cp[rawKey(pid)] as number) ?? null;
              }
              return row;
            });

            return (
              <>
                {/* "N meetings until trends" nudge */}
                <div className="mb-3 inline-flex items-center gap-2 bg-cv-teal-50 text-cv-teal-700 border border-cv-teal-700 text-xs font-medium px-3 py-1.5 rounded-full">
                  <svg className="w-3.5 h-3.5" viewBox="0 0 20 20" fill="currentColor" aria-hidden="true">
                    <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm1-12a1 1 0 10-2 0v4a1 1 0 00.293.707l2.828 2.829a1 1 0 101.415-1.415L11 9.586V6z" clipRule="evenodd" />
                  </svg>
                  {STRINGS.progressPage.meetingsUntilTrends(meetingsUntil)}
                </div>
                <ResponsiveContainer width="100%" height={240}>
                  <BarChart data={patternBarData} margin={{ top: 4, right: 16, left: 0, bottom: 40 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke={S.chartGrid} vertical={false} />
                    <XAxis dataKey="pattern" tick={axisStyle} tickLine={false} angle={-30} textAnchor="end" interval={0} />
                    <YAxis domain={[0, 100]} tickFormatter={(v) => `${v}%`} tick={axisStyle} tickLine={false} axisLine={false} />
                    <Tooltip
                      cursor={{ fill: S.chartCursor }}
                      content={({ active, payload }: any) => {
                        if (!active || !payload?.length) return null;
                        const patternName = payload[0]?.payload?.pattern;
                        return (
                          <div className="bg-white border border-cv-warm-300 rounded shadow-lg p-3 text-sm min-w-[180px]">
                            <p className="font-semibold text-cv-stone-700 mb-1.5">{patternName}</p>
                            {payload.map((entry: any) => (
                              <div key={entry.dataKey} className="flex justify-between gap-4">
                                <span style={{ color: entry.fill }} className="text-xs">{entry.dataKey}</span>
                                <span className="text-xs font-medium tabular-nums">{entry.value != null ? `${entry.value}%` : '—'}</span>
                              </div>
                            ))}
                          </div>
                        );
                      }}
                    />
                    {runLabels.map((label, i) => (
                      <Bar key={label} dataKey={label} fill={RUN_COLORS[i % RUN_COLORS.length]}
                        radius={[4, 4, 0, 0]} maxBarSize={36}
                        opacity={i === 0 ? 0.6 : 0.9}
                      />
                    ))}
                  </BarChart>
                </ResponsiveContainer>

                {/* Run legend (replaces pattern legend for bar chart) */}
                <div className="flex flex-wrap gap-3 mt-4">
                  {runLabels.map((label, i) => (
                    <span key={label} className="flex items-center text-sm text-cv-stone-700">
                      <span className="inline-block w-3 h-3 rounded-full mr-1.5 shrink-0"
                        style={{ background: RUN_COLORS[i % RUN_COLORS.length], opacity: i === 0 ? 0.6 : 0.9 }}
                      />
                      {label}
                    </span>
                  ))}
                </div>
              </>
            );
          })()}
        </>
      )}

      {/* Pattern legend — line chart only (bar chart has its own run legend) */}
      {showLineChart && (
        <div className="flex flex-wrap gap-3 mt-4">
          {visiblePatterns.map((pid) => {
            const isExp = pid === experimentPatternId;
            return (
              <span key={pid} className={`flex items-center text-sm ${isExp ? 'font-semibold text-cv-stone-900' : 'text-cv-stone-700'}`}>
                <span
                  className={`inline-block rounded-full mr-1.5 shrink-0 ${isExp ? 'w-3.5 h-3.5 ring-2 ring-offset-1 ring-current' : 'w-3 h-3'}`}
                  style={{ background: patternColor(pid) }}
                />
                {STRINGS.patternLabels[pid] ?? pid}
                {isExp && (
                  <span className="ml-1.5 text-[10px] font-semibold uppercase tracking-wide bg-cv-teal-100 text-cv-teal-700 border border-cv-teal-700 px-1.5 py-0.5 rounded-full leading-none">
                    {STRINGS.progressPage.experimentBadge}
                  </span>
                )}
                <InfoPopover patternId={pid} hoverColor={patternColor(pid)} />
              </span>
            );
          })}
        </div>
      )}
    </div>
  );
}

// ─── Past experiment card ─────────────────────────────────────────────────────

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

  const statusCls =
    exp.status === 'completed' ? 'bg-cv-teal-100 text-cv-teal-700 border-cv-teal-700'
    : exp.status === 'parked'  ? 'bg-cv-amber-100 text-cv-amber-700 border-cv-amber-700'
    : 'bg-cv-red-100 text-cv-red-700 border-cv-red-700';

  const statusLabel =
    exp.status === 'completed' ? STRINGS.experimentStatus.completed
    : exp.status === 'parked'  ? STRINGS.experimentStatus.parked
    : STRINGS.experimentStatus.abandoned;

  const dateRange =
    exp.started_at || exp.ended_at
      ? `${fmtDate(exp.started_at)} – ${fmtDate(exp.ended_at)}`
      : null;

  const expHistory = patternHistory.filter((run) => {
    if (!run.meeting_date) return false;
    if (exp.started_at && run.meeting_date < exp.started_at) return false;
    if (exp.ended_at && run.meeting_date > exp.ended_at)     return false;
    return run.patterns.some((p) => p.pattern_id === exp.pattern_id);
  });

  const pid       = exp.pattern_id;
  const color     = LINE_COLORS[0]; // teal-600 for past-exp mini-charts
  const chartData = expHistory.length > 0 ? buildChartData(expHistory, [pid], trendWindowSize) : [];

  const axisStyle = { fontSize: 10, fill: S.chartAxisFill };

  return (
    <div className="border border-cv-warm-300 rounded overflow-hidden">
      {/* Row */}
      <button
        onClick={() => setOpen((v) => !v)}
        className="w-full flex items-center justify-between px-5 py-4 bg-white hover:bg-cv-warm-50 transition-colors text-left"
        type="button"
      >
        <div className="flex items-center gap-3 min-w-0">
          <span className={`text-2xs font-semibold px-2 py-0.5 rounded-full border shrink-0 ${statusCls}`}>
            {statusLabel}
          </span>
          <span className="font-medium text-cv-stone-800 truncate text-sm">{exp.title}</span>
        </div>
        <svg
          className={`w-4 h-4 text-cv-stone-400 shrink-0 transition-transform ${open ? 'rotate-180' : ''}`}
          viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth={2}
          strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"
        >
          <path d="M5 8l5 5 5-5" />
        </svg>
      </button>

      {/* Expanded */}
      {open && (
        <div className="px-5 py-4 bg-cv-warm-50 border-t border-cv-warm-300 space-y-4">
          <div className="grid grid-cols-2 gap-3 text-sm">
            <div>
              <span className="text-2xs font-semibold uppercase tracking-[0.12em] text-cv-stone-400">{STRINGS.progressPage.pattern}</span>
              <p className="font-medium text-cv-stone-800 mt-0.5 flex items-center">
                {STRINGS.patternLabels[pid] ?? pid}
                <InfoPopover patternId={pid} hoverColor={color} />
              </p>
            </div>
            {dateRange && (
              <div>
                <span className="text-2xs font-semibold uppercase tracking-[0.12em] text-cv-stone-400">{STRINGS.progressPage.dateRange}</span>
                <p className="font-medium text-cv-stone-800 mt-0.5">{dateRange}</p>
              </div>
            )}
            {exp.attempt_count != null && (
              <div>
                <span className="text-2xs font-semibold uppercase tracking-[0.12em] text-cv-stone-400">{STRINGS.progressPage.attempts}</span>
                <p className="font-medium text-cv-stone-800 mt-0.5">
                  {STRINGS.progressPage.attemptsAcross(exp.attempt_count!, exp.meeting_count ?? 0)}
                </p>
              </div>
            )}
            <div>
              <span className="text-2xs font-semibold uppercase tracking-[0.12em] text-cv-stone-400">{STRINGS.progressPage.id}</span>
              <p className="font-mono text-xs text-cv-stone-400 mt-0.5">{exp.experiment_id}</p>
            </div>
          </div>

          {/* Mini trend chart */}
          {chartData.length >= 2 ? (
            <div>
              <p className="text-2xs font-semibold uppercase tracking-[0.12em] text-cv-stone-400 mb-2">
                {STRINGS.progressPage.duringExperiment(STRINGS.patternLabels[pid] ?? pid)}
              </p>
              <ResponsiveContainer width="100%" height={160}>
                <LineChart data={chartData} margin={{ top: 4, right: 12, left: 0, bottom: 0 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke={S.chartGrid} />
                  <XAxis dataKey="label" tick={axisStyle} tickLine={false} />
                  <YAxis domain={[0, 100]} tickFormatter={(v) => `${v}%`} tick={axisStyle} tickLine={false} axisLine={false} />
                  <Tooltip formatter={(v: any) => [v != null ? `${v}%` : '—', STRINGS.patternLabels[pid] ?? pid]} labelStyle={{ fontSize: 11 }} />
                  <Line type="monotone" dataKey={rawKey(pid)} stroke="none"
                    dot={{ r: 2, fill: color, opacity: 0.3 }} activeDot={false}
                    connectNulls={false} legendType="none" isAnimationActive={false}
                  />
                  <Line type="monotone" dataKey={pid} stroke={color} strokeWidth={2}
                    dot={false} activeDot={{ r: 4, fill: color }} connectNulls
                  />
                </LineChart>
              </ResponsiveContainer>
            </div>
          ) : chartData.length === 1 ? (
            <div>
              <p className="text-2xs font-semibold uppercase tracking-[0.12em] text-cv-stone-400 mb-1">
                {STRINGS.progressPage.duringExperiment(STRINGS.patternLabels[pid] ?? pid)}
              </p>
              <p className="text-sm font-medium text-cv-stone-800">
                {chartData[0][pid] != null ? `${chartData[0][pid]}%` : '—'}
                <span className="text-cv-stone-400 font-normal ml-1">{STRINGS.progressPage.oneMeeting}</span>
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
  const [data, setData]     = useState<ClientProgress | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError]   = useState<string | null>(null);
  const [viewMode, setViewMode] = useState<ViewMode>('top5');
  const { data: activeExp } = useActiveExperiment();

  const experimentPatternId = activeExp?.experiment?.pattern_id ?? null;
  const hasExpPattern       = !!experimentPatternId;

  useEffect(() => {
    api.getClientProgress()
      .then(setData)
      .catch((e) => setError(e?.message ?? STRINGS.progressPage.errorFallback))
      .finally(() => setLoading(false));
  }, []);

  const effectiveViewMode = viewMode === 'focus' && !hasExpPattern ? 'top5' : viewMode;

  const viewOptions: { key: ViewMode; label: string; disabled?: boolean }[] = [
    { key: 'focus', label: STRINGS.progressPage.focusPatternOnly, disabled: !hasExpPattern },
    { key: 'top5',  label: STRINGS.progressPage.top5Patterns },
    { key: 'all',   label: STRINGS.progressPage.allPatterns },
  ];

  return (
    <div className="max-w-6xl mx-auto space-y-8">
      <OnboardingTip tipId="progress" message={STRINGS.onboarding.tipProgress} />

      {/* Header */}
      <div>
        <h1 className="font-serif text-2xl text-cv-stone-900">
          {STRINGS.progressPage.heading}
        </h1>
        <p className="text-cv-stone-500 mt-1 text-sm">{STRINGS.progressPage.subtitle}</p>
      </div>

      {/* Loading */}
      {loading && (
        <div className="flex items-center justify-center gap-2 text-cv-stone-400 text-sm py-12">
          <svg className="w-4 h-4 animate-spin" viewBox="0 0 24 24" fill="none" aria-hidden="true">
            <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
            <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z" />
          </svg>
          {STRINGS.progressPage.loading}
        </div>
      )}

      {/* Error */}
      {error && (
        <div className="bg-cv-red-50 border border-cv-red-200 text-cv-red-700 rounded px-5 py-4 text-sm">
          {error}
        </div>
      )}

      {data && (
        <>
          {/* Pattern Trends */}
          <section className="bg-white rounded border border-cv-warm-300 p-6">
            <div className="flex items-center justify-between mb-5">
              <h2 className="text-lg font-semibold text-cv-stone-900">{STRINGS.progressPage.patternTrends}</h2>

              {/* View mode pill selector */}
              <div className="inline-flex rounded border border-cv-warm-300 overflow-hidden">
                {viewOptions.map(({ key, label, disabled }) => (
                  <button
                    key={key}
                    onClick={() => setViewMode(key)}
                    disabled={disabled}
                    className={[
                      'px-3 py-1.5 text-xs font-medium transition-colors border-r last:border-r-0 border-cv-warm-300',
                      effectiveViewMode === key
                        ? 'bg-cv-stone-900 text-white'
                        : disabled
                          ? 'bg-white text-cv-stone-300 cursor-not-allowed'
                          : 'bg-white text-cv-stone-600 hover:bg-cv-warm-50',
                    ].join(' ')}
                  >
                    {label}
                  </button>
                ))}
              </div>
            </div>

            <PatternTrendsChart
              history={data.pattern_history}
              trendWindowSize={data.trend_window_size}
              experimentPatternId={experimentPatternId}
              viewMode={effectiveViewMode}
            />
          </section>

          {/* Past Experiments */}
          <section className="bg-white rounded border border-cv-warm-300 p-6">
            <h2 className="text-lg font-semibold text-cv-stone-900 mb-5">
              {STRINGS.progressPage.pastExperiments}
            </h2>
            {data.past_experiments.length === 0 ? (
              <p className="text-cv-stone-400 text-sm">{STRINGS.progressPage.noPastExperiments}</p>
            ) : (
              <div className="space-y-3">
                {data.past_experiments.map((exp) => (
                  <PastExperimentCard
                    key={exp.experiment_record_id}
                    exp={exp}
                    patternHistory={data.pattern_history}
                    trendWindowSize={data.trend_window_size}
                  />
                ))}
              </div>
            )}
          </section>
        </>
      )}
    </div>
  );
}

'use client';

import { STRINGS } from '@/config/strings';
import { useEffect, useState, useMemo, useCallback } from 'react';
import { useParams } from 'next/navigation';
import Link from 'next/link';
import { api } from '@/lib/api';
import type { CoacheeSummary, Experiment, ClientProgress, RunStatus, RunHistoryPoint } from '@/lib/types';
import { ExperimentTracker } from '@/components/ExperimentTracker';
import {
  LineChart, Line, BarChart, Bar,
  XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, ReferenceLine,
} from 'recharts';

// ─── Chart palette — cv-aligned ───────────────────────────────────────────────

const LINE_COLORS = [
  '#0F6E56', // cv-teal-600
  '#D97706', // cv-amber-600
  '#2563eb',
  '#7c3aed',
  '#0891b2',
  '#db2777',
  '#65a30d',
  '#ea580c',
  '#6b7280',
  '#16a34a',
];

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

function PatternLabel({ id }: { id: string }) {
  return (
    <span className="text-2xs font-semibold uppercase tracking-[0.14em] text-cv-teal-600">
      {STRINGS.patternLabels[id] ?? id.replace(/_/g, ' ')}
    </span>
  );
}

const rawKey = (pid: string) => `${pid}_raw`;

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
        const num = den > 0 ? Math.round(p.score * den) : 0;
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
        : scoreCount > 0 ? Math.round((scoreSum / scoreCount) * 100) : null;
    }
    return point;
  });
}

// ─── Section heading ──────────────────────────────────────────────────────────

function SectionHeading({ text }: { text: string }) {
  return (
    <h2 className="text-2xs font-semibold uppercase tracking-[0.14em] text-cv-stone-400 mb-3">
      {text}
    </h2>
  );
}

// ─── Pattern trends (compact) ─────────────────────────────────────────────────

function PatternTrendsCompact({
  history,
  trendWindowSize = 3,
  experimentPatternId,
}: {
  history: RunHistoryPoint[];
  trendWindowSize?: number;
  experimentPatternId?: string | null;
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

  const visiblePatterns = useMemo(() => {
    if (experimentPatternId && !topPatterns.includes(experimentPatternId)) {
      return [...topPatterns, experimentPatternId];
    }
    return topPatterns;
  }, [experimentPatternId, topPatterns]);

  const patternColor = useCallback(
    (pid: string) => LINE_COLORS[allPatterns.indexOf(pid) % LINE_COLORS.length],
    [allPatterns],
  );

  const chartData     = useMemo(() => buildChartData(history, allPatterns, trendWindowSize), [history, allPatterns, trendWindowSize]);
  const baselinePoint = useMemo(() => chartData.find((p) => p.isBaseline), [chartData]);

  if (history.length === 0) {
    return (
      <div className="flex items-center justify-center h-32 text-cv-stone-400 text-sm">
        {STRINGS.coacheeDetail.noProgressYet}
      </div>
    );
  }

  const axisStyle = { fontSize: 10, fill: '#A8A29E' };

  return (
    <div>
      {showLineChart ? (
        <ResponsiveContainer width="100%" height={220}>
          <LineChart data={chartData} margin={{ top: 8, right: 16, left: 0, bottom: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#EDE8E3" />
            <XAxis dataKey="label" tick={axisStyle} tickLine={false} />
            <YAxis domain={[0, 100]} tickFormatter={(v) => `${v}%`} tick={axisStyle} tickLine={false} axisLine={false} />
            <Tooltip
              content={({ active, payload, label }: any) => {
                if (!active || !payload?.length) return null;
                const trendEntries = payload.filter((e: any) => !e.dataKey.endsWith('_raw'));
                if (!trendEntries.length) return null;
                return (
                  <div className="bg-white border border-cv-warm-300 rounded shadow-lg p-2 text-xs min-w-[160px]">
                    <p className="font-semibold text-cv-stone-700 mb-1">{label}</p>
                    {trendEntries.map((entry: any) => (
                      <div key={entry.dataKey} className="flex justify-between gap-3">
                        <span style={{ color: entry.color }}>{STRINGS.patternLabels[entry.dataKey] ?? entry.dataKey}</span>
                        <span className="font-medium">{entry.value != null ? `${entry.value}%` : '—'}</span>
                      </div>
                    ))}
                  </div>
                );
              }}
            />
            {visiblePatterns.map((pid) => {
              const color = patternColor(pid);
              const isExp = pid === experimentPatternId;
              return [
                <Line key={`${pid}_raw`} type="monotone" dataKey={rawKey(pid)} stroke="none"
                  dot={{ r: isExp ? 3 : 2, fill: color, opacity: isExp ? 0.5 : 0.3 }}
                  activeDot={false} connectNulls={false} legendType="none" isAnimationActive={false}
                />,
                <Line key={pid} type="monotone" dataKey={pid} stroke={color}
                  strokeWidth={isExp ? 3 : 1.5} dot={false}
                  activeDot={{ r: isExp ? 6 : 4, fill: color }}
                  connectNulls isAnimationActive={false}
                />,
              ];
            })}
            {baselinePoint && (
              <ReferenceLine
                x={baselinePoint.label}
                stroke="#A8A29E"
                strokeDasharray="4 4"
                label={{ value: STRINGS.progressPage.baseline, position: 'insideTopRight', fontSize: 10, fill: '#78716C' }}
              />
            )}
          </LineChart>
        </ResponsiveContainer>
      ) : (
        (() => {
          const meetingsUntil = Math.max(0, 3 - postBaselineCount);

          // Build pattern-grouped data: one row per pattern, one column per run
          const RUN_COLORS = ['#A8A29E', '#0F6E56', '#D97706', '#2563eb'];
          const runLabels = chartData.map((p) => p.label as string);
          const patternBarData = visiblePatterns.map((pid) => {
            const row: Record<string, string | number | null> = {
              pattern: STRINGS.patternLabels[pid] ?? pid,
            };
            for (const cp of chartData) {
              row[cp.label as string] = (cp[rawKey(pid)] as number) ?? null;
            }
            return row;
          });

          return (
            <>
              {meetingsUntil > 0 && (
                <div className="mb-3 inline-flex items-center gap-2 bg-cv-teal-50 text-cv-teal-700 text-xs font-medium px-3 py-1.5 rounded-full">
                  {STRINGS.progressPage.meetingsUntilTrends(meetingsUntil)}
                </div>
              )}
              <ResponsiveContainer width="100%" height={180}>
                <BarChart data={patternBarData} margin={{ top: 4, right: 16, left: 0, bottom: 30 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#EDE8E3" vertical={false} />
                  <XAxis dataKey="pattern" tick={{ fontSize: 9, fill: '#A8A29E' }} tickLine={false} angle={-30} textAnchor="end" interval={0} />
                  <YAxis domain={[0, 100]} tickFormatter={(v) => `${v}%`} tick={axisStyle} tickLine={false} axisLine={false} />
                  <Tooltip
                    cursor={{ fill: '#F7F4F0' }}
                    content={({ active, payload }: any) => {
                      if (!active || !payload?.length) return null;
                      const patternName = payload[0]?.payload?.pattern;
                      return (
                        <div className="bg-white border border-cv-warm-300 rounded shadow-lg p-2 text-xs min-w-[140px]">
                          <p className="font-semibold text-cv-stone-700 mb-1">{patternName}</p>
                          {payload.map((entry: any) => (
                            <div key={entry.dataKey} className="flex justify-between gap-3">
                              <span style={{ color: entry.fill }}>{entry.dataKey}</span>
                              <span className="font-medium">{entry.value != null ? `${entry.value}%` : '—'}</span>
                            </div>
                          ))}
                        </div>
                      );
                    }}
                  />
                  {runLabels.map((label, i) => (
                    <Bar key={label} dataKey={label} fill={RUN_COLORS[i % RUN_COLORS.length]}
                      radius={[4, 4, 0, 0]} maxBarSize={28}
                      opacity={i === 0 ? 0.6 : 0.9}
                    />
                  ))}
                </BarChart>
              </ResponsiveContainer>

              {/* Run legend */}
              <div className="flex flex-wrap gap-2.5 mt-3">
                {runLabels.map((label, i) => (
                  <span key={label} className="flex items-center text-xs text-cv-stone-600">
                    <span className="inline-block w-2.5 h-2.5 rounded-full mr-1 shrink-0"
                      style={{ background: RUN_COLORS[i % RUN_COLORS.length], opacity: i === 0 ? 0.6 : 0.9 }}
                    />
                    {label}
                  </span>
                ))}
              </div>
            </>
          );
        })()
      )}

      {/* Pattern legend — line chart only (bar chart has its own run legend) */}
      {showLineChart && (
        <div className="flex flex-wrap gap-2.5 mt-3">
          {visiblePatterns.map((pid) => {
            const isExp = pid === experimentPatternId;
            return (
              <span key={pid} className={`flex items-center text-xs ${isExp ? 'font-semibold text-cv-stone-900' : 'text-cv-stone-600'}`}>
                <span className="inline-block w-2.5 h-2.5 rounded-full mr-1 shrink-0" style={{ background: patternColor(pid) }} />
                {STRINGS.patternLabels[pid] ?? pid}
                {isExp && (
                  <span className="ml-1 text-[9px] font-semibold uppercase tracking-wide bg-cv-teal-100 text-cv-teal-700 px-1 py-0.5 rounded-full leading-none">
                    Exp
                  </span>
                )}
              </span>
            );
          })}
        </div>
      )}
    </div>
  );
}

// ─── Proposed experiment row ──────────────────────────────────────────────────

function ProposedExperimentRow({ experiment }: { experiment: Experiment }) {
  return (
    <div className="bg-cv-warm-50 border border-cv-warm-300 rounded p-4 space-y-2">
      <div className="flex items-start justify-between gap-3">
        <div className="space-y-1 min-w-0">
          <PatternLabel id={experiment.pattern_id} />
          <p className="text-sm font-semibold text-cv-stone-800 leading-snug font-serif">
            {experiment.title}
          </p>
        </div>
        <span className="text-2xs px-2 py-0.5 rounded-full font-semibold bg-cv-warm-200 text-cv-stone-600 whitespace-nowrap shrink-0">
          {STRINGS.experimentStatus.proposed}
        </span>
      </div>
      <p className="text-xs text-cv-stone-500 leading-relaxed line-clamp-2">
        {experiment.instruction}
      </p>
    </div>
  );
}

// ─── Pattern snapshot bar ─────────────────────────────────────────────────────

function PatternSnapshotBar({ item }: { item: { pattern_id: string; score?: number | null; evaluable_status?: string } }) {
  const score = item.score;
  const pct   = score != null ? Math.round(score) : null;
  const label = STRINGS.patternLabels[item.pattern_id] ?? item.pattern_id.replace(/_/g, ' ');

  if (pct === null) {
    return (
      <div className="flex items-center justify-between text-xs py-0.5">
        <span className="text-cv-stone-500">{label}</span>
        <span className="text-cv-stone-300">{STRINGS.evaluableStatus[item.evaluable_status ?? ''] ?? '—'}</span>
      </div>
    );
  }

  const barColor = pct >= 70 ? 'bg-cv-teal-400' : pct >= 40 ? 'bg-cv-amber-400' : 'bg-cv-red-400';

  return (
    <div className="flex items-center gap-2 py-0.5">
      <span className="text-xs text-cv-stone-600 w-40 truncate shrink-0">{label}</span>
      <div className="flex-1 h-1.5 bg-cv-warm-200 rounded-full overflow-hidden">
        <div className={`h-full rounded-full ${barColor}`} style={{ width: `${pct}%` }} />
      </div>
      <span className="text-xs text-cv-stone-500 w-8 text-right tabular-nums">{pct}%</span>
    </div>
  );
}

// ─── Past experiment row ──────────────────────────────────────────────────────

function PastExperimentRow({ exp }: { exp: Record<string, unknown> }) {
  const statusCls =
    exp.status === 'completed' ? 'bg-cv-teal-100 text-cv-teal-700'
    : exp.status === 'parked'  ? 'bg-cv-amber-100 text-cv-amber-700'
    : 'bg-cv-red-100 text-cv-red-700';

  const dateRange =
    exp.started_at || exp.ended_at
      ? `${fmtDate(exp.started_at as string)} – ${fmtDate(exp.ended_at as string)}`
      : null;

  return (
    <div className="flex items-center justify-between px-4 py-3 bg-white border border-cv-warm-300 rounded">
      <div className="flex items-center gap-3 min-w-0">
        <span className={`text-2xs font-semibold px-2 py-0.5 rounded-full shrink-0 ${statusCls}`}>
          {STRINGS.experimentStatus[exp.status as string] ?? exp.status}
        </span>
        <div className="min-w-0">
          <p className="text-sm font-medium text-cv-stone-800 truncate">{exp.title as string}</p>
          <p className="text-xs text-cv-stone-400">
            {STRINGS.patternLabels[exp.pattern_id as string] ?? exp.pattern_id}
            {exp.attempt_count != null && ` · ${STRINGS.progressPage.attemptsAcross(exp.attempt_count as number, (exp.meeting_count as number) ?? 0)}`}
          </p>
        </div>
      </div>
      {dateRange && (
        <span className="text-xs text-cv-stone-400 whitespace-nowrap ml-3">{dateRange}</span>
      )}
    </div>
  );
}

// ─── Recent run row ───────────────────────────────────────────────────────────

function RunRow({ run }: { run: Record<string, unknown> }) {
  const [expanded, setExpanded]       = useState(false);
  const [runDetail, setRunDetail]     = useState<RunStatus | null>(null);
  const [loadingDetail, setLoadingDetail] = useState(false);

  const runId        = (run.run_id as string) ?? (run.id as string);
  const gate1Pass    = run.gate1_pass as boolean | null;
  const title        = run.title as string | undefined;
  const meetingDate  = run.meeting_date as string | undefined;
  const meetingType  = run.meeting_type as string | undefined;
  const analysisType = run.analysis_type as string | undefined;
  const focusPattern = run.focus_pattern as string | undefined;

  const displayTitle = title
    || (meetingType ? meetingType.replace(/_/g, ' ').replace(/\b\w/g, (l: string) => l.toUpperCase()) : null)
    || STRINGS.common.meeting;

  const isBaseline = analysisType === 'baseline_pack';

  const handleToggle = () => {
    if (!expanded && !runDetail && runId) {
      setLoadingDetail(true);
      api.getRun(runId).then(setRunDetail).catch(() => {}).finally(() => setLoadingDetail(false));
    }
    setExpanded((v) => !v);
  };

  return (
    <div className="border border-cv-warm-300 rounded overflow-hidden">
      {/* Row header */}
      <button
        onClick={handleToggle}
        className="w-full flex items-center justify-between px-4 py-3 bg-white hover:bg-cv-warm-50 transition-colors text-left"
        type="button"
      >
        <div className="flex items-center gap-2.5 min-w-0">
          {gate1Pass === false && (
            <span className="text-2xs px-2 py-0.5 rounded-full font-semibold bg-cv-amber-100 text-cv-amber-700 whitespace-nowrap shrink-0">
              {STRINGS.coacheeDetail.gateFailLabel}
            </span>
          )}
          {isBaseline && (
            <span className="text-2xs px-2 py-0.5 rounded-full font-semibold bg-cv-teal-100 text-cv-teal-700 whitespace-nowrap shrink-0">
              {STRINGS.common.baselinePackAnalysis}
            </span>
          )}
          <span className="text-sm font-medium text-cv-stone-800 truncate">{displayTitle}</span>
          {focusPattern && gate1Pass !== false && (
            <span className="text-xs text-cv-stone-400 whitespace-nowrap shrink-0">
              Focus: {STRINGS.patternLabels[focusPattern] ?? focusPattern.replace(/_/g, ' ')}
            </span>
          )}
        </div>
        <div className="flex items-center gap-2 shrink-0 ml-3">
          <span className="text-xs text-cv-stone-400">{meetingDate ? fmtDate(meetingDate) : ''}</span>
          <svg
            className={`w-4 h-4 text-cv-stone-400 transition-transform ${expanded ? 'rotate-180' : ''}`}
            viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth={2}
            strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"
          >
            <path d="M5 8l5 5 5-5" />
          </svg>
        </div>
      </button>

      {/* Expanded detail */}
      {expanded && (
        <div className="px-4 py-4 bg-cv-warm-50 border-t border-cv-warm-300 space-y-4">
          {loadingDetail && (
            <div className="flex items-center gap-2 text-cv-stone-400 text-sm py-4 justify-center">
              <span className="w-4 h-4 border-2 border-cv-teal-500 border-t-transparent rounded-full animate-spin" />
              {STRINGS.common.loading}
            </div>
          )}

          {runDetail && runDetail.status === 'complete' && gate1Pass !== false && (
            <>
              {runDetail.pattern_snapshot && runDetail.pattern_snapshot.length > 0 && (
                <div>
                  <p className="text-2xs font-semibold uppercase tracking-[0.14em] text-cv-stone-400 mb-2">
                    {STRINGS.runStatusPoller.patternSnapshot}
                  </p>
                  <div className="space-y-1">
                    {runDetail.pattern_snapshot.map((item) => (
                      <PatternSnapshotBar key={item.pattern_id} item={item} />
                    ))}
                  </div>
                </div>
              )}

              {runDetail.strengths.length > 0 && (
                <div>
                  <p className="text-2xs font-semibold uppercase tracking-[0.14em] text-cv-teal-50 bg-cv-teal-800 inline-block px-2 py-0.5 rounded mb-1.5">
                    {STRINGS.coachingCard.strengthsHeading}
                  </p>
                  {runDetail.strengths.map((s, i) => (
                    <div key={i} className="mb-2">
                      <p className="text-xs text-cv-stone-500 font-medium">
                        {STRINGS.patternLabels[s.pattern_id] ?? s.pattern_id}
                      </p>
                      <p className="text-sm text-cv-stone-700">{s.message}</p>
                    </div>
                  ))}
                </div>
              )}

              {runDetail.focus && (
                <div>
                  <p className="text-2xs font-semibold uppercase tracking-[0.14em] text-cv-amber-50 bg-cv-amber-800 inline-block px-2 py-0.5 rounded mb-1.5">
                    {STRINGS.coachingCard.focusHeading}
                  </p>
                  <p className="text-xs text-cv-amber-800 font-medium">
                    {STRINGS.patternLabels[runDetail.focus.pattern_id] ?? runDetail.focus.pattern_id}
                  </p>
                  <p className="text-sm text-cv-stone-700">{runDetail.focus.message}</p>
                  {(() => {
                    const rewrite = runDetail.pattern_snapshot?.find(
                      (ps) => ps.pattern_id === runDetail.focus!.pattern_id
                    )?.suggested_rewrite;
                    return rewrite ? (
                      <div className="mt-1.5 bg-cv-teal-50 border border-cv-teal-100 rounded px-3 py-2">
                        <p className="text-2xs font-semibold text-cv-teal-600 mb-0.5">{STRINGS.common.nextTimeTry}</p>
                        <p className="text-sm text-cv-teal-800 italic">{rewrite}</p>
                      </div>
                    ) : null;
                  })()}
                </div>
              )}

              {runDetail.experiment_detection && (
                <div className="bg-cv-warm-100 border border-cv-warm-300 rounded px-3 py-2">
                  <p className="text-2xs font-semibold text-cv-stone-600 mb-0.5">
                    {runDetail.experiment_detection.attempt === 'yes'
                      ? STRINGS.runStatusPoller.nicelyDone
                      : runDetail.experiment_detection.attempt === 'partial'
                        ? STRINGS.runStatusPoller.partialAttemptDetected
                        : STRINGS.runStatusPoller.noAttemptDetected}
                  </p>
                  {runDetail.experiment_detection.coaching_note && (
                    <p className="text-sm text-cv-stone-700">{runDetail.experiment_detection.coaching_note}</p>
                  )}
                </div>
              )}
            </>
          )}

          {runDetail && runDetail.status === 'complete' && gate1Pass === false && (
            <p className="text-sm text-cv-amber-600">{STRINGS.runStatusPoller.qualityCheckDesc}</p>
          )}
          {runDetail && runDetail.status === 'error' && (
            <p className="text-sm text-cv-red-600">{STRINGS.runStatusPoller.errorFallback}</p>
          )}
        </div>
      )}
    </div>
  );
}

// ─── Page ─────────────────────────────────────────────────────────────────────

export default function CoacheeDetailPage() {
  const { id } = useParams<{ id: string }>();
  const [data, setData]                     = useState<CoacheeSummary | null>(null);
  const [progress, setProgress]             = useState<ClientProgress | null>(null);
  const [loading, setLoading]               = useState(true);
  const [progressLoading, setProgressLoading] = useState(true);

  useEffect(() => {
    api.getCoacheeSummary(id).then(setData).finally(() => setLoading(false));
    api.getCoacheeProgress(id).then(setProgress).catch(() => {}).finally(() => setProgressLoading(false));
  }, [id]);

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <span className="w-8 h-8 border-2 border-cv-teal-600 border-t-transparent rounded-full animate-spin" />
      </div>
    );
  }

  if (!data) return <p className="text-sm text-cv-stone-500">{STRINGS.coacheeDetail.coacheeNotFound}</p>;

  const proposedExperiments  = data.proposed_experiments ?? [];
  const experimentPatternId  = data.active_experiment?.pattern_id ?? null;

  // Shared card shell
  const cardCls = 'bg-white rounded border border-cv-warm-300 p-5';

  return (
    <div className="max-w-5xl mx-auto space-y-8 py-2">
      {/* Back + header */}
      <div>
        <Link href="/coach" className="text-sm text-cv-stone-500 hover:text-cv-stone-700 transition-colors">
          ← {STRINGS.coacheeDetail.backToDashboard}
        </Link>
        <div className="flex items-start justify-between mt-2">
          <div>
            <h1 className="font-serif text-2xl text-cv-stone-900">
              {data.coachee.display_name ?? data.coachee.email}
            </h1>
            <p className="text-sm text-cv-stone-500">{data.coachee.email}</p>
          </div>
          <Link
            href={`/coach/analyze?coachee=${id}`}
            className="flex items-center gap-2 px-4 py-2 bg-cv-navy-600 text-white rounded text-sm font-medium hover:bg-cv-navy-700 transition-colors shadow-sm"
          >
            <span className="shrink-0"><svg viewBox="0 0 16 16" fill="none" className="w-4 h-4 shrink-0" aria-hidden="true"><path d="M8 1v3M8 12v3M1 8h3M12 8h3M3.05 3.05l2.12 2.12M10.83 10.83l2.12 2.12M3.05 12.95l2.12-2.12M10.83 5.17l2.12-2.12" stroke="currentColor" strokeWidth={1.4} strokeLinecap="round"/></svg></span>
            {STRINGS.coacheeDetail.analyzeForCoachee}
          </Link>
        </div>
      </div>

      {/* Active experiment */}
      <section className={cardCls}>
        <SectionHeading text={STRINGS.coacheeDetail.activeExperiment} />
        {data.active_experiment ? (
          <ExperimentTracker experiment={data.active_experiment} events={[]} />
        ) : (
          <p className="text-sm text-cv-stone-400">{STRINGS.coacheeDetail.noActiveExperiment}</p>
        )}
      </section>

      {/* Proposed experiments */}
      {proposedExperiments.length > 0 && (
        <section className={cardCls}>
          <div className="flex items-center justify-between mb-3">
            <SectionHeading text={STRINGS.coacheeDetail.suggestedExperiments} />
            <span className="text-xs text-cv-stone-400 -mt-3">
              {STRINGS.coacheeDetail.inQueue(proposedExperiments.length)}
            </span>
          </div>
          <div className="space-y-2">
            {proposedExperiments.map((exp) => (
              <ProposedExperimentRow key={exp.experiment_record_id} experiment={exp} />
            ))}
          </div>
          <p className="text-xs text-cv-stone-400 mt-2">{STRINGS.coacheeDetail.coacheeCanAccept}</p>
        </section>
      )}

      {/* Pattern trends */}
      <section className={cardCls}>
        <SectionHeading text={STRINGS.coacheeDetail.progressTitle} />
        {progressLoading ? (
          <div className="flex items-center gap-2 text-cv-stone-400 text-sm py-8 justify-center">
            <span className="w-4 h-4 border-2 border-cv-teal-500 border-t-transparent rounded-full animate-spin" />
            {STRINGS.common.loading}
          </div>
        ) : progress && progress.pattern_history.length > 0 ? (
          <PatternTrendsCompact
            history={progress.pattern_history}
            trendWindowSize={progress.trend_window_size}
            experimentPatternId={experimentPatternId}
          />
        ) : (
          <p className="text-sm text-cv-stone-400 py-4 text-center">{STRINGS.coacheeDetail.noProgressYet}</p>
        )}
      </section>

      {/* Baseline pack */}
      {data.active_baseline_pack && (
        <section className={cardCls}>
          <SectionHeading text={STRINGS.coacheeDetail.baselinePack} />
          <div className="flex items-center gap-2">
            {(() => {
              const status = (data.active_baseline_pack as Record<string, unknown>).status as string;
              const statusCls =
                status === 'completed' || status === 'baseline_ready'
                  ? 'bg-cv-teal-100 text-cv-teal-700'
                  : status === 'building'
                    ? 'bg-cv-amber-100 text-cv-amber-700'
                    : status === 'error'
                      ? 'bg-cv-red-100 text-cv-red-700'
                      : 'bg-cv-warm-100 text-cv-stone-600';
              return (
                <span className={`text-2xs font-semibold px-2.5 py-1 rounded-full ${statusCls}`}>
                  {STRINGS.baselineStatus[status] ?? status}
                </span>
              );
            })()}
          </div>
        </section>
      )}

      {/* Recent analyses */}
      <section className={cardCls}>
        <SectionHeading text={STRINGS.coacheeDetail.recentRuns} />
        {data.recent_runs.length > 0 ? (
          <div className="space-y-2">
            {data.recent_runs.map((run: Record<string, unknown>, i) => (
              <RunRow key={(run.run_id as string) ?? i} run={run} />
            ))}
          </div>
        ) : (
          <p className="text-sm text-cv-stone-400">{STRINGS.coacheeDetail.noRuns}</p>
        )}
      </section>

      {/* Past experiments */}
      {progress && progress.past_experiments.length > 0 && (
        <section className={cardCls}>
          <SectionHeading text={STRINGS.coacheeDetail.pastExperiments} />
          <div className="space-y-2">
            {progress.past_experiments.map((exp) => (
              <PastExperimentRow key={exp.experiment_record_id} exp={exp as unknown as Record<string, unknown>} />
            ))}
          </div>
        </section>
      )}
    </div>
  );
}

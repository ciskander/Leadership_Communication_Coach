'use client';

import { STRINGS } from '@/config/strings';
import { useEffect, useState, useMemo, useCallback } from 'react';
import { useParams } from 'next/navigation';
import Link from 'next/link';
import { api } from '@/lib/api';
import type { CoacheeSummary, Experiment, ClientProgress, RunStatus, RunHistoryPoint } from '@/lib/types';
import { ExperimentTracker } from '@/components/ExperimentTracker';
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
  ResponsiveContainer,
  ReferenceLine,
} from 'recharts';

// ── Helpers ──────────────────────────────────────────────────────────────────

const LINE_COLORS = [
  '#2563eb', '#16a34a', '#dc2626', '#d97706', '#7c3aed',
  '#0891b2', '#db2777', '#65a30d', '#ea580c', '#6b7280',
];

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

function PatternLabel({ id }: { id: string }) {
  return (
    <span className="text-xs font-semibold text-stone-400 uppercase tracking-widest">
      {STRINGS.patternLabels[id] ?? id.replace(/_/g, ' ')}
    </span>
  );
}

// ── Chart helpers (mirrored from progress page) ─────────────────────────────

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
      const cur = runData[idx][pid];
      if (cur) {
        point[rawKey(pid)] = cur.den > 0
          ? Math.round((cur.num / cur.den) * 100)
          : Math.round(cur.ratio * 100);
      }

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
      point[pid] = totalDen > 0
        ? Math.round((totalNum / totalDen) * 100)
        : ratioCount > 0
          ? Math.round((ratioSum / ratioCount) * 100)
          : null;
    }

    return point;
  });
}

// ── Pattern Trends (compact version for coach view) ──────────────────────────

function PatternTrendsCompact({
  history,
  trendWindowSize = 3,
  experimentPatternId,
}: {
  history: RunHistoryPoint[];
  trendWindowSize?: number;
  experimentPatternId?: string | null;
}) {
  const hasBaseline = history.some((r) => r.is_baseline);
  const postBaselineCount = history.filter((r) => !r.is_baseline).length;
  const showLineChart = hasBaseline && postBaselineCount >= 3;

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

  const chartData = useMemo(
    () => buildChartData(history, allPatterns, trendWindowSize),
    [history, allPatterns, trendWindowSize],
  );
  const baselinePoint = useMemo(() => chartData.find((p) => p.isBaseline), [chartData]);

  if (history.length === 0) {
    return (
      <div className="flex items-center justify-center h-32 text-stone-400 text-sm">
        {STRINGS.coacheeDetail.noProgressYet}
      </div>
    );
  }

  return (
    <div>
      {showLineChart ? (
        <ResponsiveContainer width="100%" height={220}>
          <LineChart data={chartData} margin={{ top: 8, right: 16, left: 0, bottom: 0 }}>
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
              content={({ active, payload, label }: any) => {
                if (!active || !payload?.length) return null;
                const trendEntries = payload.filter((e: any) => !e.dataKey.endsWith('_raw'));
                if (!trendEntries.length) return null;
                return (
                  <div className="bg-white border border-stone-200 rounded-lg shadow-lg p-2 text-xs min-w-[160px]">
                    <p className="font-semibold text-stone-700 mb-1">{label}</p>
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
                <Line
                  key={`${pid}_raw`}
                  type="monotone"
                  dataKey={rawKey(pid)}
                  stroke="none"
                  dot={{ r: isExp ? 3 : 2, fill: color, opacity: isExp ? 0.5 : 0.3 }}
                  activeDot={false}
                  connectNulls={false}
                  legendType="none"
                  isAnimationActive={false}
                />,
                <Line
                  key={pid}
                  type="monotone"
                  dataKey={pid}
                  stroke={color}
                  strokeWidth={isExp ? 3 : 1.5}
                  dot={false}
                  activeDot={{ r: isExp ? 6 : 4, fill: color }}
                  connectNulls
                  isAnimationActive={false}
                />,
              ];
            })}
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
      ) : (
        (() => {
          const latest = [...history].reverse().find((r) => !r.is_baseline) ?? history[history.length - 1];
          const barData = visiblePatterns.map((pid) => {
            const p = latest.patterns.find((x) => x.pattern_id === pid);
            return {
              name: STRINGS.patternLabels[pid] ?? pid,
              score: p ? Math.round(p.ratio * 100) : 0,
              pid,
            };
          });
          const meetingsUntil = Math.max(0, 3 - postBaselineCount);
          return (
            <>
              {meetingsUntil > 0 && (
                <div className="mb-3 inline-flex items-center gap-2 bg-blue-50 text-blue-700 text-xs font-medium px-3 py-1.5 rounded-full">
                  {STRINGS.progressPage.meetingsUntilTrends(meetingsUntil)}
                </div>
              )}
              <ResponsiveContainer width="100%" height={180}>
                <BarChart data={barData} margin={{ top: 4, right: 16, left: 0, bottom: 30 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" vertical={false} />
                  <XAxis
                    dataKey="name"
                    tick={{ fontSize: 9, fill: '#9ca3af' }}
                    tickLine={false}
                    angle={-30}
                    textAnchor="end"
                    interval={0}
                  />
                  <YAxis
                    domain={[0, 100]}
                    tickFormatter={(v) => `${v}%`}
                    tick={{ fontSize: 10, fill: '#9ca3af' }}
                    tickLine={false}
                    axisLine={false}
                  />
                  <Bar dataKey="score" radius={[4, 4, 0, 0]} maxBarSize={36}>
                    {barData.map((entry) => (
                      <Cell key={entry.pid} fill={patternColor(entry.pid)} opacity={0.8} />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </>
          );
        })()
      )}

      {/* Legend */}
      <div className="flex flex-wrap gap-2.5 mt-3">
        {visiblePatterns.map((pid) => {
          const isExp = pid === experimentPatternId;
          return (
            <span key={pid} className={`flex items-center text-xs ${isExp ? 'font-semibold text-stone-900' : 'text-stone-600'}`}>
              <span
                className="inline-block w-2.5 h-2.5 rounded-full mr-1 flex-shrink-0"
                style={{ background: patternColor(pid) }}
              />
              {STRINGS.patternLabels[pid] ?? pid}
              {isExp && (
                <span className="ml-1 text-[9px] font-semibold uppercase tracking-wide bg-indigo-100 text-indigo-700 px-1 py-0.5 rounded-full leading-none">
                  Exp
                </span>
              )}
            </span>
          );
        })}
      </div>
    </div>
  );
}

// ── Proposed Experiment Row ──────────────────────────────────────────────────

function ProposedExperimentRow({ experiment }: { experiment: Experiment }) {
  return (
    <div className="bg-white border border-stone-200 rounded-xl p-4 space-y-2">
      <div className="flex items-start justify-between gap-3">
        <div className="space-y-1 min-w-0">
          <PatternLabel id={experiment.pattern_id} />
          <p className="text-sm font-semibold text-stone-800 leading-snug">
            {experiment.title}
          </p>
        </div>
        <span className="text-xs px-2 py-0.5 rounded-full font-semibold bg-violet-100 text-violet-700 whitespace-nowrap shrink-0">
          {STRINGS.experimentStatus.proposed}
        </span>
      </div>
      <p className="text-xs text-stone-500 leading-relaxed line-clamp-2">
        {experiment.instruction}
      </p>
    </div>
  );
}

// ── Recent Run Row ───────────────────────────────────────────────────────────

function RunRow({ run }: { run: Record<string, unknown> }) {
  const [expanded, setExpanded] = useState(false);
  const [runDetail, setRunDetail] = useState<RunStatus | null>(null);
  const [loadingDetail, setLoadingDetail] = useState(false);

  const runId = (run.run_id as string) ?? (run.id as string);
  const gate1Pass = run.gate1_pass as boolean | null;
  const createdAt = run.created_at as string | undefined;
  const meetingType = run.meeting_type as string | undefined;
  const focusPattern = run.focus_pattern as string | undefined;

  const handleToggle = () => {
    if (!expanded && !runDetail && runId) {
      setLoadingDetail(true);
      api.getRun(runId).then(setRunDetail).catch(() => {}).finally(() => setLoadingDetail(false));
    }
    setExpanded((v) => !v);
  };

  return (
    <div className="border border-stone-200 rounded-xl overflow-hidden">
      <button
        onClick={handleToggle}
        className="w-full flex items-center justify-between px-4 py-3 bg-white hover:bg-stone-50 transition-colors text-left"
        type="button"
      >
        <div className="flex items-center gap-3 min-w-0">
          {gate1Pass === false ? (
            <span className="text-xs px-2 py-0.5 rounded-full font-semibold bg-amber-100 text-amber-700 whitespace-nowrap">
              {STRINGS.coacheeDetail.gateFailLabel}
            </span>
          ) : focusPattern ? (
            <span className="text-xs px-2 py-0.5 rounded-full font-semibold bg-blue-50 text-blue-700 whitespace-nowrap">
              {STRINGS.patternLabels[focusPattern] ?? focusPattern.replace(/_/g, ' ')}
            </span>
          ) : null}
          <span className="text-sm text-stone-700 truncate">
            {meetingType
              ? meetingType.replace(/_/g, ' ').replace(/\b\w/g, (l) => l.toUpperCase())
              : STRINGS.common.meeting}
          </span>
        </div>
        <div className="flex items-center gap-2">
          <span className="text-xs text-stone-400">
            {createdAt ? fmtDate(createdAt) : ''}
          </span>
          <svg
            className={`w-4 h-4 text-stone-400 transition-transform ${expanded ? 'rotate-180' : ''}`}
            viewBox="0 0 20 20"
            fill="currentColor"
          >
            <path fillRule="evenodd" d="M5.293 7.293a1 1 0 011.414 0L10 10.586l3.293-3.293a1 1 0 111.414 1.414l-4 4a1 1 0 01-1.414 0l-4-4a1 1 0 010-1.414z" clipRule="evenodd" />
          </svg>
        </div>
      </button>

      {expanded && (
        <div className="px-4 py-4 bg-stone-50 border-t border-stone-200 space-y-3">
          {loadingDetail && (
            <div className="flex items-center gap-2 text-stone-400 text-sm py-4 justify-center">
              <div className="w-4 h-4 border-2 border-emerald-500 border-t-transparent rounded-full animate-spin" />
              {STRINGS.common.loading}
            </div>
          )}
          {runDetail && runDetail.status === 'complete' && gate1Pass !== false && (
            <>
              {/* Strengths */}
              {runDetail.strengths.length > 0 && (
                <div>
                  <p className="text-xs font-semibold text-emerald-700 uppercase tracking-widest mb-1.5">
                    {STRINGS.coachingCard.strengthsHeading}
                  </p>
                  {runDetail.strengths.map((s, i) => (
                    <div key={i} className="mb-2">
                      <p className="text-xs text-stone-500 font-medium">
                        {STRINGS.patternLabels[s.pattern_id] ?? s.pattern_id}
                      </p>
                      <p className="text-sm text-stone-700">{s.message}</p>
                    </div>
                  ))}
                </div>
              )}
              {/* Focus */}
              {runDetail.focus && (
                <div>
                  <p className="text-xs font-semibold text-amber-700 uppercase tracking-widest mb-1.5">
                    {STRINGS.coachingCard.focusHeading}
                  </p>
                  <p className="text-xs text-stone-500 font-medium">
                    {STRINGS.patternLabels[runDetail.focus.pattern_id] ?? runDetail.focus.pattern_id}
                  </p>
                  <p className="text-sm text-stone-700">{runDetail.focus.message}</p>
                  {runDetail.focus.suggested_rewrite && (
                    <div className="mt-1.5 bg-blue-50 rounded-lg px-3 py-2">
                      <p className="text-xs text-blue-600 font-medium mb-0.5">{STRINGS.common.nextTimeTry}</p>
                      <p className="text-sm text-blue-800 italic">{runDetail.focus.suggested_rewrite}</p>
                    </div>
                  )}
                </div>
              )}
              {/* Experiment detection */}
              {runDetail.experiment_detection && (
                <div className="bg-violet-50 rounded-lg px-3 py-2">
                  <p className="text-xs font-semibold text-violet-700 mb-0.5">
                    {runDetail.experiment_detection.attempt === 'yes'
                      ? STRINGS.runStatusPoller.nicelyDone
                      : runDetail.experiment_detection.attempt === 'partial'
                        ? STRINGS.runStatusPoller.partialAttemptDetected
                        : STRINGS.runStatusPoller.noAttemptDetected}
                  </p>
                  {runDetail.experiment_detection.coaching_note && (
                    <p className="text-sm text-violet-800">{runDetail.experiment_detection.coaching_note}</p>
                  )}
                </div>
              )}
            </>
          )}
          {runDetail && runDetail.status === 'complete' && gate1Pass === false && (
            <p className="text-sm text-amber-600">{STRINGS.runStatusPoller.qualityCheckDesc}</p>
          )}
          {runDetail && runDetail.status === 'error' && (
            <p className="text-sm text-rose-600">{STRINGS.runStatusPoller.errorFallback}</p>
          )}
        </div>
      )}
    </div>
  );
}

// ── Past Experiment Card (compact) ───────────────────────────────────────────

function PastExperimentRow({ exp }: { exp: Record<string, unknown> }) {
  const statusColor =
    exp.status === 'completed'
      ? 'bg-emerald-100 text-emerald-700'
      : exp.status === 'parked'
        ? 'bg-amber-100 text-amber-700'
        : 'bg-rose-100 text-rose-700';

  const dateRange =
    exp.started_at || exp.ended_at
      ? `${fmtDate(exp.started_at as string)} – ${fmtDate(exp.ended_at as string)}`
      : null;

  return (
    <div className="flex items-center justify-between px-4 py-3 bg-white border border-stone-200 rounded-xl">
      <div className="flex items-center gap-3 min-w-0">
        <span className={`text-xs font-semibold px-2 py-0.5 rounded-full flex-shrink-0 ${statusColor}`}>
          {STRINGS.experimentStatus[exp.status as string] ?? exp.status}
        </span>
        <div className="min-w-0">
          <p className="text-sm font-medium text-stone-800 truncate">{exp.title as string}</p>
          <p className="text-xs text-stone-400">
            {STRINGS.patternLabels[exp.pattern_id as string] ?? exp.pattern_id}
            {exp.attempt_count != null && ` · ${STRINGS.progressPage.attemptsAcross(exp.attempt_count as number, (exp.meeting_count as number) ?? 0)}`}
          </p>
        </div>
      </div>
      {dateRange && (
        <span className="text-xs text-stone-400 whitespace-nowrap ml-3">{dateRange}</span>
      )}
    </div>
  );
}

// ── Page ─────────────────────────────────────────────────────────────────────

export default function CoacheeDetailPage() {
  const { id } = useParams<{ id: string }>();
  const [data, setData] = useState<CoacheeSummary | null>(null);
  const [progress, setProgress] = useState<ClientProgress | null>(null);
  const [loading, setLoading] = useState(true);
  const [progressLoading, setProgressLoading] = useState(true);

  useEffect(() => {
    api.getCoacheeSummary(id).then(setData).finally(() => setLoading(false));
    api.getCoacheeProgress(id).then(setProgress).catch(() => {}).finally(() => setProgressLoading(false));
  }, [id]);

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-emerald-600" />
      </div>
    );
  }

  if (!data) return <p className="text-sm text-stone-500">{STRINGS.coacheeDetail.coacheeNotFound}</p>;

  const proposedExperiments = data.proposed_experiments ?? [];
  const experimentPatternId = data.active_experiment?.pattern_id ?? null;

  return (
    <div className="max-w-3xl mx-auto space-y-8 py-2">
      {/* Back + Header */}
      <div>
        <Link
          href="/coach"
          className="text-sm text-stone-500 hover:text-stone-700 transition-colors"
        >
          {STRINGS.coacheeDetail.backToDashboard}
        </Link>
        <div className="flex items-start justify-between mt-2">
          <div>
            <h1 className="text-2xl font-bold text-stone-900">
              {data.coachee.display_name ?? data.coachee.email}
            </h1>
            <p className="text-sm text-stone-500">{data.coachee.email}</p>
          </div>
          <Link
            href={`/coach/analyze?coachee=${id}`}
            className="flex items-center gap-1.5 px-4 py-2 bg-emerald-600 text-white rounded-xl text-sm font-medium hover:bg-emerald-700 transition-colors shadow-sm"
          >
            {STRINGS.coacheeDetail.analyzeForCoachee}
          </Link>
        </div>
      </div>

      {/* Active Experiment */}
      <section className="bg-white rounded-2xl border border-stone-200 shadow-sm p-5">
        <h2 className="text-sm font-semibold text-stone-700 uppercase tracking-wide mb-3">
          {STRINGS.coacheeDetail.activeExperiment}
        </h2>
        {data.active_experiment ? (
          <ExperimentTracker
            experiment={data.active_experiment}
            events={[]}
          />
        ) : (
          <p className="text-sm text-stone-400">{STRINGS.coacheeDetail.noActiveExperiment}</p>
        )}
      </section>

      {/* Proposed Experiments */}
      {proposedExperiments.length > 0 && (
        <section className="bg-white rounded-2xl border border-stone-200 shadow-sm p-5">
          <div className="flex items-center justify-between mb-3">
            <h2 className="text-sm font-semibold text-stone-700 uppercase tracking-wide">
              {STRINGS.coacheeDetail.suggestedExperiments}
            </h2>
            <span className="text-xs text-stone-400">
              {STRINGS.coacheeDetail.inQueue(proposedExperiments.length)}
            </span>
          </div>
          <div className="space-y-2">
            {proposedExperiments.map((exp) => (
              <ProposedExperimentRow key={exp.experiment_record_id} experiment={exp} />
            ))}
          </div>
          <p className="text-xs text-stone-400 mt-2">
            {STRINGS.coacheeDetail.coacheeCanAccept}
          </p>
        </section>
      )}

      {/* Pattern Trends */}
      <section className="bg-white rounded-2xl border border-stone-200 shadow-sm p-5">
        <h2 className="text-sm font-semibold text-stone-700 uppercase tracking-wide mb-4">
          {STRINGS.coacheeDetail.progressTitle}
        </h2>
        {progressLoading ? (
          <div className="flex items-center gap-2 text-stone-400 text-sm py-8 justify-center">
            <div className="w-4 h-4 border-2 border-emerald-500 border-t-transparent rounded-full animate-spin" />
            {STRINGS.common.loading}
          </div>
        ) : progress && progress.pattern_history.length > 0 ? (
          <PatternTrendsCompact
            history={progress.pattern_history}
            trendWindowSize={progress.trend_window_size}
            experimentPatternId={experimentPatternId}
          />
        ) : (
          <p className="text-sm text-stone-400 py-4 text-center">
            {STRINGS.coacheeDetail.noProgressYet}
          </p>
        )}
      </section>

      {/* Baseline Pack */}
      {data.active_baseline_pack && (
        <section className="bg-white rounded-2xl border border-stone-200 shadow-sm p-5">
          <h2 className="text-sm font-semibold text-stone-700 uppercase tracking-wide mb-3">
            {STRINGS.coacheeDetail.baselinePack}
          </h2>
          <div className="flex items-center gap-2">
            {(() => {
              const status = (data.active_baseline_pack as Record<string, unknown>).status as string;
              const statusColor =
                status === 'completed' || status === 'baseline_ready'
                  ? 'bg-emerald-100 text-emerald-700'
                  : status === 'building'
                    ? 'bg-amber-100 text-amber-700'
                    : status === 'error'
                      ? 'bg-rose-100 text-rose-700'
                      : 'bg-stone-100 text-stone-600';
              return (
                <span className={`text-xs font-semibold px-2.5 py-1 rounded-full ${statusColor}`}>
                  {STRINGS.baselineStatus[status] ?? status}
                </span>
              );
            })()}
          </div>
        </section>
      )}

      {/* Recent Analyses */}
      <section className="bg-white rounded-2xl border border-stone-200 shadow-sm p-5">
        <h2 className="text-sm font-semibold text-stone-700 uppercase tracking-wide mb-3">
          {STRINGS.coacheeDetail.recentRuns}
        </h2>
        {data.recent_runs.length > 0 ? (
          <div className="space-y-2">
            {data.recent_runs.map((run: Record<string, unknown>, i) => (
              <RunRow key={(run.run_id as string) ?? i} run={run} />
            ))}
          </div>
        ) : (
          <p className="text-sm text-stone-400">{STRINGS.coacheeDetail.noRuns}</p>
        )}
      </section>

      {/* Past Experiments */}
      {progress && progress.past_experiments.length > 0 && (
        <section className="bg-white rounded-2xl border border-stone-200 shadow-sm p-5">
          <h2 className="text-sm font-semibold text-stone-700 uppercase tracking-wide mb-3">
            {STRINGS.coacheeDetail.pastExperiments}
          </h2>
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

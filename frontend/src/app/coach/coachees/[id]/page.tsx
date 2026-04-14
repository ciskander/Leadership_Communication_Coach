'use client';

import { STRINGS } from '@/config/strings';
import { useEffect, useState, useMemo, useCallback } from 'react';
import { useParams } from 'next/navigation';
import Link from 'next/link';
import { api } from '@/lib/api';
import type { CoacheeSummary, Experiment, ClientProgress, RunStatus, RunHistoryPoint, BaselinePack, BaselinePackMeeting, CoachingItem, PatternSnapshotItem, CoachingTheme } from '@/lib/types';
import { ExperimentTracker } from '@/components/ExperimentTracker';
import { CoachingCard } from '@/components/CoachingCard';
import { PatternSnapshot, buildTrendData } from '@/components/PatternSnapshot';
import type { PatternTrendData } from '@/components/PatternSnapshot';
import { StrengthThemeCard, DevelopmentalThemeCard } from '@/components/RunStatusPoller';
import { EvidenceQuoteList } from '@/components/EvidenceQuote';
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

function RelatedPatternsLabel({ relatedPatterns, patternId }: { relatedPatterns?: string[]; patternId?: string }) {
  const pids = relatedPatterns?.length ? relatedPatterns : patternId ? [patternId] : [];
  if (pids.length === 0) return null;
  return (
    <span className="text-2xs font-semibold uppercase tracking-[0.14em] text-cv-teal-600">
      {pids.map(pid => STRINGS.patternLabels[pid] ?? pid.replace(/_/g, ' ')).join(', ')}
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
  experimentPatternIds,
}: {
  history: RunHistoryPoint[];
  experimentPatternIds?: string[];
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

  const expIds = experimentPatternIds ?? [];
  const visiblePatterns = useMemo(() => {
    const extra = expIds.filter(pid => allPatterns.includes(pid) && !topPatterns.includes(pid));
    return extra.length > 0 ? [...topPatterns, ...extra] : topPatterns;
  }, [expIds, allPatterns, topPatterns]);

  const patternColor = useCallback(
    (pid: string) => LINE_COLORS[allPatterns.indexOf(pid) % LINE_COLORS.length],
    [allPatterns],
  );

  const chartData     = useMemo(() => buildChartData(history, allPatterns, 1), [history, allPatterns]);
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
              const isExp = expIds.includes(pid);
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
                <div className="mb-3 inline-flex items-center gap-2 bg-cv-teal-50 text-cv-teal-700 border border-cv-teal-700 text-xs font-medium px-3 py-1.5 rounded-full">
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
            const isExp = expIds.includes(pid);
            return (
              <span key={pid} className={`flex items-center text-xs ${isExp ? 'font-semibold text-cv-stone-900' : 'text-cv-stone-600'}`}>
                <span className="inline-block w-2.5 h-2.5 rounded-full mr-1 shrink-0" style={{ background: patternColor(pid) }} />
                {STRINGS.patternLabels[pid] ?? pid}
                {isExp && (
                  <span className="ml-1 text-[9px] font-semibold uppercase tracking-wide bg-cv-teal-50 text-cv-teal-700 border border-cv-teal-700 px-1 py-0.5 rounded-full leading-none">
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
          <RelatedPatternsLabel relatedPatterns={experiment.related_patterns} patternId={experiment.pattern_id} />
          <p className="text-sm font-semibold text-cv-stone-800 leading-snug font-serif">
            {experiment.title}
          </p>
        </div>
        <span className="text-2xs px-2 py-0.5 rounded-full font-semibold bg-cv-warm-200 text-cv-stone-600 border border-cv-stone-600 whitespace-nowrap shrink-0">
          {STRINGS.experimentStatus.proposed}
        </span>
      </div>
      <p className="text-xs text-cv-stone-500 leading-relaxed line-clamp-2">
        {experiment.instruction}
      </p>
    </div>
  );
}

// ─── Past experiment row ──────────────────────────────────────────────────────

function PastExperimentRow({ exp }: { exp: Record<string, unknown> }) {
  const statusCls =
    exp.status === 'completed' ? 'bg-cv-teal-50 text-cv-teal-700 border-cv-teal-700'
    : exp.status === 'parked'  ? 'bg-cv-amber-100 text-cv-amber-700 border-cv-amber-700'
    : 'bg-cv-red-100 text-cv-red-700 border-cv-red-700';

  const dateRange =
    exp.started_at || exp.ended_at
      ? `${fmtDate(exp.started_at as string)} – ${fmtDate(exp.ended_at as string)}`
      : null;

  return (
    <div className="flex items-center justify-between px-4 py-3 bg-white border border-cv-warm-300 rounded">
      <div className="flex items-center gap-3 min-w-0">
        <span className={`text-2xs font-semibold px-2 py-0.5 rounded-full border shrink-0 ${statusCls}`}>
          {STRINGS.experimentStatus[exp.status as string] ?? exp.status}
        </span>
        <div className="min-w-0">
          <p className="text-sm font-medium text-cv-stone-800 truncate">{exp.title as string}</p>
          <p className="text-xs text-cv-stone-400">
            {(() => {
              const rp = exp.related_patterns as string[] | undefined;
              const pid = exp.pattern_id as string | undefined;
              const pids = rp?.length ? rp : pid ? [pid] : [];
              return pids.map(p => STRINGS.patternLabels[p] ?? p).join(', ');
            })()}
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

// ─── Baseline meeting components ──────────────────────────────────────────────

function BaselineCoachingThemesSection({ themes }: { themes: CoachingTheme[] }) {
  if (!themes || themes.length === 0) return null;
  return (
    <section className="bg-white rounded border border-cv-rose-700 overflow-hidden">
      <div className="flex items-center gap-2.5 px-5 py-3.5 border-b border-cv-warm-300 bg-cv-rose-700">
        <svg viewBox="0 0 20 20" fill="currentColor" className="w-4 h-4 text-cv-rose-50 shrink-0" aria-hidden="true">
          <path d="M10 12.5a2.5 2.5 0 100-5 2.5 2.5 0 000 5z" />
          <path fillRule="evenodd" d="M.664 10.59a1.651 1.651 0 010-1.186A10.004 10.004 0 0110 3c4.257 0 7.893 2.66 9.336 6.41.147.381.146.804 0 1.186A10.004 10.004 0 0110 17c-4.257 0-7.893-2.66-9.336-6.41zM14 10a4 4 0 11-8 0 4 4 0 018 0z" clipRule="evenodd" />
        </svg>
        <h3 className="text-sm font-semibold text-cv-rose-50">{STRINGS.coachingCard.coachingThemesHeading}</h3>
      </div>
      <div className="divide-y divide-cv-warm-300">
        {themes.map((theme, idx) => (
          <div key={idx} className="px-5 py-4">
            <div className="flex items-center gap-2 mb-1.5">
              <span className={`text-xs font-medium px-2 py-0.5 rounded-full ${
                theme.priority === 'primary'
                  ? 'bg-cv-rose-100 text-cv-rose-700 border border-cv-rose-700'
                  : 'bg-cv-amber-50 text-cv-amber-700 border border-cv-amber-700'
              }`}>
                {theme.priority === 'primary'
                  ? STRINGS.runStatusPoller.primaryThemeLabel
                  : STRINGS.runStatusPoller.secondaryThemeLabel}
              </span>
            </div>
            <p className="text-sm font-medium text-stone-800 mb-1">{theme.theme}</p>
            <p className="text-sm text-stone-600 leading-relaxed">{theme.explanation}</p>
          </div>
        ))}
      </div>
    </section>
  );
}

function BaselineMeetingCard({
  meeting,
  index,
  open,
  onToggle,
  targetSpeaker,
}: {
  meeting: BaselinePackMeeting;
  index: number;
  open: boolean;
  onToggle: () => void;
  targetSpeaker?: string | null;
}) {
  const title = meeting.title || 'Untitled meeting';
  const date = fmtDate(meeting.meeting_date);
  const role = meeting.target_role
    ? (STRINGS.roles[meeting.target_role] ?? meeting.target_role)
    : null;
  const meta = [date, meeting.meeting_type, role].filter(Boolean).join(' · ');

  const hasSubRunData = !!(
    meeting.sub_run_executive_summary ||
    meeting.sub_run_focus ||
    meeting.sub_run_pattern_snapshot?.length
  );

  return (
    <div className={`bg-white border rounded overflow-hidden transition-colors ${
      open ? 'border-cv-stone-100' : 'border-cv-warm-300'
    }`}>
      <button
        onClick={onToggle}
        className="w-full flex items-start justify-between gap-3 px-5 py-4 text-left hover:bg-cv-warm-100 transition-colors"
      >
        <div className="flex items-start gap-3 min-w-0">
          <div className="w-6 h-6 rounded-full bg-cv-warm-200 text-cv-stone-600 flex items-center justify-center text-2xs font-semibold flex-shrink-0 mt-0.5">
            {index + 1}
          </div>
          <div className="min-w-0">
            <p className="text-sm font-medium text-cv-stone-900 truncate">{title}</p>
            {meta && (
              <p className="text-xs text-cv-stone-400 font-light mt-0.5">{meta}</p>
            )}
          </div>
        </div>
        <svg
          viewBox="0 0 16 16"
          fill="none"
          className={`w-4 h-4 text-cv-stone-400 flex-shrink-0 mt-0.5 transition-transform duration-200 ${open ? 'rotate-180' : ''}`}
          aria-hidden="true"
        >
          <path d="M4 6l4 4 4-4" stroke="currentColor" strokeWidth={1.5} strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      </button>

      {open && (
        <div className="border-t border-cv-warm-300 px-5 pb-6 pt-5 space-y-6">
          {meeting.run_id && hasSubRunData ? (
            <>
              {meeting.sub_run_executive_summary && (
                <section className="bg-white rounded border border-cv-navy-600 overflow-hidden">
                  <div className="flex items-center gap-2.5 px-5 py-3.5 border-b border-cv-warm-300 bg-cv-navy-600">
                    <svg viewBox="0 0 20 20" fill="currentColor" className="w-4 h-4 text-cv-blue-50 shrink-0" aria-hidden="true">
                      <path fillRule="evenodd" d="M4.5 2A1.5 1.5 0 003 3.5v13A1.5 1.5 0 004.5 18h11a1.5 1.5 0 001.5-1.5V7.621a1.5 1.5 0 00-.44-1.06l-4.12-4.122A1.5 1.5 0 0011.378 2H4.5zm2.25 8.5a.75.75 0 000 1.5h6.5a.75.75 0 000-1.5h-6.5zm0 3a.75.75 0 000 1.5h6.5a.75.75 0 000-1.5h-6.5z" clipRule="evenodd" />
                    </svg>
                    <h3 className="text-sm font-semibold text-cv-blue-50">{STRINGS.runStatusPoller.summaryHeading}</h3>
                  </div>
                  <div className="px-5 py-4">
                    <p className="text-sm text-cv-stone-700 leading-relaxed">{meeting.sub_run_executive_summary}</p>
                  </div>
                </section>
              )}

              {meeting.sub_run_focus && (
                <CoachingCard
                  focus={(meeting.sub_run_focus ?? null) as CoachingItem | null}
                  microExperiment={null}
                  targetSpeaker={targetSpeaker}
                  patternSnapshot={meeting.sub_run_pattern_snapshot as unknown as PatternSnapshotItem[]}
                  patternCoaching={meeting.sub_run_pattern_coaching}
                />
              )}

              <BaselineCoachingThemesSection themes={meeting.sub_run_coaching_themes ?? []} />

              {meeting.sub_run_pattern_snapshot &&
                meeting.sub_run_pattern_snapshot.length > 0 && (
                <section className="bg-white rounded border border-cv-stone-700 overflow-hidden">
                  <div className="flex items-center gap-2.5 px-5 py-3.5 border-b border-cv-warm-300 bg-cv-stone-700">
                    <svg viewBox="0 0 20 20" fill="currentColor" className="w-4 h-4 text-cv-stone-50 shrink-0" aria-hidden="true">
                      <rect x="2" y="2.35" width="1.8" height="1.8" />
                      <rect x="7" y="2.35" width="11" height="1.8" />
                      <rect x="2" y="6.85" width="1.8" height="1.8" />
                      <rect x="7" y="6.85" width="11" height="1.8" />
                      <rect x="2" y="11.35" width="1.8" height="1.8" />
                      <rect x="7" y="11.35" width="11" height="1.8" />
                      <rect x="2" y="15.85" width="1.8" height="1.8" />
                      <rect x="7" y="15.85" width="11" height="1.8" />
                    </svg>
                    <h3 className="text-sm font-semibold text-cv-stone-50">{STRINGS.runStatusPoller.patternSnapshot}</h3>
                  </div>
                  <div className="px-5 py-4">
                    <PatternSnapshot
                      patterns={meeting.sub_run_pattern_snapshot as unknown as PatternSnapshotItem[]}
                      patternCoaching={meeting.sub_run_pattern_coaching}
                      targetSpeaker={targetSpeaker}
                      groupByCluster
                      strengthPatternIds={(meeting.sub_run_coaching_themes ?? []).filter((t: CoachingTheme) => t.nature === 'strength').flatMap((t: CoachingTheme) => t.related_patterns)}
                      growthAreaPatternIds={[]}
                    />
                  </div>
                </section>
              )}
            </>
          ) : (
            <p className="text-xs text-cv-stone-400 font-light">
              {meeting.run_id
                ? STRINGS.baselineDetail.noAnalysisData
                : STRINGS.baselineDetail.notAnalysedYet}
            </p>
          )}
        </div>
      )}
    </div>
  );
}

// ─── Recent run row ───────────────────────────────────────────────────────────

function RunRow({ run, patternHistory }: { run: Record<string, unknown>; patternHistory?: RunHistoryPoint[] }) {
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

  // Build trend data when run detail is loaded
  const trendData = useMemo<Record<string, PatternTrendData> | undefined>(() => {
    if (!runDetail || !patternHistory || patternHistory.length === 0) return undefined;
    const trends = buildTrendData(patternHistory, 1, runId);
    return Object.keys(trends).length > 0 ? trends : undefined;
  }, [runDetail, patternHistory, runId]);

  // Derive coaching theme data
  const targetSpeaker = runDetail?.target_speaker_label ?? null;
  const strengthThemes = runDetail?.coaching_themes?.filter((t) => t.nature === 'strength') ?? [];
  const developmentalThemes = runDetail?.coaching_themes?.filter(
    (t) => t.nature === 'developmental' || t.nature === 'mixed'
  ) ?? [];

  const patternScores: Record<string, number> = {};
  for (const ps of runDetail?.pattern_snapshot ?? []) {
    if (ps.score != null) patternScores[ps.pattern_id] = ps.score;
  }
  const strengthThemePatternIds = strengthThemes
    .flatMap((t) => t.related_patterns)
    .filter((pid) => (patternScores[pid] ?? 0) >= 0.70);
  const growthAreaPatternIds = isBaseline ? [] : developmentalThemes
    .flatMap((t) => t.related_patterns)
    .filter((pid) => (runDetail?.pattern_coaching ?? []).some((pc) => pc.pattern_id === pid && pc.suggested_rewrite));

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
            <span className="text-2xs px-2 py-0.5 rounded-full font-semibold bg-cv-amber-100 text-cv-amber-700 border border-cv-amber-700 whitespace-nowrap shrink-0">
              {STRINGS.coacheeDetail.gateFailLabel}
            </span>
          )}
          {isBaseline && (
            <span className="text-2xs px-2 py-0.5 rounded-full font-semibold bg-cv-teal-50 text-cv-teal-700 border border-cv-teal-700 whitespace-nowrap shrink-0">
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
        <div className="border-t border-cv-warm-300 bg-cv-warm-50">
          {loadingDetail && (
            <div className="flex items-center gap-2 text-cv-stone-400 text-sm py-8 justify-center">
              <span className="w-4 h-4 border-2 border-cv-teal-500 border-t-transparent rounded-full animate-spin" />
              {STRINGS.common.loading}
            </div>
          )}

          {runDetail && runDetail.status === 'complete' && gate1Pass !== false && (
            <div className="p-4 space-y-4">
              {/* Executive summary */}
              {runDetail.executive_summary && (
                <section className="bg-white rounded border border-cv-navy-600 overflow-hidden">
                  <div className="flex items-center gap-2.5 px-4 py-3 border-b border-cv-warm-300 bg-cv-navy-600">
                    <svg viewBox="0 0 20 20" fill="currentColor" className="w-4 h-4 text-cv-blue-50 shrink-0" aria-hidden="true">
                      <path fillRule="evenodd" d="M4.5 2A1.5 1.5 0 003 3.5v13A1.5 1.5 0 004.5 18h11a1.5 1.5 0 001.5-1.5V7.621a1.5 1.5 0 00-.44-1.06l-4.12-4.122A1.5 1.5 0 0011.378 2H4.5zm2.25 8.5a.75.75 0 000 1.5h6.5a.75.75 0 000-1.5h-6.5zm0 3a.75.75 0 000 1.5h6.5a.75.75 0 000-1.5h-6.5z" clipRule="evenodd" />
                    </svg>
                    <h3 className="text-sm font-semibold text-cv-blue-50">{STRINGS.runStatusPoller.summaryHeading}</h3>
                  </div>
                  <div className="px-4 py-3">
                    <p className="text-sm text-cv-stone-700 leading-relaxed">{runDetail.executive_summary}</p>
                  </div>
                </section>
              )}

              {/* Coaching card (focus + micro-experiment) */}
              <CoachingCard
                focus={runDetail.focus}
                targetSpeaker={targetSpeaker}
                microExperiment={null}
                patternSnapshot={runDetail.pattern_snapshot}
                patternCoaching={isBaseline ? [] : runDetail.pattern_coaching}
                trendData={trendData}
              />

              {/* Strength themes */}
              {strengthThemes.length > 0 && (
                <section className="bg-white rounded border border-cv-teal-700 overflow-hidden">
                  <div className="flex items-center gap-2.5 px-4 py-3 border-b border-cv-warm-300 bg-cv-teal-700">
                    <svg viewBox="0 0 24 24" fill="currentColor" className="w-4 h-4 text-cv-teal-50 shrink-0" aria-hidden="true">
                      <path d="M22,3H19V2a1,1,0,0,0-1-1H6A1,1,0,0,0,5,2V3H2A1,1,0,0,0,1,4V6a4.994,4.994,0,0,0,4.276,4.927A7.009,7.009,0,0,0,11,15.92V18H7a1,1,0,0,0-.949.684l-1,3A1,1,0,0,0,6,23H18a1,1,0,0,0,.948-1.316l-1-3A1,1,0,0,0,17,18H13V15.92a7.009,7.009,0,0,0,5.724-4.993A4.994,4.994,0,0,0,23,6V4A1,1,0,0,0,22,3ZM5,8.829A3.006,3.006,0,0,1,3,6V5H5ZM16.279,20l.333,1H7.387l.334-1ZM17,9A5,5,0,0,1,7,9V3H17Zm4-3a3.006,3.006,0,0,1-2,2.829V5h2ZM10.667,8.667,9,7.292,11,7l1-2,1,2,2,.292L13.333,8.667,13.854,11,12,9.667,10.146,11Z"/>
                    </svg>
                    <h3 className="text-sm font-semibold text-cv-teal-50">{STRINGS.coachingCard.strengthsHeading}</h3>
                  </div>
                  <div className="divide-y divide-cv-warm-300">
                    {strengthThemes.map((theme, idx) => (
                      <StrengthThemeCard key={idx} theme={theme} targetSpeaker={targetSpeaker} />
                    ))}
                  </div>
                </section>
              )}

              {/* Developmental/mixed themes */}
              {developmentalThemes.length > 0 && (
                <section className="bg-white rounded border border-cv-rose-700 overflow-hidden">
                  <div className="flex items-center gap-2.5 px-4 py-3 border-b border-cv-warm-300 bg-cv-rose-700">
                    <svg viewBox="0 0 20 20" fill="currentColor" className="w-4 h-4 text-cv-rose-50 shrink-0" aria-hidden="true">
                      <path d="M10 12.5a2.5 2.5 0 100-5 2.5 2.5 0 000 5z" />
                      <path fillRule="evenodd" d="M.664 10.59a1.651 1.651 0 010-1.186A10.004 10.004 0 0110 3c4.257 0 7.893 2.66 9.336 6.41.147.381.146.804 0 1.186A10.004 10.004 0 0110 17c-4.257 0-7.893-2.66-9.336-6.41zM14 10a4 4 0 11-8 0 4 4 0 018 0z" clipRule="evenodd" />
                    </svg>
                    <h3 className="text-sm font-semibold text-cv-rose-50">{STRINGS.coachingCard.coachingThemesHeading}</h3>
                  </div>
                  <div className="divide-y divide-cv-warm-300">
                    {developmentalThemes.map((theme, idx) => (
                      <DevelopmentalThemeCard key={idx} theme={theme} showPriorityBadge={developmentalThemes.length >= 2} targetSpeaker={targetSpeaker} />
                    ))}
                  </div>
                </section>
              )}

              {/* Experiment detection */}
              {runDetail.experiment_detection && (() => {
                const detection = runDetail.experiment_detection!;
                const attempt = detection.attempt;
                const countAttempts = detection.count_attempts;
                const detectionQuotes = detection.quotes ?? [];
                const expCoaching = runDetail.experiment_coaching;

                const attemptConfig =
                  attempt === 'yes'
                    ? {
                        icon: <svg viewBox="0 0 16 16" fill="none" className="w-4 h-4 shrink-0 text-cv-teal-600" aria-hidden="true"><circle cx="8" cy="8" r="7" stroke="currentColor" strokeWidth={1.4}/><path d="M5 8l2 2 4-4" stroke="currentColor" strokeWidth={1.4} strokeLinecap="round" strokeLinejoin="round"/></svg>,
                        bgColor: 'bg-cv-teal-50',
                        labelColor: 'text-cv-teal-800',
                        label: STRINGS.runStatusPoller.nicelyDone,
                        desc: STRINGS.runStatusPoller.clearAttempts(countAttempts ?? 'multiple'),
                      }
                    : attempt === 'partial'
                    ? {
                        icon: <svg viewBox="0 0 16 16" fill="none" className="w-4 h-4 shrink-0 text-cv-amber-600" aria-hidden="true"><circle cx="8" cy="8" r="7" stroke="currentColor" strokeWidth={1.4}/><path d="M5 8h6" stroke="currentColor" strokeWidth={1.4} strokeLinecap="round"/></svg>,
                        bgColor: 'bg-cv-amber-50',
                        labelColor: 'text-cv-amber-800',
                        label: STRINGS.runStatusPoller.partialAttemptDetected,
                        desc: STRINGS.runStatusPoller.partialAttemptDesc(countAttempts),
                      }
                    : {
                        icon: <svg viewBox="0 0 16 16" fill="none" className="w-4 h-4 shrink-0 text-cv-stone-400" aria-hidden="true"><path d="M6 1v5L2 14h12L10 6V1" stroke="currentColor" strokeWidth={1.4} strokeLinejoin="round"/><path d="M4.5 1h7" stroke="currentColor" strokeWidth={1.4} strokeLinecap="round"/></svg>,
                        bgColor: 'bg-cv-warm-50',
                        labelColor: 'text-cv-stone-700',
                        label: STRINGS.runStatusPoller.noAttemptDetected,
                        desc: null,
                      };

                const hasDetails =
                  (attempt === 'yes' || attempt === 'partial') && detectionQuotes.length > 0;

                const bestSuccessSpanId = detection.best_success_span_id;
                const bestSuccessQuotes = bestSuccessSpanId
                  ? detectionQuotes.filter(q => q.span_id === bestSuccessSpanId)
                  : [];
                const rewriteSpanId = expCoaching?.rewrite_for_span_id;
                const rewriteGroupQuotes = rewriteSpanId
                  ? detectionQuotes.filter(q => q.span_id === rewriteSpanId)
                  : [];
                const hasSplit = bestSuccessQuotes.length > 0 && !!expCoaching?.coaching_note;

                return (
                  <section className="bg-white rounded border border-cv-amber-800 overflow-hidden">
                    <div className="flex items-center gap-2.5 px-4 py-3 border-b border-cv-warm-300 bg-cv-amber-800">
                      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.7} strokeLinecap="round" strokeLinejoin="round" className="w-4 h-4 text-cv-amber-50 shrink-0" aria-hidden="true">
                        <path d="M9 3H15" /><path d="M9 3V9L4 18H20L15 9V3" /><path d="M7.5 14H16.5" />
                      </svg>
                      <h3 className="text-sm font-semibold text-cv-amber-50">{STRINGS.runStatusPoller.experimentSectionHeading}</h3>
                    </div>

                    <div className="px-4 py-4 space-y-3">
                      {/* Detection banner */}
                      <div className="rounded border border-cv-stone-400 overflow-hidden">
                        <div className={`flex items-center gap-2.5 px-4 py-3 ${attemptConfig.bgColor}`}>
                          {attemptConfig.icon}
                          <span className={`text-sm font-semibold ${attemptConfig.labelColor}`}>
                            {attemptConfig.label}
                          </span>
                        </div>

                        <div className="px-4 py-3 space-y-2">
                          {attempt !== 'no' && attemptConfig.desc && (
                            <p className="text-sm text-cv-stone-700 leading-relaxed">{attemptConfig.desc}</p>
                          )}

                          {hasDetails && (
                            <div className="space-y-3 pt-1">
                              {/* Best success quote */}
                              {bestSuccessQuotes.length > 0 && (attempt === 'yes' || hasSplit) && (
                                <div>
                                  <p className="text-2xs font-medium text-cv-stone-400 uppercase tracking-widest mb-1.5">
                                    {STRINGS.common.whatYouDidWell}
                                  </p>
                                  <EvidenceQuoteList quotes={bestSuccessQuotes} targetSpeaker={targetSpeaker} />
                                </div>
                              )}

                              {/* Coaching note */}
                              {expCoaching?.coaching_note && (
                                <div>
                                  <p className="text-2xs font-medium text-cv-stone-400 uppercase tracking-widest mb-1.5">
                                    {attempt === 'yes'
                                      ? STRINGS.runStatusPoller.coachsNote
                                      : hasSplit
                                        ? STRINGS.common.whereYouCanImprove
                                        : STRINGS.runStatusPoller.whatWorkedMissing}
                                  </p>
                                  <p className="text-sm text-cv-stone-700 leading-relaxed">
                                    {expCoaching.coaching_note}
                                  </p>
                                </div>
                              )}

                              {/* Rewrite target quote (partial only) */}
                              {attempt === 'partial' && rewriteGroupQuotes.length > 0 && (
                                <div>
                                  <p className="text-2xs font-medium text-cv-stone-400 uppercase tracking-widest mb-1.5">
                                    {STRINGS.common.forExampleYouSaid}
                                  </p>
                                  <EvidenceQuoteList quotes={rewriteGroupQuotes} targetSpeaker={targetSpeaker} />
                                </div>
                              )}

                              {/* Suggested rewrite */}
                              {expCoaching?.suggested_rewrite && (
                                <div>
                                  <p className="text-2xs font-medium text-cv-stone-400 uppercase tracking-widest mb-1.5">
                                    {STRINGS.common.nextTimeTry}
                                  </p>
                                  <blockquote className="border-l-[2px] border-cv-teal-700 pl-4 pr-3 py-2.5 bg-cv-teal-50 rounded-r my-2">
                                    <p className="text-sm text-cv-stone-700 italic leading-relaxed">
                                      &ldquo;{expCoaching.suggested_rewrite}&rdquo;
                                    </p>
                                  </blockquote>
                                </div>
                              )}
                            </div>
                          )}
                        </div>
                      </div>
                    </div>
                  </section>
                );
              })()}

              {/* Pattern snapshot */}
              {runDetail.pattern_snapshot && runDetail.pattern_snapshot.length > 0 && (
                <section className="bg-white rounded border border-cv-stone-700 overflow-hidden">
                  <div className="flex items-center gap-2.5 px-4 py-3 border-b border-cv-warm-300 bg-cv-stone-700">
                    <svg viewBox="0 0 20 20" fill="currentColor" className="w-4 h-4 text-cv-stone-50 shrink-0" aria-hidden="true">
                      <rect x="2" y="2.35" width="1.8" height="1.8" />
                      <rect x="7" y="2.35" width="11" height="1.8" />
                      <rect x="2" y="6.85" width="1.8" height="1.8" />
                      <rect x="7" y="6.85" width="11" height="1.8" />
                      <rect x="2" y="11.35" width="1.8" height="1.8" />
                      <rect x="7" y="11.35" width="11" height="1.8" />
                      <rect x="2" y="15.85" width="1.8" height="1.8" />
                      <rect x="7" y="15.85" width="11" height="1.8" />
                    </svg>
                    <h3 className="text-sm font-semibold text-cv-stone-50">{STRINGS.runStatusPoller.patternSnapshot}</h3>
                  </div>
                  <div className="px-4 py-3">
                    <PatternSnapshot
                      patterns={runDetail.pattern_snapshot}
                      patternCoaching={isBaseline ? [] : runDetail.pattern_coaching}
                      targetSpeaker={targetSpeaker}
                      trendData={trendData}
                      groupByCluster
                      strengthPatternIds={strengthThemePatternIds}
                      growthAreaPatternIds={growthAreaPatternIds}
                    />
                  </div>
                </section>
              )}
            </div>
          )}

          {runDetail && runDetail.status === 'complete' && gate1Pass === false && (
            <div className="p-4">
              <p className="text-sm text-cv-amber-600">{STRINGS.runStatusPoller.qualityCheckDesc}</p>
            </div>
          )}
          {runDetail && runDetail.status === 'error' && (
            <div className="p-4">
              <p className="text-sm text-cv-red-600">{STRINGS.runStatusPoller.errorFallback}</p>
            </div>
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
  const [baselinePack, setBaselinePack]     = useState<BaselinePack | null>(null);
  const [openMeetingIdx, setOpenMeetingIdx] = useState<number | null>(null);
  const [loading, setLoading]               = useState(true);
  const [progressLoading, setProgressLoading] = useState(true);

  useEffect(() => {
    api.getCoacheeSummary(id).then(setData).finally(() => setLoading(false));
    api.getCoacheeProgress(id).then(setProgress).catch(() => {}).finally(() => setProgressLoading(false));
  }, [id]);

  // Fetch baseline pack detail once summary is loaded
  useEffect(() => {
    if (!data?.active_baseline_pack) return;
    const bp = data.active_baseline_pack as Record<string, unknown>;
    const bpId = bp.record_id as string | undefined;
    const status = bp.status as string | undefined;
    if (bpId && (status === 'completed' || status === 'baseline_ready')) {
      api.getBaselinePack(bpId).then(setBaselinePack).catch(() => {});
    }
  }, [data]);

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <span className="w-8 h-8 border-2 border-cv-teal-600 border-t-transparent rounded-full animate-spin" />
      </div>
    );
  }

  if (!data) return <p className="text-sm text-cv-stone-500">{STRINGS.coacheeDetail.coacheeNotFound}</p>;

  const proposedExperiments  = data.proposed_experiments ?? [];
  const experimentPatternIds = data.active_experiment?.related_patterns
    ?? (data.active_experiment?.pattern_id ? [data.active_experiment.pattern_id] : []);

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
            experimentPatternIds={experimentPatternIds}
          />
        ) : (
          <p className="text-sm text-cv-stone-400 py-4 text-center">{STRINGS.coacheeDetail.noProgressYet}</p>
        )}
      </section>

      {/* Baseline pack */}
      {data.active_baseline_pack && (
        <section className={cardCls}>
          <SectionHeading text={STRINGS.coacheeDetail.baselinePack} />
          <div className="flex items-center gap-2 mb-3">
            {(() => {
              const status = (data.active_baseline_pack as Record<string, unknown>).status as string;
              const statusCls =
                status === 'completed' || status === 'baseline_ready'
                  ? 'bg-cv-teal-50 text-cv-teal-700 border-cv-teal-700'
                  : status === 'building'
                    ? 'bg-cv-amber-100 text-cv-amber-700 border-cv-amber-700'
                    : status === 'error'
                      ? 'bg-cv-red-100 text-cv-red-700 border-cv-red-700'
                      : 'bg-cv-warm-100 text-cv-stone-600 border-cv-stone-600';
              return (
                <span className={`text-2xs font-semibold px-2.5 py-1 rounded-full border ${statusCls}`}>
                  {STRINGS.baselineStatus[status] ?? status}
                </span>
              );
            })()}
          </div>
          {baselinePack?.meetings && baselinePack.meetings.length > 0 && (
            <div className="space-y-2">
              {baselinePack.meetings.map((meeting, i) => (
                <BaselineMeetingCard
                  key={meeting.run_id ?? i}
                  meeting={meeting}
                  index={i}
                  open={openMeetingIdx === i}
                  onToggle={() => setOpenMeetingIdx(openMeetingIdx === i ? null : i)}
                  targetSpeaker={baselinePack.target_speaker_label}
                />
              ))}
            </div>
          )}
        </section>
      )}

      {/* Recent analyses */}
      <section className={cardCls}>
        <SectionHeading text={STRINGS.coacheeDetail.recentRuns} />
        {data.recent_runs.length > 0 ? (
          <div className="space-y-2">
            {data.recent_runs.map((run: Record<string, unknown>, i) => (
              <RunRow key={(run.run_id as string) ?? i} run={run} patternHistory={progress?.pattern_history} />
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

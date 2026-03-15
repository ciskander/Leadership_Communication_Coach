'use client';

import { useState } from 'react';
import { LineChart, Line, ResponsiveContainer } from 'recharts';
import type { PatternSnapshotItem, RunHistoryPoint } from '@/lib/types';
import { EvidenceQuote, EvidenceQuoteList } from './EvidenceQuote';
import { STRINGS } from '@/config/strings';

// ─── Trend data types ────────────────────────────────────────────────────────

export interface PatternTrendData {
  /** Rolling-average data points for the sparkline, in chronological order (0-100). */
  points: number[];
  /** Current score (latest rolling average), 0-100. */
  currentScore: number;
  /** Baseline average score, 0-100. */
  baselineAvg: number;
  /** Delta: currentScore - baselineAvg. */
  delta: number;
}

// ─── Build trend data from progress history ──────────────────────────────────

const STABLE_THRESHOLD = 2; // delta within +/- this value is considered "stable"

export function buildTrendData(
  history: RunHistoryPoint[],
  windowSize: number,
): Record<string, PatternTrendData> {
  const baselineRuns = history.filter((r) => r.is_baseline);
  const postBaselineRuns = history.filter((r) => !r.is_baseline);

  if (baselineRuns.length === 0 || postBaselineRuns.length === 0) return {};

  // Collect all pattern IDs across history
  const allPatternIds = new Set<string>();
  for (const run of history) {
    for (const p of run.patterns) allPatternIds.add(p.pattern_id);
  }

  const result: Record<string, PatternTrendData> = {};

  for (const pid of Array.from(allPatternIds)) {
    // Compute baseline average (aggregate num/den across all baseline runs)
    let blNum = 0, blDen = 0;
    for (const run of baselineRuns) {
      const p = run.patterns.find((x) => x.pattern_id === pid);
      if (p) {
        const den = p.opportunity_count ?? 0;
        const num = den > 0 ? Math.round(p.ratio * den) : 0;
        blNum += num;
        blDen += den;
      }
    }
    const baselineAvg = blDen > 0 ? Math.round((blNum / blDen) * 100) : null;
    if (baselineAvg == null) continue;

    // Build per-run numerator/denominator data for rolling average
    const runData: { num: number; den: number; ratio: number }[] = [];
    for (const run of history) {
      const p = run.patterns.find((x) => x.pattern_id === pid);
      if (p) {
        const den = p.opportunity_count ?? 0;
        const num = den > 0 ? Math.round(p.ratio * den) : 0;
        runData.push({ num, den, ratio: p.ratio });
      } else {
        runData.push({ num: 0, den: 0, ratio: 0 });
      }
    }

    // Compute rolling average points
    const points: number[] = [];
    for (let idx = 0; idx < history.length; idx++) {
      let totalNum = 0, totalDen = 0, ratioSum = 0, ratioCount = 0;
      const start = Math.max(0, idx - windowSize + 1);
      for (let j = start; j <= idx; j++) {
        const d = runData[j];
        if (d.den > 0 || d.ratio > 0) {
          totalNum += d.num;
          totalDen += d.den;
          ratioSum += d.ratio;
          ratioCount++;
        }
      }
      const val = totalDen > 0
        ? Math.round((totalNum / totalDen) * 100)
        : ratioCount > 0
          ? Math.round((ratioSum / ratioCount) * 100)
          : null;
      if (val != null) points.push(val);
    }

    if (points.length < 2) continue;

    const currentScore = points[points.length - 1];
    const delta = currentScore - baselineAvg;

    result[pid] = { points, currentScore, baselineAvg, delta };
  }

  return result;
}

// ─── Pattern icons (inline SVG — replaces STRINGS.patternIcons emoji) ─────────

const PATTERN_ICONS: Record<string, JSX.Element> = {
  agenda_clarity: (
    <svg viewBox="0 0 16 16" fill="none" className="w-3.5 h-3.5" aria-hidden="true">
      <rect x="2" y="1.5" width="12" height="13" rx="1.5" stroke="currentColor" strokeWidth={1.4} />
      <path d="M5 5h6M5 8h6M5 11h4" stroke="currentColor" strokeWidth={1.4} strokeLinecap="round" />
    </svg>
  ),
  objective_signaling: (
    <svg viewBox="0 0 16 16" fill="none" className="w-3.5 h-3.5" aria-hidden="true">
      <circle cx="8" cy="8" r="6" stroke="currentColor" strokeWidth={1.4} />
      <circle cx="8" cy="8" r="2.5" stroke="currentColor" strokeWidth={1.4} />
      <path d="M8 2V1M8 15v-1M2 8H1M15 8h-1" stroke="currentColor" strokeWidth={1.4} strokeLinecap="round" />
    </svg>
  ),
  turn_allocation: (
    <svg viewBox="0 0 16 16" fill="none" className="w-3.5 h-3.5" aria-hidden="true">
      <path d="M2 5.5h9.5M2 5.5l2.5-2.5M2 5.5l2.5 2.5" stroke="currentColor" strokeWidth={1.4} strokeLinecap="round" strokeLinejoin="round" />
      <path d="M14 10.5H4.5M14 10.5l-2.5-2.5M14 10.5l-2.5 2.5" stroke="currentColor" strokeWidth={1.4} strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  ),
  facilitative_inclusion: (
    <svg viewBox="0 0 16 16" fill="none" className="w-3.5 h-3.5" aria-hidden="true">
      <circle cx="8" cy="4.5" r="2" stroke="currentColor" strokeWidth={1.4} />
      <path d="M4 13c0-2.21 1.79-4 4-4s4 1.79 4 4" stroke="currentColor" strokeWidth={1.4} strokeLinecap="round" />
      <circle cx="2.5" cy="6" r="1.5" stroke="currentColor" strokeWidth={1.2} />
      <path d="M0 13c0-1.66 1.12-3 2.5-3" stroke="currentColor" strokeWidth={1.2} strokeLinecap="round" />
      <circle cx="13.5" cy="6" r="1.5" stroke="currentColor" strokeWidth={1.2} />
      <path d="M16 13c0-1.66-1.12-3-2.5-3" stroke="currentColor" strokeWidth={1.2} strokeLinecap="round" />
    </svg>
  ),
  decision_closure: (
    <svg viewBox="0 0 16 16" fill="none" className="w-3.5 h-3.5" aria-hidden="true">
      <rect x="3" y="7" width="10" height="7.5" rx="1.5" stroke="currentColor" strokeWidth={1.4} />
      <path d="M5.5 7V5a2.5 2.5 0 015 0v2" stroke="currentColor" strokeWidth={1.4} strokeLinecap="round" />
      <path d="M6 10.5l1.5 1.5 2.5-2.5" stroke="currentColor" strokeWidth={1.4} strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  ),
  owner_timeframe_specification: (
    <svg viewBox="0 0 16 16" fill="none" className="w-3.5 h-3.5" aria-hidden="true">
      <rect x="1.5" y="3" width="13" height="11.5" rx="1.5" stroke="currentColor" strokeWidth={1.4} />
      <path d="M1.5 6.5h13" stroke="currentColor" strokeWidth={1.4} />
      <path d="M5 1.5v3M11 1.5v3" stroke="currentColor" strokeWidth={1.4} strokeLinecap="round" />
      <path d="M4.5 9.5h3M4.5 12h2" stroke="currentColor" strokeWidth={1.4} strokeLinecap="round" />
      <circle cx="11.5" cy="11" r="2" stroke="currentColor" strokeWidth={1.2} />
      <path d="M11.5 9.8V11l.8.8" stroke="currentColor" strokeWidth={1.2} strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  ),
  summary_checkback: (
    <svg viewBox="0 0 16 16" fill="none" className="w-3.5 h-3.5" aria-hidden="true">
      <path d="M3 4h10M3 7.5h10M3 11h6" stroke="currentColor" strokeWidth={1.4} strokeLinecap="round" />
      <circle cx="12.5" cy="12.5" r="2.5" fill="currentColor" fillOpacity={0.15} stroke="currentColor" strokeWidth={1.2} />
      <path d="M11.3 12.5l.8.8 1.4-1.4" stroke="currentColor" strokeWidth={1.2} strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  ),
  question_quality: (
    <svg viewBox="0 0 16 16" fill="none" className="w-3.5 h-3.5" aria-hidden="true">
      <circle cx="8" cy="8" r="6.5" stroke="currentColor" strokeWidth={1.4} />
      <path d="M6.2 6.2a1.8 1.8 0 013.2 1.1c0 1.8-2.2 1.8-2.2 3.2" stroke="currentColor" strokeWidth={1.4} strokeLinecap="round" />
      <circle cx="7.2" cy="11.8" r="0.6" fill="currentColor" />
    </svg>
  ),
  listener_response_quality: (
    <svg viewBox="0 0 16 16" fill="none" className="w-3.5 h-3.5" aria-hidden="true">
      <path d="M4.5 10.5C3.5 9.5 3 8.3 3 7a4 4 0 018 0c0 1.2-.8 2-1.2 2.5-.4.5-.8 1-.8 1.8v.2a1.5 1.5 0 01-3 0" stroke="currentColor" strokeWidth={1.4} strokeLinecap="round" strokeLinejoin="round" />
      <path d="M7 5.5A1.5 1.5 0 005.5 7c0 .6.3 1 .7 1.3" stroke="currentColor" strokeWidth={1.4} strokeLinecap="round" strokeLinejoin="round" />
      <path d="M12 5.5a4.5 4.5 0 010 4" stroke="currentColor" strokeWidth={1.4} strokeLinecap="round" />
      <path d="M13.5 3.5a7 7 0 010 6" stroke="currentColor" strokeWidth={1.4} strokeLinecap="round" />
    </svg>
  ),
  conversational_balance: (
    <svg viewBox="0 0 16 16" fill="none" className="w-3.5 h-3.5" aria-hidden="true">
      <path d="M8 2v12" stroke="currentColor" strokeWidth={1.4} strokeLinecap="round" />
      <path d="M3 2h10" stroke="currentColor" strokeWidth={1.4} strokeLinecap="round" />
      <path d="M3 2l-2 4h4L3 2zM13 2l-2 4h4L13 2z" stroke="currentColor" strokeWidth={1.3} strokeLinejoin="round" />
      <path d="M2 14h4M10 14h4" stroke="currentColor" strokeWidth={1.4} strokeLinecap="round" />
    </svg>
  ),
};


// ─── Sub-components ───────────────────────────────────────────────────────────

function SectionLabel({ text }: { text: string }) {
  return (
    <p className="text-2xs font-semibold uppercase tracking-[0.14em] text-cv-stone-400 mb-1.5">
      {text}
    </p>
  );
}

function SuggestedRewrite({ text }: { text: string }) {
  return (
    <blockquote className="border-l-[3px] border-cv-teal-700 pl-4 pr-3 py-2.5 bg-cv-teal-50 rounded-r my-2">
      <p className="text-sm text-cv-stone-700 italic leading-relaxed">
        &ldquo;{text}&rdquo;
      </p>
    </blockquote>
  );
}

// ─── Balance badge ────────────────────────────────────────────────────────────

const BALANCE_COLORS: Record<string, { bg: string; dot: string; text: string }> = {
  balanced:      { bg: 'bg-cv-teal-50',   dot: 'bg-cv-teal-500',   text: 'text-cv-stone-700' },
  over_indexed:  { bg: 'bg-cv-red-50',    dot: 'bg-cv-red-400',    text: 'text-cv-stone-700' },
  under_indexed: { bg: 'bg-cv-amber-50',  dot: 'bg-cv-amber-400',  text: 'text-cv-stone-700' },
  unclear:       { bg: 'bg-cv-warm-100',  dot: 'bg-cv-stone-300',  text: 'text-cv-stone-500' },
};

function BalanceBadge({ assessment }: { assessment: string }) {
  const colors = BALANCE_COLORS[assessment] ?? BALANCE_COLORS.unclear;
  const label  = STRINGS.balanceLabels[assessment] ?? assessment;
  return (
    <span className={`inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full text-xs font-medium ${colors.bg} ${colors.text}`}>
      <span className={`w-1.5 h-1.5 rounded-full shrink-0 ${colors.dot}`} />
      {label}
    </span>
  );
}

// ─── Trend indicator (delta arrow + label) ───────────────────────────────────

function TrendDelta({ delta }: { delta: number }) {
  if (Math.abs(delta) <= STABLE_THRESHOLD) {
    return (
      <span className="text-sm text-cv-stone-400 font-medium ml-1.5">
        &mdash; {STRINGS.trendSparkline.stable}
      </span>
    );
  }
  if (delta > 0) {
    return (
      <span className="text-sm text-cv-teal-600 font-semibold ml-1.5">
        &uarr; +{delta}
      </span>
    );
  }
  return (
    <span className="text-sm text-cv-red-500 font-semibold ml-1.5">
      &darr; {delta}
    </span>
  );
}

// ─── Trend sparkline (mini Recharts line) ────────────────────────────────────

const SPARKLINE_TEAL  = '#0F6E56';
const SPARKLINE_AMBER = '#D97706';
const SPARKLINE_RED   = '#EF4444';

function TrendSparkline({ trend }: { trend: PatternTrendData }) {
  // Color based on current score (same thresholds as RatioBar)
  const color = trend.currentScore >= 75
    ? SPARKLINE_TEAL
    : trend.currentScore >= 50
      ? SPARKLINE_AMBER
      : SPARKLINE_RED;

  const data = trend.points.map((v, i) => ({ v, i }));
  const lastIdx = data.length - 1;

  return (
    <div className="mt-1" style={{ height: 32 }}>
      <ResponsiveContainer width="100%" height={32}>
        <LineChart data={data} margin={{ top: 4, right: 6, left: 6, bottom: 4 }}>
          <Line
            type="monotone"
            dataKey="v"
            stroke={color}
            strokeWidth={1.5}
            dot={(props: any) => {
              if (props.index !== lastIdx) return <g key={props.index} />;
              return (
                <circle
                  key={props.index}
                  cx={props.cx}
                  cy={props.cy}
                  r={3.5}
                  fill={color}
                  stroke="white"
                  strokeWidth={1.5}
                />
              );
            }}
            activeDot={false}
            isAnimationActive={false}
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}

// ─── Ratio bar (fallback when no trend data) ────────────────────────────────

function RatioBar({ ratio }: { ratio: number }) {
  const pct = Math.round(ratio * 100);
  const fill =
    pct >= 75 ? 'bg-cv-teal-500'
    : pct >= 50 ? 'bg-cv-amber-400'
    : 'bg-cv-red-400';
  return (
    <div className="flex items-center gap-2 mt-1.5">
      <div className="flex-1 bg-cv-warm-200 rounded-full h-1.5 overflow-hidden">
        <div
          className={`h-1.5 rounded-full transition-all duration-300 ${fill}`}
          style={{ width: `${pct}%` }}
        />
      </div>
      <span className="text-xs tabular-nums text-cv-stone-500 w-9 text-right">{pct}%</span>
    </div>
  );
}

// ─── Expand/collapse chevron ──────────────────────────────────────────────────

function Chevron({ open }: { open: boolean }) {
  return (
    <svg
      viewBox="0 0 20 20"
      fill="none"
      stroke="currentColor"
      strokeWidth={2}
      strokeLinecap="round"
      strokeLinejoin="round"
      className={`w-3.5 h-3.5 text-cv-stone-400 transition-transform duration-200 ${open ? 'rotate-180' : ''}`}
      aria-hidden="true"
    >
      <path d="M5 8l5 5 5-5" />
    </svg>
  );
}

// ─── Individual pattern card ──────────────────────────────────────────────────

function PatternCard({
  pattern,
  targetSpeaker,
  trend,
}: {
  pattern: PatternSnapshotItem;
  targetSpeaker: string | null;
  trend?: PatternTrendData;
}) {
  const [expanded, setExpanded] = useState(false);

  const quotes                  = pattern.quotes ?? [];
  const isConversationalBalance = pattern.pattern_id === 'conversational_balance';
  const hasQuotes               = quotes.length > 0;
  const hasCoaching             = !!pattern.coaching_note;
  const hasNotes                = !!pattern.notes;
  const isBalanced              = pattern.balance_assessment === 'balanced';

  const isExpandable = isConversationalBalance
    ? (isBalanced ? hasNotes : hasCoaching)
    : (hasQuotes || hasCoaching || hasNotes);

  const hasMissedOpportunities =
    pattern.evaluable_status === 'evaluable' &&
    pattern.numerator != null &&
    pattern.denominator != null &&
    pattern.numerator < pattern.denominator;

  const isPerfectScore =
    pattern.evaluable_status === 'evaluable' &&
    pattern.numerator != null &&
    pattern.denominator != null &&
    pattern.numerator === pattern.denominator &&
    pattern.numerator > 0;

  const isMixedScore = hasMissedOpportunities && pattern.numerator != null && pattern.numerator > 0;

  const rewriteSpanId   = pattern.rewrite_for_span_id;
  const canSplitQuotes  = isMixedScore && !!rewriteSpanId;
  const successQuotes   = canSplitQuotes
    ? quotes.filter((q) => q.span_id !== rewriteSpanId)
    : (isPerfectScore ? quotes : []);
  const improvementQuotes = canSplitQuotes
    ? quotes.filter((q) => q.span_id === rewriteSpanId)
    : (isPerfectScore ? [] : quotes);

  // For zero-score and mixed-no-split paths: ensure the quote shown above the
  // suggested rewrite is the one matching rewrite_for_span_id, not just quotes[0].
  const rewriteTargetQuote = rewriteSpanId
    ? quotes.find((q) => q.span_id === rewriteSpanId) ?? quotes[0]
    : quotes[0];
  const remainingQuotes = rewriteTargetQuote
    ? quotes.filter((q) => q !== rewriteTargetQuote)
    : quotes.slice(1);

  // Determine if we should show sparkline for this pattern
  const showSparkline = !!trend && trend.points.length >= 2;

  return (
    <div className={`bg-white border border-cv-warm-200 rounded overflow-hidden${expanded ? ' sm:col-span-2' : ''}`}>
      {/* ── Card header row ── */}
      <button
        type="button"
        onClick={() => isExpandable && setExpanded(!expanded)}
        className={[
          'w-full px-4 py-3 text-left',
          isExpandable ? 'cursor-pointer hover:bg-cv-warm-50 transition-colors' : 'cursor-default',
        ].join(' ')}
      >
        <div className="flex items-center justify-between mb-0.5">
          {/* Pattern name */}
          <span className="text-sm font-medium text-cv-stone-800 leading-snug">
            {PATTERN_ICONS[pattern.pattern_id] && (
              <span className="mr-1.5 text-cv-stone-400 inline-flex items-center">
                {PATTERN_ICONS[pattern.pattern_id]}
              </span>
            )}
            {STRINGS.patternLabels[pattern.pattern_id] ?? pattern.pattern_id}
          </span>

          {/* Tier tag + chevron */}
          <div className="flex items-center gap-1.5 shrink-0 ml-2">
            {pattern.tier && (
              <span className="text-2xs text-cv-stone-400 tabular-nums">T{pattern.tier}</span>
            )}
            {isExpandable && <Chevron open={expanded} />}
          </div>
        </div>

        {/* Score row */}
        {pattern.evaluable_status === 'evaluable' && pattern.ratio != null ? (
          showSparkline ? (
            <div className="mt-1">
              <div className="flex items-baseline">
                <span className="text-xl font-bold tabular-nums text-cv-stone-800">
                  {trend!.currentScore}%
                </span>
                <TrendDelta delta={trend!.delta} />
              </div>
              <TrendSparkline trend={trend!} />
            </div>
          ) : (
            <RatioBar ratio={pattern.ratio} />
          )
        ) : pattern.evaluable_status === 'evaluable' && pattern.balance_assessment ? (
          <div className="mt-1 flex items-center gap-2">
            <BalanceBadge assessment={pattern.balance_assessment} />
            {trend && trend.points.length >= 2 && (
              <TrendDelta delta={trend.delta} />
            )}
          </div>
        ) : (
          <span className="text-xs text-cv-stone-400 capitalize">
            {pattern.evaluable_status === 'insufficient_signal'
              ? STRINGS.evaluableStatus.insufficient_signal
              : STRINGS.evaluableStatus.not_evaluable}
          </span>
        )}
      </button>

      {/* ── Expanded detail ── */}
      {expanded && (
        <div className="border-t border-cv-warm-100 px-4 pb-4 pt-3 space-y-3">

          {/* Perfect score */}
          {isPerfectScore && (hasQuotes || hasNotes) && (
            <div>
              <SectionLabel text={STRINGS.common.whatYouDidWell} />
              {hasNotes && (
                <p className="text-sm text-cv-stone-700 leading-relaxed mb-2">{pattern.notes}</p>
              )}
              <EvidenceQuoteList quotes={quotes} targetSpeaker={targetSpeaker} />
            </div>
          )}

          {/* Mixed score — splittable */}
          {isMixedScore && canSplitQuotes && (
            <>
              {(successQuotes.length > 0 || hasNotes) && (
                <div>
                  <SectionLabel text={STRINGS.common.whatYouDidWell} />
                  {hasNotes && (
                    <p className="text-sm text-cv-stone-700 leading-relaxed mb-2">{pattern.notes}</p>
                  )}
                  <EvidenceQuoteList quotes={successQuotes} targetSpeaker={targetSpeaker} />
                </div>
              )}
              <div>
                <SectionLabel text={STRINGS.common.whereYouCanImprove} />
                {hasCoaching && (
                  <p className="text-sm text-cv-stone-700 leading-relaxed mb-2">{pattern.coaching_note}</p>
                )}
                {improvementQuotes.length > 0 && (
                  <div>
                    <SectionLabel text={STRINGS.common.forExampleYouSaid} />
                    <EvidenceQuote quote={improvementQuotes[0]} targetSpeaker={targetSpeaker} />
                  </div>
                )}
                {pattern.suggested_rewrite && (
                  <div className="mt-2">
                    <SectionLabel text={STRINGS.common.nextTimeTry} />
                    <SuggestedRewrite text={pattern.suggested_rewrite} />
                  </div>
                )}
                {improvementQuotes.length > 1 && (
                  <div className="mt-2">
                    <SectionLabel text={STRINGS.common.otherMoments} />
                    <EvidenceQuoteList quotes={improvementQuotes.slice(1)} targetSpeaker={targetSpeaker} />
                  </div>
                )}
              </div>
            </>
          )}

          {/* Mixed score — no split target */}
          {isMixedScore && !canSplitQuotes && (
            <>
              {hasNotes && (
                <div>
                  <SectionLabel text={STRINGS.common.whatYouDidWell} />
                  <p className="text-sm text-cv-stone-700 leading-relaxed">{pattern.notes}</p>
                </div>
              )}
              <div>
                <SectionLabel text={STRINGS.common.whereYouCanImprove} />
                {hasCoaching && (
                  <p className="text-sm text-cv-stone-700 leading-relaxed mb-2">{pattern.coaching_note}</p>
                )}
                {hasQuotes && rewriteTargetQuote && (
                  <div>
                    <SectionLabel text={STRINGS.common.forExampleYouSaid} />
                    <EvidenceQuote quote={rewriteTargetQuote} targetSpeaker={targetSpeaker} />
                  </div>
                )}
                {pattern.suggested_rewrite && (
                  <div className="mt-2">
                    <SectionLabel text={STRINGS.common.nextTimeTry} />
                    <SuggestedRewrite text={pattern.suggested_rewrite} />
                  </div>
                )}
                {remainingQuotes.length > 0 && (
                  <div className="mt-2">
                    <SectionLabel text={STRINGS.common.otherMoments} />
                    <EvidenceQuoteList quotes={remainingQuotes} targetSpeaker={targetSpeaker} />
                  </div>
                )}
              </div>
            </>
          )}

          {/* Conversational balance — balanced */}
          {isConversationalBalance && isBalanced && hasNotes && (
            <div>
              <SectionLabel text={STRINGS.common.whatYouDidWell} />
              <p className="text-sm text-cv-stone-700 leading-relaxed">{pattern.notes}</p>
            </div>
          )}

          {/* Conversational balance — off-balance */}
          {isConversationalBalance && !isBalanced && hasCoaching && (
            <div>
              <SectionLabel text={STRINGS.common.observation} />
              <p className="text-sm text-cv-stone-700 leading-relaxed">{pattern.coaching_note}</p>
            </div>
          )}

          {/* Zero / no-numerator score (excluding conversational balance) */}
          {!isConversationalBalance && !isPerfectScore && !isMixedScore && (
            <div>
              <SectionLabel text={STRINGS.common.whereYouCanImprove} />
              {hasCoaching && (
                <p className="text-sm text-cv-stone-700 leading-relaxed mb-2">{pattern.coaching_note}</p>
              )}
              {hasQuotes && rewriteTargetQuote && (
                <div>
                  <SectionLabel text={STRINGS.common.forExampleYouSaid} />
                  <EvidenceQuote quote={rewriteTargetQuote} targetSpeaker={targetSpeaker} />
                </div>
              )}
              {pattern.suggested_rewrite && (
                <div className="mt-2">
                  <SectionLabel text={STRINGS.common.nextTimeTry} />
                  <SuggestedRewrite text={pattern.suggested_rewrite} />
                </div>
              )}
              {remainingQuotes.length > 0 && (
                <div className="mt-2">
                  <SectionLabel text={STRINGS.common.otherMoments} />
                  <EvidenceQuoteList quotes={remainingQuotes} targetSpeaker={targetSpeaker} />
                </div>
              )}
            </div>
          )}

        </div>
      )}
    </div>
  );
}

// ─── Grid wrapper ─────────────────────────────────────────────────────────────

interface PatternSnapshotProps {
  patterns: PatternSnapshotItem[];
  targetSpeaker?: string | null;
  trendData?: Record<string, PatternTrendData>;
}

export function PatternSnapshot({ patterns, targetSpeaker, trendData }: PatternSnapshotProps) {
  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
      {patterns.map((p) => (
        <PatternCard
          key={p.pattern_id}
          pattern={p}
          targetSpeaker={targetSpeaker ?? null}
          trend={trendData?.[p.pattern_id]}
        />
      ))}
    </div>
  );
}

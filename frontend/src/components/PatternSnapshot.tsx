'use client';

import { useState, useEffect, useRef, useCallback } from 'react';
import { createPortal } from 'react-dom';
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
  upToRunId?: string,
): Record<string, PatternTrendData> {
  // If upToRunId is provided, only include history up to and including that run.
  let scopedHistory = history;
  if (upToRunId) {
    const idx = history.findIndex((r) => r.run_id === upToRunId);
    if (idx !== -1) {
      scopedHistory = history.slice(0, idx + 1);
    }
  }

  const baselineRuns = scopedHistory.filter((r) => r.is_baseline);
  const postBaselineRuns = scopedHistory.filter((r) => !r.is_baseline);

  if (baselineRuns.length === 0 || postBaselineRuns.length === 0) return {};

  // Collect all pattern IDs across scoped history
  const allPatternIds = new Set<string>();
  for (const run of scopedHistory) {
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
        const num = den > 0 ? p.score * den : 0;
        blNum += num;
        blDen += den;
      }
    }
    const baselineAvg = blDen > 0 ? Math.round((blNum / blDen) * 100) : null;
    if (baselineAvg == null) continue;

    // Build per-run numerator/denominator data for rolling average
    const runData: { num: number; den: number; score: number }[] = [];
    for (const run of scopedHistory) {
      const p = run.patterns.find((x) => x.pattern_id === pid);
      if (p) {
        const den = p.opportunity_count ?? 0;
        const num = den > 0 ? p.score * den : 0;
        runData.push({ num, den, score: p.score });
      } else {
        runData.push({ num: 0, den: 0, score: 0 });
      }
    }

    // Compute rolling average points
    const points: number[] = [];
    for (let idx = 0; idx < scopedHistory.length; idx++) {
      let totalNum = 0, totalDen = 0, scoreSum = 0, scoreCount = 0;
      const start = Math.max(0, idx - windowSize + 1);
      for (let j = start; j <= idx; j++) {
        const d = runData[j];
        if (d.den > 0 || d.score > 0) {
          totalNum += d.num;
          totalDen += d.den;
          scoreSum += d.score;
          scoreCount++;
        }
      }
      const val = totalDen > 0
        ? Math.round((totalNum / totalDen) * 100)
        : scoreCount > 0
          ? Math.round((scoreSum / scoreCount) * 100)
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
  purposeful_framing: (
    <svg viewBox="0 0 16 16" fill="none" className="w-3.5 h-3.5" aria-hidden="true">
      <circle cx="8" cy="8" r="6" stroke="currentColor" strokeWidth={1.4} />
      <circle cx="8" cy="8" r="2.5" stroke="currentColor" strokeWidth={1.4} />
      <path d="M8 2V1M8 15v-1M2 8H1M15 8h-1" stroke="currentColor" strokeWidth={1.4} strokeLinecap="round" />
    </svg>
  ),
  participation_management: (
    <svg viewBox="0 0 16 16" fill="none" className="w-3.5 h-3.5" aria-hidden="true">
      <circle cx="8" cy="4.5" r="2" stroke="currentColor" strokeWidth={1.4} />
      <path d="M4 13c0-2.21 1.79-4 4-4s4 1.79 4 4" stroke="currentColor" strokeWidth={1.4} strokeLinecap="round" />
      <circle cx="2.5" cy="6" r="1.5" stroke="currentColor" strokeWidth={1.2} />
      <path d="M0 13c0-1.66 1.12-3 2.5-3" stroke="currentColor" strokeWidth={1.2} strokeLinecap="round" />
      <circle cx="13.5" cy="6" r="1.5" stroke="currentColor" strokeWidth={1.2} />
      <path d="M16 13c0-1.66-1.12-3-2.5-3" stroke="currentColor" strokeWidth={1.2} strokeLinecap="round" />
    </svg>
  ),
  resolution_and_alignment: (
    <svg viewBox="0 0 16 16" fill="none" className="w-3.5 h-3.5" aria-hidden="true">
      <rect x="3" y="7" width="10" height="7.5" rx="1.5" stroke="currentColor" strokeWidth={1.4} />
      <path d="M5.5 7V5a2.5 2.5 0 015 0v2" stroke="currentColor" strokeWidth={1.4} strokeLinecap="round" />
      <path d="M6 10.5l1.5 1.5 2.5-2.5" stroke="currentColor" strokeWidth={1.4} strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  ),
  assignment_clarity: (
    <svg viewBox="0 0 16 16" fill="none" className="w-3.5 h-3.5" aria-hidden="true">
      <rect x="1.5" y="3" width="13" height="11.5" rx="1.5" stroke="currentColor" strokeWidth={1.4} />
      <path d="M1.5 6.5h13" stroke="currentColor" strokeWidth={1.4} />
      <path d="M5 1.5v3M11 1.5v3" stroke="currentColor" strokeWidth={1.4} strokeLinecap="round" />
      <path d="M4.5 9.5h3M4.5 12h2" stroke="currentColor" strokeWidth={1.4} strokeLinecap="round" />
      <circle cx="11.5" cy="11" r="2" stroke="currentColor" strokeWidth={1.2} />
      <path d="M11.5 9.8V11l.8.8" stroke="currentColor" strokeWidth={1.2} strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  ),
  communication_clarity: (
    <svg viewBox="0 0 16 16" fill="none" className="w-3.5 h-3.5" aria-hidden="true">
      <path d="M4.5 10.5C3.5 9.5 3 8.3 3 7a4 4 0 018 0c0 1.2-.8 2-1.2 2.5-.4.5-.8 1-.8 1.8v.2a1.5 1.5 0 01-3 0" stroke="currentColor" strokeWidth={1.4} strokeLinecap="round" strokeLinejoin="round" />
      <path d="M7 5.5A1.5 1.5 0 005.5 7c0 .6.3 1 .7 1.3" stroke="currentColor" strokeWidth={1.4} strokeLinecap="round" strokeLinejoin="round" />
      <path d="M12 5.5a4.5 4.5 0 010 4" stroke="currentColor" strokeWidth={1.4} strokeLinecap="round" />
      <path d="M13.5 3.5a7 7 0 010 6" stroke="currentColor" strokeWidth={1.4} strokeLinecap="round" />
    </svg>
  ),
  question_quality: (
    <svg viewBox="0 0 16 16" fill="none" className="w-3.5 h-3.5" aria-hidden="true">
      <circle cx="8" cy="8" r="6.5" stroke="currentColor" strokeWidth={1.4} />
      <path d="M6.2 6.2a1.8 1.8 0 013.2 1.1c0 1.8-2.2 1.8-2.2 3.2" stroke="currentColor" strokeWidth={1.4} strokeLinecap="round" />
      <circle cx="7.2" cy="11.8" r="0.6" fill="currentColor" />
    </svg>
  ),
};


// ─── Info popover ─────────────────────────────────────────────────────────────

const HOVER_DELAY_MS = 400;

function InfoPopover({ patternId }: { patternId: string }) {
  const [open, setOpen] = useState(false);
  const [pinned, setPinned] = useState(false);
  const btnRef = useRef<HTMLButtonElement>(null);
  const popoverRef = useRef<HTMLDivElement>(null);
  const hoverTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const leaveTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const [pos, setPos] = useState<{ top: number; left: number } | null>(null);

  const updatePos = useCallback(() => {
    if (!btnRef.current) return;
    const r = btnRef.current.getBoundingClientRect();
    setPos({ top: r.top, left: r.right + 6 });
  }, []);

  useEffect(() => {
    if (!open) return;
    updatePos();
    const dismiss = (e: MouseEvent) => {
      const t = e.target as Node;
      if (btnRef.current?.contains(t) || popoverRef.current?.contains(t)) return;
      setOpen(false);
      setPinned(false);
    };
    document.addEventListener('mousedown', dismiss);
    window.addEventListener('scroll', updatePos, true);
    window.addEventListener('resize', updatePos);
    return () => {
      document.removeEventListener('mousedown', dismiss);
      window.removeEventListener('scroll', updatePos, true);
      window.removeEventListener('resize', updatePos);
    };
  }, [open, updatePos]);

  useEffect(() => {
    return () => {
      if (hoverTimer.current) clearTimeout(hoverTimer.current);
      if (leaveTimer.current) clearTimeout(leaveTimer.current);
    };
  }, []);

  const handleMouseEnter = () => {
    if (leaveTimer.current) { clearTimeout(leaveTimer.current); leaveTimer.current = null; }
    hoverTimer.current = setTimeout(() => setOpen(true), HOVER_DELAY_MS);
  };

  const handleMouseLeave = () => {
    if (hoverTimer.current) { clearTimeout(hoverTimer.current); hoverTimer.current = null; }
    if (!pinned) {
      leaveTimer.current = setTimeout(() => setOpen(false), 200);
    }
  };

  const handlePopoverEnter = () => {
    if (leaveTimer.current) { clearTimeout(leaveTimer.current); leaveTimer.current = null; }
  };

  const handlePopoverLeave = () => {
    if (!pinned) {
      leaveTimer.current = setTimeout(() => setOpen(false), 200);
    }
  };

  const explanation = STRINGS.patternExplanations[patternId];
  if (!explanation) return null;

  return (
    <>
      <button
        ref={btnRef}
        onClick={(e) => { e.stopPropagation(); setPinned((v) => !v); setOpen((v) => !v); }}
        onMouseEnter={handleMouseEnter}
        onMouseLeave={handleMouseLeave}
        className="ml-1 text-cv-stone-400 hover:text-cv-stone-600 transition-colors align-middle leading-none"
        aria-label="Pattern explanation"
        type="button"
      >
        <svg className="w-3.5 h-3.5 inline" viewBox="0 0 20 20" fill="currentColor" aria-hidden="true">
          <path fillRule="evenodd" d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7-4a1 1 0 11-2 0 1 1 0 012 0zM9 9a1 1 0 000 2v3a1 1 0 001 1h1a1 1 0 100-2v-3a1 1 0 00-1-1H9z" clipRule="evenodd" />
        </svg>
      </button>
      {open && pos && createPortal(
        <div
          ref={popoverRef}
          className="fixed z-[9999] w-64 bg-white border border-cv-warm-200 rounded shadow-lg p-3 text-sm text-cv-stone-700 leading-snug"
          style={{ top: pos.top, left: pos.left }}
          onMouseEnter={handlePopoverEnter}
          onMouseLeave={handlePopoverLeave}
        >
          {explanation}
        </div>,
        document.body,
      )}
    </>
  );
}

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
    <blockquote className="border-l-[2px] border-cv-teal-700 pl-4 pr-3 py-2.5 bg-cv-teal-50 rounded-r my-2">
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

const SPARKLINE_TEAL  = '#0F6E56'; // cv-teal-600
const SPARKLINE_AMBER = '#D97706'; // cv-amber-600
const SPARKLINE_RED   = '#E24B4A'; // cv-red-400

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

export function PatternCard({
  pattern,
  targetSpeaker,
  trend,
  highlightType,
}: {
  pattern: PatternSnapshotItem;
  targetSpeaker: string | null;
  trend?: PatternTrendData;
  highlightType?: 'strength' | 'focus' | null;
}) {
  const [expanded, setExpanded] = useState(false);

  const quotes      = pattern.quotes ?? [];
  const hasQuotes    = quotes.length > 0;
  const hasCoaching  = !!pattern.coaching_note;
  const hasNotes     = !!pattern.notes;
  const isBalanced   = pattern.balance_assessment === 'balanced';

  const isExpandable = hasQuotes || hasCoaching || hasNotes;

  const score = pattern.score;
  const hasMissedOpportunities =
    pattern.evaluable_status === 'evaluable' &&
    score != null &&
    score < 1;

  const isPerfectScore =
    pattern.evaluable_status === 'evaluable' &&
    score != null &&
    score >= 1;

  const isMixedScore = hasMissedOpportunities && score != null && score > 0;

  const rewriteSpanId   = pattern.rewrite_for_span_id;
  const successSpanIds  = new Set(pattern.success_span_ids ?? []);

  // Split quotes into three groups using success_span_ids from the LLM:
  // 1. rewriteTargetQuote — the missed-opportunity quote paired with suggested_rewrite
  // 2. successQuotes — spans the speaker did well on
  // 3. otherFailureQuotes — other missed opportunities (excluding the rewrite target)
  const rewriteTargetQuotes = rewriteSpanId
    ? quotes.filter((q) => q.span_id === rewriteSpanId)
    : [];

  const successQuotes = quotes.filter(
    (q) => q.span_id != null && successSpanIds.has(q.span_id)
  );

  const otherFailureQuotes = quotes.filter(
    (q) => q.span_id !== rewriteSpanId && !(q.span_id != null && successSpanIds.has(q.span_id))
  );

  // Determine if we should show sparkline for this pattern
  const showSparkline = !!trend && trend.points.length >= 2;

  const highlightBorder = highlightType === 'strength'
    ? 'border-l-[3px] border-l-cv-teal-500'
    : highlightType === 'focus'
      ? 'border-l-[3px] border-l-cv-amber-500'
      : '';

  return (
    <div className={`bg-white border border-cv-stone-400 rounded overflow-hidden${expanded ? ' sm:col-span-2' : ''} ${highlightBorder}`}>
      {/* ── Card header row ── */}
      <button
        type="button"
        onClick={() => isExpandable && setExpanded(!expanded)}
        className={[
          'w-full px-4 py-3 text-left',
          isExpandable ? 'cursor-pointer hover:bg-cv-warm-100 transition-colors' : 'cursor-default',
        ].join(' ')}
      >
        <div className="flex items-center justify-between mb-0.5">
          {/* Pattern name + highlight badge */}
          <span className="text-sm font-medium text-cv-stone-800 leading-snug flex items-center gap-1.5">
            {PATTERN_ICONS[pattern.pattern_id] && (
              <span className="text-cv-stone-400 inline-flex items-center">
                {PATTERN_ICONS[pattern.pattern_id]}
              </span>
            )}
            {STRINGS.patternLabels[pattern.pattern_id] ?? pattern.pattern_id}
            <InfoPopover patternId={pattern.pattern_id} />
            {highlightType === 'strength' && (
              <span className="ml-1 inline-flex items-center px-1.5 py-0.5 rounded text-2xs font-medium bg-cv-teal-50 text-cv-teal-700">
                {STRINGS.highlightBadges.strength}
              </span>
            )}
            {highlightType === 'focus' && (
              <span className="ml-1 inline-flex items-center px-1.5 py-0.5 rounded text-2xs font-medium bg-cv-amber-50 text-cv-amber-700">
                {STRINGS.highlightBadges.focus}
              </span>
            )}
          </span>

          {/* Chevron */}
          <div className="flex items-center gap-1.5 shrink-0 ml-2">
            {isExpandable && <Chevron open={expanded} />}
          </div>
        </div>

        {/* Score row */}
        {pattern.evaluable_status === 'evaluable' && pattern.score != null ? (
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
            <>
              <RatioBar ratio={pattern.score} />
              {pattern.balance_assessment && (
                <div className="mt-1">
                  <BalanceBadge assessment={pattern.balance_assessment} />
                </div>
              )}
            </>
          )
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
        <div className="border-t border-cv-warm-300 px-4 pb-4 pt-3 space-y-3">

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

          {/* Mixed score */}
          {isMixedScore && (
            <>
              {(successQuotes.length > 0 || hasNotes) && (
                <div>
                  <SectionLabel text={STRINGS.common.whatYouDidWell} />
                  {hasNotes && (
                    <p className="text-sm text-cv-stone-700 leading-relaxed mb-2">{pattern.notes}</p>
                  )}
                  {successQuotes.length > 0 && (
                    <EvidenceQuoteList quotes={successQuotes} targetSpeaker={targetSpeaker} />
                  )}
                </div>
              )}
              {(hasCoaching || rewriteTargetQuotes.length > 0 || pattern.suggested_rewrite || otherFailureQuotes.length > 0) && (
                <div>
                  <SectionLabel text={STRINGS.common.whereYouCanImprove} />
                  {hasCoaching && (
                    <p className="text-sm text-cv-stone-700 leading-relaxed mb-2">{pattern.coaching_note}</p>
                  )}
                  {rewriteTargetQuotes.length > 0 && (
                    <div>
                      <SectionLabel text={STRINGS.common.forExampleYouSaid} />
                      <EvidenceQuoteList quotes={rewriteTargetQuotes} targetSpeaker={targetSpeaker} />
                    </div>
                  )}
                  {pattern.suggested_rewrite && (
                    <div className="mt-2">
                      <SectionLabel text={STRINGS.common.nextTimeTry} />
                      <SuggestedRewrite text={pattern.suggested_rewrite} />
                    </div>
                  )}
                  {otherFailureQuotes.length > 0 && (
                    <div className="mt-2">
                      <SectionLabel text={STRINGS.common.otherMoments} />
                      <EvidenceQuoteList quotes={otherFailureQuotes} targetSpeaker={targetSpeaker} />
                    </div>
                  )}
                </div>
              )}
            </>
          )}

          {/* Zero / no-numerator score */}
          {!isPerfectScore && !isMixedScore &&
            (hasCoaching || rewriteTargetQuotes.length > 0 || pattern.suggested_rewrite || otherFailureQuotes.length > 0) && (
            <div>
              <SectionLabel text={STRINGS.common.whereYouCanImprove} />
              {hasCoaching && (
                <p className="text-sm text-cv-stone-700 leading-relaxed mb-2">{pattern.coaching_note}</p>
              )}
              {rewriteTargetQuotes.length > 0 && (
                <div>
                  <SectionLabel text={STRINGS.common.forExampleYouSaid} />
                  <EvidenceQuoteList quotes={rewriteTargetQuotes} targetSpeaker={targetSpeaker} />
                </div>
              )}
              {pattern.suggested_rewrite && (
                <div className="mt-2">
                  <SectionLabel text={STRINGS.common.nextTimeTry} />
                  <SuggestedRewrite text={pattern.suggested_rewrite} />
                </div>
              )}
              {otherFailureQuotes.length > 0 && (
                <div className="mt-2">
                  <SectionLabel text={STRINGS.common.otherMoments} />
                  <EvidenceQuoteList quotes={otherFailureQuotes} targetSpeaker={targetSpeaker} />
                </div>
              )}
            </div>
          )}

        </div>
      )}
    </div>
  );
}

// ─── Cluster header ───────────────────────────────────────────────────────────

function ClusterHeader({ clusterId }: { clusterId: string }) {
  const label = STRINGS.clusterLabels[clusterId] ?? clusterId;
  return (
    <div className="sm:col-span-2 pt-4 first:pt-0">
      <p className="text-2xs font-semibold uppercase tracking-[0.14em] text-cv-stone-400">
        {label}
      </p>
      <div className="border-b border-cv-warm-200 mt-1.5" />
    </div>
  );
}

// ─── Grid wrapper ─────────────────────────────────────────────────────────────

interface PatternSnapshotProps {
  patterns: PatternSnapshotItem[];
  targetSpeaker?: string | null;
  trendData?: Record<string, PatternTrendData>;
  excludePatternIds?: string[];
  /** When true, group patterns by cluster with cluster headers. */
  groupByCluster?: boolean;
  /** Pattern IDs that should show a "Strength" badge. */
  strengthPatternIds?: string[];
  /** Pattern ID that should show a "Focus area" badge. */
  focusPatternId?: string | null;
}

export function PatternSnapshot({
  patterns,
  targetSpeaker,
  trendData,
  excludePatternIds,
  groupByCluster,
  strengthPatternIds,
  focusPatternId,
}: PatternSnapshotProps) {
  const filtered = excludePatternIds?.length
    ? patterns.filter((p) => !excludePatternIds.includes(p.pattern_id))
    : patterns;

  if (filtered.length === 0) return null;

  const strengthSet = new Set(strengthPatternIds ?? []);

  function getHighlightType(patternId: string): 'strength' | 'focus' | null {
    if (strengthSet.has(patternId)) return 'strength';
    if (focusPatternId === patternId) return 'focus';
    return null;
  }

  if (!groupByCluster) {
    return (
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        {filtered.map((p) => (
          <PatternCard
            key={p.pattern_id}
            pattern={p}
            targetSpeaker={targetSpeaker ?? null}
            trend={trendData?.[p.pattern_id]}
            highlightType={getHighlightType(p.pattern_id)}
          />
        ))}
      </div>
    );
  }

  // Group patterns by cluster in defined order
  const clusterOrder = STRINGS.clusterOrder;
  const byCluster: Record<string, PatternSnapshotItem[]> = {};
  for (const p of filtered) {
    const cid = p.cluster_id ?? 'unknown';
    if (!byCluster[cid]) byCluster[cid] = [];
    byCluster[cid].push(p);
  }

  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
      {clusterOrder.map((cid) => {
        const clusterPatterns = byCluster[cid];
        if (!clusterPatterns || clusterPatterns.length === 0) return null;
        return [
          <ClusterHeader key={`header-${cid}`} clusterId={cid} />,
          ...clusterPatterns.map((p) => (
            <PatternCard
              key={p.pattern_id}
              pattern={p}
              targetSpeaker={targetSpeaker ?? null}
              trend={trendData?.[p.pattern_id]}
              highlightType={getHighlightType(p.pattern_id)}
            />
          )),
        ];
      })}
    </div>
  );
}

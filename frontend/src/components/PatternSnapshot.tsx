'use client';

import { useState, useEffect, useRef, useCallback } from 'react';
import { createPortal } from 'react-dom';
import { LineChart, Line, ResponsiveContainer } from 'recharts';
import type { PatternSnapshotItem, PatternCoachingItem, RunHistoryPoint } from '@/lib/types';
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
  _windowSize?: number,
  upToRunId?: string,
): Record<string, PatternTrendData> {
  // Rolling average disabled — always use window of 1 (show each meeting's
  // actual score). The _windowSize parameter is kept for call-site compat.
  const windowSize = 1;
  // If upToRunId is provided, only include history up to and including that run.
  // If the run isn't found in the history, return empty so the UI falls back to
  // showing the raw score from the run response instead of stale trend data.
  let scopedHistory = history;
  if (upToRunId) {
    const idx = history.findIndex((r) => r.run_id === upToRunId);
    if (idx !== -1) {
      scopedHistory = history.slice(0, idx + 1);
    } else {
      return {};
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

export const PATTERN_ICONS: Record<string, JSX.Element> = {
  purposeful_framing: (
    <svg viewBox="0 0 16 16" fill="none" className="w-3.5 h-3.5" aria-hidden="true">
      <rect x="1.5" y="1.5" width="13" height="13" rx="1.5" stroke="currentColor" strokeWidth={1.4} />
      <path d="M10 4.5h2v2" stroke="currentColor" strokeWidth={1.4} strokeLinecap="round" strokeLinejoin="round" />
      <path d="M6 11.5H4v-2" stroke="currentColor" strokeWidth={1.4} strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  ),
  focus_management: (
    <svg viewBox="0 0 16 16" fill="none" className="w-3.5 h-3.5" aria-hidden="true">
      <circle cx="8" cy="8" r="6" stroke="currentColor" strokeWidth={1.4} />
      <circle cx="8" cy="8" r="2.5" stroke="currentColor" strokeWidth={1.4} />
      <path d="M8 2V1M8 15v-1M2 8H1M15 8h-1" stroke="currentColor" strokeWidth={1.4} strokeLinecap="round" />
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
      <circle cx="5" cy="5" r="2" stroke="currentColor" strokeWidth={1.4} />
      <path d="M1 14a4 4 0 018 0" stroke="currentColor" strokeWidth={1.4} strokeLinecap="round" />
      <path d="M11 5a2.5 2.5 0 010 3" stroke="currentColor" strokeWidth={1.4} strokeLinecap="round" />
      <path d="M13 3.5a5 5 0 010 6" stroke="currentColor" strokeWidth={1.4} strokeLinecap="round" />
    </svg>
  ),
  question_quality: (
    <svg viewBox="0 0 16 16" fill="none" className="w-3.5 h-3.5" aria-hidden="true">
      <circle cx="8" cy="8" r="6.5" stroke="currentColor" strokeWidth={1.4} />
      <path d="M6.2 6.2a1.8 1.8 0 013.2 1.1c0 1.8-2.2 1.8-2.2 3.2" stroke="currentColor" strokeWidth={1.4} strokeLinecap="round" />
      <circle cx="7.2" cy="11.8" r="0.6" fill="currentColor" />
    </svg>
  ),
  disagreement_navigation: (
    <svg viewBox="0 0 16 16" fill="none" className="w-3.5 h-3.5" aria-hidden="true">
      <path d="M8 1.5L14.5 13a.5.5 0 01-.43.75H1.93a.5.5 0 01-.43-.75L8 1.5z" stroke="currentColor" strokeWidth={1.4} strokeLinejoin="round" />
      <path d="M8 6v3.5" stroke="currentColor" strokeWidth={1.4} strokeLinecap="round" />
      <circle cx="8" cy="11.5" r="0.7" fill="currentColor" />
    </svg>
  ),
  feedback_quality: (
    <svg viewBox="0 0 16 16" fill="none" className="w-3.5 h-3.5" aria-hidden="true">
      <path d="M2 2.5h12A1.5 1.5 0 0115.5 4v6a1.5 1.5 0 01-1.5 1.5H5L2 14v-2.5h-.5A1.5 1.5 0 010 10V4A1.5 1.5 0 011.5 2.5z" stroke="currentColor" strokeWidth={1.4} strokeLinejoin="round" />
      <circle cx="4.5" cy="7" r="1" fill="currentColor" />
      <circle cx="8" cy="7" r="1" fill="currentColor" />
      <circle cx="11.5" cy="7" r="1" fill="currentColor" />
    </svg>
  ),
  behavioral_integrity: (
    <svg viewBox="0 0 16 16" fill="none" className="w-3.5 h-3.5" aria-hidden="true">
      <path d="M8 1.5L2 4v4.5c0 3.5 2.5 5.5 6 7 3.5-1.5 6-3.5 6-7V4L8 1.5z" stroke="currentColor" strokeWidth={1.4} strokeLinejoin="round" />
      <path d="M5.5 8l2 2 3-3.5" stroke="currentColor" strokeWidth={1.4} strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  ),
  active_listening: (
    <svg className="w-4 h-4" viewBox="0 0 32 32" fill="currentColor" xmlns="http://www.w3.org/2000/svg">
      <path d="M16.97 1.25c-4.86 0-9.78 3.692-9.78 10.75 0 0.414 0.336 0.75 0.75 0.75s0.75-0.336 0.75-0.75c0-6.355 4.292-9.25 8.28-9.25s8.28 2.895 8.28 9.25c0.005 0.122 0.007 0.265 0.007 0.409 0 0.756-0.071 1.496-0.206 2.213l0.012-0.074c-0.373 1.716-1.119 3.218-2.151 4.476l0.015-0.018c-0.197 0.238-0.416 0.455-0.631 0.67-0.357 0.338-0.68 0.704-0.97 1.097l-0.016 0.023c-0.415 0.612-0.823 1.32-1.18 2.057l-0.045 0.103c-0.256 0.47-0.499 1.025-0.696 1.601l-0.023 0.078c-0.09 0.299-0.153 0.648-0.177 1.007l-0.001 0.015c-0.016 0.257-0.056 0.496-0.119 0.726l0.006-0.025c-0.091 0.311-0.195 0.576-0.318 0.829l0.014-0.031c-0.252 0.485-0.574 0.897-0.96 1.24l-0.004 0.004c-0.805 0.687-1.821 1.149-2.938 1.279l-0.026 0.002c-0.25 0.034-0.538 0.054-0.831 0.054-0.894 0-1.745-0.181-2.52-0.509l0.042 0.016c-1.001-0.418-1.802-1.151-2.296-2.073l-0.012-0.024c-0.3-0.609-0.476-1.326-0.476-2.084 0-0.021 0-0.043 0-0.064l0 0.003c0-0.414-0.336-0.75-0.75-0.75s-0.75 0.336-0.75 0.75c0 0.017 0 0.038 0 0.058 0 1.004 0.234 1.953 0.652 2.795l-0.016-0.037c0.667 1.262 1.727 2.242 3.015 2.79l0.04 0.015c0.889 0.389 1.926 0.615 3.015 0.615 0.011 0 0.022 0 0.032 0 0.001 0 0.003 0 0.004 0 0.368 0 0.73-0.024 1.086-0.071l-0.042 0.005c1.457-0.168 2.75-0.763 3.778-1.656l-0.009 0.007c0.528-0.47 0.965-1.029 1.29-1.656l0.015-0.032c0.144-0.288 0.28-0.629 0.386-0.983l0.012-0.047c0.088-0.294 0.15-0.636 0.173-0.988l0.001-0.014c0.017-0.264 0.058-0.51 0.123-0.747l-0.006 0.026c0.195-0.569 0.408-1.051 0.655-1.51l-0.026 0.053c0.365-0.767 0.736-1.413 1.149-2.029l-0.036 0.056c0.253-0.339 0.521-0.638 0.813-0.913l0.004-0.003c0.25-0.25 0.5-0.5 0.729-0.777 1.165-1.418 2.019-3.136 2.431-5.019l0.015-0.079c0.145-0.729 0.228-1.567 0.228-2.425 0-0.153-0.003-0.305-0.008-0.457l0.001 0.022c0-7.058-4.92-10.75-9.78-10.75z"/>
      <path d="M17.175 16.774c-0.133 0.037-0.288 0.063-0.448 0.071l-0.005 0c-1.98 0.323-3.473 2.022-3.473 4.068 0 0.030 0 0.060 0.001 0.090l0-0.005c0 2.34-2.5 2.34-2.5 0 0-0.414-0.336-0.75-0.75-0.75s-0.75 0.336-0.75 0.75c-0.011 0.093-0.017 0.2-0.017 0.309 0 1.552 1.225 2.819 2.761 2.886l0.006 0c1.542-0.067 2.767-1.334 2.767-2.886 0-0.109-0.006-0.216-0.018-0.322l0.001 0.013c0-0.011 0-0.024 0-0.037 0-1.342 0.989-2.453 2.279-2.643l0.015-0.002c0.315-0.019 0.607-0.101 0.868-0.234l-0.012 0.006c0.247-0.148 0.453-0.337 0.615-0.561l0.004-0.006c0.708-0.865 1.138-1.981 1.138-3.199 0-1.094-0.347-2.108-0.937-2.936l0.011 0.015c-0.864-1.159-2.23-1.901-3.77-1.901-0.848 0-1.644 0.225-2.331 0.619l0.023-0.012c0.447-2.039 2.22-3.549 4.353-3.587l0.004 0c0.007 0 0.015 0 0.023 0 1.228 0 2.337 0.509 3.128 1.328l0.001 0.001c0.915 1.022 1.474 2.378 1.474 3.866 0 0.1-0.003 0.198-0.007 0.297l0.001-0.014c0 0.414 0.336 0.75 0.75 0.75s0.75-0.336 0.75-0.75c0.020-0.188 0.031-0.406 0.031-0.626 0-3.438-2.73-6.238-6.14-6.351l-0.010 0c-3.42 0.114-6.149 2.914-6.149 6.351 0 0.221 0.011 0.438 0.033 0.653l-0.002-0.027c0 0.414 0.336 0.75 0.75 0.75 0.347-0.003 0.636-0.244 0.713-0.568l0.001-0.005c0.034-0.027 0.082-0.021 0.112-0.054 0.601-0.687 1.479-1.119 2.458-1.119 1.062 0 2.005 0.508 2.6 1.294l0.006 0.008c0.392 0.564 0.626 1.264 0.626 2.018 0 0.871-0.312 1.669-0.831 2.288l0.005-0.006c-0.043 0.065-0.095 0.12-0.154 0.167l-0.002 0.001z"/>
    </svg>
  ),
  recognition: (
    <svg className="w-4 h-4" viewBox="0 0 64 64" fill="none" stroke="currentColor" strokeWidth="3" xmlns="http://www.w3.org/2000/svg">
      <circle cx="33.52" cy="39.9" r="20.42" strokeLinecap="round"/>
      <circle cx="33.52" cy="39.9" r="15.22" strokeLinecap="round"/>
      <path d="M33.28,30.49,36,36a.1.1,0,0,0,.08.05l6,.88a.1.1,0,0,1,.06.17l-4.38,4.27a.08.08,0,0,0,0,.09l1,6a.09.09,0,0,1-.14.1l-5.42-2.84a.08.08,0,0,0-.09,0l-5.41,2.84a.1.1,0,0,1-.15-.1l1-6a.14.14,0,0,0,0-.09l-4.38-4.27a.1.1,0,0,1,.05-.17L30.32,36a.08.08,0,0,0,.07-.05l2.71-5.49A.1.1,0,0,1,33.28,30.49Z" strokeLinecap="round"/>
      <polyline points="21.48 23.75 9.89 3.67 19.97 3.67 29.04 19.38 19.97 3.67"/>
      <polyline points="44.82 22.89 55.92 3.67 45.79 3.67 36.77 19.38" strokeLinecap="round"/>
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
          className="fixed z-[9999] w-64 bg-white border border-cv-warm-300 rounded shadow-lg p-3 text-sm text-cv-stone-700 leading-snug"
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
  coaching,
  targetSpeaker,
  trend,
  highlightType,
}: {
  pattern: PatternSnapshotItem;
  coaching?: PatternCoachingItem | null;
  targetSpeaker: string | null;
  trend?: PatternTrendData;
  highlightType?: 'strength' | 'focus' | null;
}) {
  const [expanded, setExpanded] = useState(false);

  const quotes      = pattern.quotes ?? [];
  const hasQuotes    = quotes.length > 0;
  const hasCoaching  = !!coaching?.coaching_note;
  const hasNotes     = !!coaching?.notes;
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

  const rewriteSpanId   = coaching?.rewrite_for_span_id;
  const successSpanIds  = new Set(pattern.success_span_ids ?? []);

  // Split quotes into groups using success_span_ids from the LLM:
  // 1. rewriteTargetQuotes — the missed-opportunity quote paired with suggested_rewrite
  // 2. successQuotes — spans the speaker did well on
  // 3. bestSuccessQuotes — the single most compelling success example
  const rewriteTargetQuotes = rewriteSpanId
    ? quotes.filter((q) => q.span_id === rewriteSpanId)
    : [];

  const successQuotes = quotes.filter(
    (q) => q.span_id != null && successSpanIds.has(q.span_id)
  );

  const bestSuccessSpanId = coaching?.best_success_span_id;
  const bestSuccessQuotes = (() => {
    if (bestSuccessSpanId) {
      const matched = successQuotes.filter((q) => q.span_id === bestSuccessSpanId);
      if (matched.length > 0) return matched;
    }
    return successQuotes.length > 0 ? [successQuotes[0]] : [];
  })();

  // Determine if we should show sparkline for this pattern
  const showSparkline = !!trend && trend.points.length >= 2;

  const highlightBorder = 'border border-cv-stone-400';

  const highlightBg = '';

  return (
    <div className={`bg-cv-warm-50 rounded overflow-hidden${expanded ? ' sm:col-span-2' : ''} ${highlightBorder}`}>
      {/* ── Card header row ── */}
      <button
        type="button"
        onClick={() => isExpandable && setExpanded(!expanded)}
        className={[
          'w-full px-4 py-3 text-left',
          highlightBg || (isExpandable ? 'hover:bg-cv-warm-100' : ''),
          isExpandable ? 'cursor-pointer transition-colors' : 'cursor-default',
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
              <span className="ml-1 inline-flex items-center px-1.5 py-0.5 rounded text-2xs font-medium bg-cv-teal-50 text-cv-teal-700 border border-cv-teal-700">
                {STRINGS.highlightBadges.strength}
              </span>
            )}
            {highlightType === 'focus' && (
              <span className="ml-1 inline-flex items-center px-1.5 py-0.5 rounded text-2xs font-medium bg-cv-rose-50 text-cv-rose-700 border border-cv-rose-700">
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
            </>
          )
        ) : (
          <span className="text-xs text-cv-stone-400 capitalize">
            {pattern.evaluable_status === 'not_evaluable'
              ? STRINGS.evaluableStatus.not_evaluable
              : STRINGS.evaluableStatus.insufficient_signal}
          </span>
        )}
      </button>

      {/* ── Expanded detail ── */}
      {expanded && (
        <div className="border-t border-cv-warm-300 px-4 pb-4 pt-3 space-y-3 bg-white">

          {/* Perfect score */}
          {isPerfectScore && (bestSuccessQuotes.length > 0 || hasNotes) && (
            <div>
              <SectionLabel text={STRINGS.common.whatYouDidWell} />
              {hasNotes && (
                <p className="text-sm text-cv-stone-700 leading-relaxed mb-2">{coaching?.notes}</p>
              )}
              <EvidenceQuoteList quotes={bestSuccessQuotes} targetSpeaker={targetSpeaker} />
            </div>
          )}

          {/* Mixed score */}
          {isMixedScore && (
            <>
              {(bestSuccessQuotes.length > 0 || hasNotes) && (
                <div>
                  <SectionLabel text={STRINGS.common.whatYouDidWell} />
                  {hasNotes && (
                    <p className="text-sm text-cv-stone-700 leading-relaxed mb-2">{coaching?.notes}</p>
                  )}
                  {bestSuccessQuotes.length > 0 && (
                    <EvidenceQuoteList quotes={bestSuccessQuotes} targetSpeaker={targetSpeaker} />
                  )}
                </div>
              )}
              {(hasCoaching || rewriteTargetQuotes.length > 0 || coaching?.suggested_rewrite) && (
                <div>
                  <SectionLabel text={STRINGS.common.whereYouCanImprove} />
                  {hasCoaching && (
                    <p className="text-sm text-cv-stone-700 leading-relaxed mb-2">{coaching?.coaching_note}</p>
                  )}
                  {rewriteTargetQuotes.length > 0 && (
                    rewriteSpanId && rewriteSpanId === bestSuccessSpanId ? (
                      <p className="text-xs text-cv-stone-400 italic mb-2">{STRINGS.common.referringToExampleAbove}</p>
                    ) : (
                      <div>
                        <SectionLabel text={STRINGS.common.forExampleYouSaid} />
                        <EvidenceQuoteList quotes={rewriteTargetQuotes} targetSpeaker={targetSpeaker} />
                      </div>
                    )
                  )}
                  {coaching?.suggested_rewrite && (
                    <div className="mt-2">
                      <SectionLabel text={STRINGS.common.nextTimeTry} />
                      <SuggestedRewrite text={coaching?.suggested_rewrite} />
                    </div>
                  )}
                </div>
              )}
            </>
          )}

          {/* Zero / no-numerator score */}
          {!isPerfectScore && !isMixedScore &&
            (hasCoaching || rewriteTargetQuotes.length > 0 || coaching?.suggested_rewrite) && (
            <div>
              <SectionLabel text={STRINGS.common.whereYouCanImprove} />
              {hasCoaching && (
                <p className="text-sm text-cv-stone-700 leading-relaxed mb-2">{coaching?.coaching_note}</p>
              )}
              {rewriteTargetQuotes.length > 0 && (
                rewriteSpanId && rewriteSpanId === bestSuccessSpanId ? (
                  <p className="text-xs text-cv-stone-400 italic mb-2">{STRINGS.common.referringToExampleAbove}</p>
                ) : (
                  <div>
                    <SectionLabel text={STRINGS.common.forExampleYouSaid} />
                    <EvidenceQuoteList quotes={rewriteTargetQuotes} targetSpeaker={targetSpeaker} />
                  </div>
                )
              )}
              {coaching?.suggested_rewrite && (
                <div className="mt-2">
                  <SectionLabel text={STRINGS.common.nextTimeTry} />
                  <SuggestedRewrite text={coaching?.suggested_rewrite} />
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
      <div className="border-b border-cv-warm-300 mt-1.5" />
    </div>
  );
}

function SubClusterHeader({ subClusterId }: { subClusterId: string }) {
  const label = STRINGS.subClusterLabels[subClusterId] ?? subClusterId;
  return (
    <div className="sm:col-span-2 pt-2">
      <p className="text-2xs font-medium tracking-[0.08em] text-cv-stone-400/80">
        {label}
      </p>
    </div>
  );
}

// ─── Grid wrapper ─────────────────────────────────────────────────────────────

interface PatternSnapshotProps {
  patterns: PatternSnapshotItem[];
  patternCoaching?: PatternCoachingItem[];
  targetSpeaker?: string | null;
  trendData?: Record<string, PatternTrendData>;
  excludePatternIds?: string[];
  /** When true, group patterns by cluster with cluster headers. */
  groupByCluster?: boolean;
  /** Pattern IDs that should show a "Strength" badge. */
  strengthPatternIds?: string[];
  /** Pattern IDs that should show a "Growth area" badge. */
  growthAreaPatternIds?: string[];
}

export function PatternSnapshot({
  patterns,
  patternCoaching,
  targetSpeaker,
  trendData,
  excludePatternIds,
  groupByCluster,
  strengthPatternIds,
  growthAreaPatternIds,
}: PatternSnapshotProps) {
  const filtered = excludePatternIds?.length
    ? patterns.filter((p) => !excludePatternIds.includes(p.pattern_id))
    : patterns;

  if (filtered.length === 0) return null;

  // Build coaching lookup by pattern_id
  const coachingByPatternId: Record<string, PatternCoachingItem> = {};
  for (const pc of patternCoaching ?? []) {
    coachingByPatternId[pc.pattern_id] = pc;
  }

  const strengthSet = new Set(strengthPatternIds ?? []);
  const growthAreaSet = new Set(growthAreaPatternIds ?? []);

  function getHighlightType(patternId: string): 'strength' | 'focus' | null {
    // Growth area takes precedence if both apply
    if (growthAreaSet.has(patternId)) return 'focus';
    if (strengthSet.has(patternId)) return 'strength';
    return null;
  }

  if (!groupByCluster) {
    return (
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        {filtered.map((p) => (
          <PatternCard
            key={p.pattern_id}
            pattern={p}
            coaching={coachingByPatternId[p.pattern_id]}
            targetSpeaker={targetSpeaker ?? null}
            trend={trendData?.[p.pattern_id]}
            highlightType={getHighlightType(p.pattern_id)}
          />
        ))}
      </div>
    );
  }

  // Group patterns by axis with sub-cluster headers
  const clusterOrder = STRINGS.clusterOrder;
  const axisGrouping = STRINGS.axisPatternGrouping;
  const filteredIds = new Set(filtered.map((p) => p.pattern_id));
  const patternById: Record<string, PatternSnapshotItem> = {};
  for (const p of filtered) patternById[p.pattern_id] = p;

  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
      {clusterOrder.map((axisId) => {
        const groups = axisGrouping[axisId];
        if (!groups) return null;
        // Check if any patterns in this axis exist in the data
        const axisHasPatterns = groups.some((g) =>
          g.patterns.some((pid) => filteredIds.has(pid))
        );
        if (!axisHasPatterns) return null;

        return [
          <ClusterHeader key={`axis-${axisId}`} clusterId={axisId} />,
          ...groups.flatMap((group) => {
            const groupPatterns = group.patterns.filter((pid) => filteredIds.has(pid));
            if (groupPatterns.length === 0) return [];
            return [
              ...(group.subCluster != null
                ? [<SubClusterHeader key={`sub-${group.subCluster}`} subClusterId={group.subCluster} />]
                : []),
              ...groupPatterns.map((pid) => (
                <PatternCard
                  key={pid}
                  pattern={patternById[pid]}
                  coaching={coachingByPatternId[pid]}
                  targetSpeaker={targetSpeaker ?? null}
                  trend={trendData?.[pid]}
                  highlightType={getHighlightType(pid)}
                />
              )),
            ];
          }),
        ];
      })}
    </div>
  );
}

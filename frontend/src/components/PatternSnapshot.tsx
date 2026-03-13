'use client';

import { useState } from 'react';
import type { PatternSnapshotItem } from '@/lib/types';
import { EvidenceQuote } from './EvidenceQuote';
import { STRINGS } from '@/config/strings';

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
    <blockquote className="border-l-[3px] border-cv-teal-400 pl-4 pr-3 py-2.5 bg-cv-teal-50 rounded-r-lg my-2">
      <p className="text-sm text-cv-stone-700 font-serif italic leading-relaxed">
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

// ─── Ratio bar ────────────────────────────────────────────────────────────────

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

function PatternCard({ pattern }: { pattern: PatternSnapshotItem }) {
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

  return (
    <div className="bg-white border border-cv-warm-200 rounded-xl overflow-hidden">
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
            {STRINGS.patternIcons[pattern.pattern_id] && (
              <span className="mr-1.5">{STRINGS.patternIcons[pattern.pattern_id]}</span>
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
          <RatioBar ratio={pattern.ratio} />
        ) : pattern.evaluable_status === 'evaluable' && pattern.balance_assessment ? (
          <div className="mt-1">
            <BalanceBadge assessment={pattern.balance_assessment} />
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
              {quotes.map((q, i) => <EvidenceQuote key={i} quote={q} />)}
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
                  {successQuotes.map((q, i) => <EvidenceQuote key={i} quote={q} />)}
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
                    <EvidenceQuote quote={improvementQuotes[0]} />
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
                    {improvementQuotes.slice(1).map((q, i) => <EvidenceQuote key={i} quote={q} />)}
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
                {hasQuotes && (
                  <div>
                    <SectionLabel text={STRINGS.common.forExampleYouSaid} />
                    <EvidenceQuote quote={quotes[0]} />
                  </div>
                )}
                {pattern.suggested_rewrite && (
                  <div className="mt-2">
                    <SectionLabel text={STRINGS.common.nextTimeTry} />
                    <SuggestedRewrite text={pattern.suggested_rewrite} />
                  </div>
                )}
                {quotes.length > 1 && (
                  <div className="mt-2">
                    <SectionLabel text={STRINGS.common.otherMoments} />
                    {quotes.slice(1).map((q, i) => <EvidenceQuote key={i} quote={q} />)}
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
              {hasQuotes && (
                <div>
                  <SectionLabel text={STRINGS.common.forExampleYouSaid} />
                  <EvidenceQuote quote={quotes[0]} />
                </div>
              )}
              {pattern.suggested_rewrite && (
                <div className="mt-2">
                  <SectionLabel text={STRINGS.common.nextTimeTry} />
                  <SuggestedRewrite text={pattern.suggested_rewrite} />
                </div>
              )}
              {quotes.length > 1 && (
                <div className="mt-2">
                  <SectionLabel text={STRINGS.common.otherMoments} />
                  {quotes.slice(1).map((q, i) => <EvidenceQuote key={i} quote={q} />)}
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
}

export function PatternSnapshot({ patterns }: PatternSnapshotProps) {
  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
      {patterns.map((p) => (
        <PatternCard key={p.pattern_id} pattern={p} />
      ))}
    </div>
  );
}

'use client';

import { useState } from 'react';
import type { PatternSnapshotItem } from '@/lib/types';
import { EvidenceQuote } from './EvidenceQuote';
import { STRINGS } from '@/config/strings';

interface PatternSnapshotProps {
  patterns: PatternSnapshotItem[];
}

const BALANCE_COLORS: Record<string, { bg: string; dot: string }> = {
  balanced: { bg: 'bg-emerald-50', dot: 'bg-emerald-500' },
  over_indexed: { bg: 'bg-rose-50', dot: 'bg-rose-400' },
  under_indexed: { bg: 'bg-amber-50', dot: 'bg-amber-400' },
  unclear: { bg: 'bg-gray-50', dot: 'bg-gray-400' },
};

function BalanceBadge({ assessment }: { assessment: string }) {
  const colors = BALANCE_COLORS[assessment] ?? BALANCE_COLORS.unclear;
  const label = STRINGS.balanceLabels[assessment] ?? assessment;
  return (
    <span className={`inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full text-xs font-medium text-gray-700 ${colors.bg}`}>
      <span className={`w-1.5 h-1.5 rounded-full ${colors.dot}`} />
      {label}
    </span>
  );
}

function RatioBar({ ratio }: { ratio: number }) {
  const pct = Math.round(ratio * 100);
  const color =
    pct >= 75 ? 'bg-emerald-500' : pct >= 50 ? 'bg-amber-400' : 'bg-rose-400';
  return (
    <div className="flex items-center gap-2">
      <div className="flex-1 bg-gray-200 rounded-full h-2">
        <div
          className={`h-2 rounded-full ${color}`}
          style={{ width: `${pct}%` }}
        />
      </div>
      <span className="text-xs text-gray-600 w-10 text-right">{pct}%</span>
    </div>
  );
}

function PatternCard({ pattern }: { pattern: PatternSnapshotItem }) {
  const [expanded, setExpanded] = useState(false);

  const quotes = pattern.quotes ?? [];
  const isConversationalBalance = pattern.pattern_id === 'conversational_balance';
  const hasQuotes = quotes.length > 0;
  const hasCoaching = !!pattern.coaching_note;
  const hasNotes = !!pattern.notes;
  const isBalanced = pattern.balance_assessment === 'balanced';
  const isExpandable = isConversationalBalance
    ? (isBalanced ? hasNotes : hasCoaching)
    : (hasQuotes || hasCoaching || hasNotes);

  // Determine if this pattern has missed opportunities
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

  const isMixedScore =
    hasMissedOpportunities &&
    pattern.numerator != null &&
    pattern.numerator > 0;

  // Split quotes into success vs needs-improvement using rewrite_for_span_id.
  // Only split when we have a rewrite target to distinguish them.
  const rewriteSpanId = pattern.rewrite_for_span_id;
  const canSplitQuotes = isMixedScore && !!rewriteSpanId;
  const successQuotes = canSplitQuotes
    ? quotes.filter((q) => q.span_id !== rewriteSpanId)
    : (isPerfectScore ? quotes : []);
  const improvementQuotes = canSplitQuotes
    ? quotes.filter((q) => q.span_id === rewriteSpanId)
    : (isPerfectScore ? [] : quotes);

  return (
    <div className="bg-white border border-gray-200 rounded-lg overflow-hidden">
      <button
        type="button"
        onClick={() => isExpandable && setExpanded(!expanded)}
        className={`w-full p-3 text-left ${isExpandable ? 'cursor-pointer hover:bg-stone-50 transition-colors' : 'cursor-default'}`}
      >
        <div className="flex items-center justify-between mb-1">
          <span className="text-xs font-medium text-gray-700">
            {STRINGS.patternIcons[pattern.pattern_id] && (
              <span className="mr-1">{STRINGS.patternIcons[pattern.pattern_id]}</span>
            )}
            {STRINGS.patternLabels[pattern.pattern_id] ?? pattern.pattern_id}
          </span>
          <div className="flex items-center gap-1.5">
            {pattern.tier && (
              <span className="text-xs text-gray-400">T{pattern.tier}</span>
            )}
            {isExpandable && (
              <span className={`text-xs text-gray-400 transition-transform ${expanded ? 'rotate-180' : ''}`}>
                ▾
              </span>
            )}
          </div>
        </div>
        {pattern.evaluable_status === 'evaluable' && pattern.ratio != null ? (
          <RatioBar ratio={pattern.ratio} />
        ) : pattern.evaluable_status === 'evaluable' && pattern.balance_assessment ? (
          <BalanceBadge assessment={pattern.balance_assessment} />
        ) : (
          <span className="text-xs text-gray-400 capitalize">
            {pattern.evaluable_status === 'insufficient_signal'
              ? STRINGS.evaluableStatus.insufficient_signal
              : STRINGS.evaluableStatus.not_evaluable}
          </span>
        )}
      </button>

      {expanded && (
        <div className="border-t border-gray-100 px-3 pb-3 pt-2 space-y-3">

          {/* ── Perfect score: positive explainer + all quotes ── */}
          {isPerfectScore && (hasQuotes || hasNotes) && (
            <div>
              <p className="text-xs font-semibold text-stone-400 uppercase tracking-widest mb-1.5">
                {STRINGS.common.whatYouDidWell}
              </p>
              {hasNotes && (
                <p className="text-sm text-stone-700 leading-relaxed mb-2">
                  {pattern.notes}
                </p>
              )}
              {quotes.map((q, i) => (
                <EvidenceQuote key={i} quote={q} />
              ))}
            </div>
          )}

          {/* ── Mixed score with splittable quotes ── */}
          {isMixedScore && canSplitQuotes && (
            <>
              {(successQuotes.length > 0 || hasNotes) && (
                <div>
                  <p className="text-xs font-semibold text-stone-400 uppercase tracking-widest mb-1.5">
                    {STRINGS.common.whatYouDidWell}
                  </p>
                  {hasNotes && (
                    <p className="text-sm text-stone-700 leading-relaxed mb-2">
                      {pattern.notes}
                    </p>
                  )}
                  {successQuotes.map((q, i) => (
                    <EvidenceQuote key={i} quote={q} />
                  ))}
                </div>
              )}

              <div>
                <p className="text-xs font-semibold text-stone-400 uppercase tracking-widest mb-1.5">
                  {STRINGS.common.whereYouCanImprove}
                </p>
                {hasCoaching && (
                  <p className="text-sm text-stone-700 leading-relaxed mb-2">
                    {pattern.coaching_note}
                  </p>
                )}
                {improvementQuotes.length > 0 && (
                  <div>
                    <p className="text-xs font-semibold text-stone-400 uppercase tracking-widest mb-1.5">
                      {STRINGS.common.forExampleYouSaid}
                    </p>
                    <EvidenceQuote quote={improvementQuotes[0]} />
                  </div>
                )}
                {pattern.suggested_rewrite && (
                  <div className="mt-2">
                    <p className="text-xs font-semibold text-stone-400 uppercase tracking-widest mb-1.5">
                      {STRINGS.common.nextTimeTry}
                    </p>
                    <blockquote className="border-l-4 border-emerald-300 pl-4 py-1 my-2 bg-emerald-50 rounded-r-md">
                      <p className="text-sm text-stone-700 italic">
                        &ldquo;{pattern.suggested_rewrite}&rdquo;
                      </p>
                    </blockquote>
                  </div>
                )}
                {improvementQuotes.length > 1 && (
                  <div className="mt-2">
                    <p className="text-xs font-semibold text-stone-400 uppercase tracking-widest mb-1.5">
                      {STRINGS.common.otherMoments}
                    </p>
                    {improvementQuotes.slice(1).map((q, i) => (
                      <EvidenceQuote key={i} quote={q} />
                    ))}
                  </div>
                )}
              </div>
            </>
          )}

          {/* ── Mixed score without rewrite target (can't split) ── */}
          {isMixedScore && !canSplitQuotes && (
            <>
              {hasNotes && (
                <div>
                  <p className="text-xs font-semibold text-stone-400 uppercase tracking-widest mb-1.5">
                    {STRINGS.common.whatYouDidWell}
                  </p>
                  <p className="text-sm text-stone-700 leading-relaxed">
                    {pattern.notes}
                  </p>
                </div>
              )}

              <div>
                <p className="text-xs font-semibold text-stone-400 uppercase tracking-widest mb-1.5">
                  {STRINGS.common.whereYouCanImprove}
                </p>
                {hasCoaching && (
                  <p className="text-sm text-stone-700 leading-relaxed mb-2">
                    {pattern.coaching_note}
                  </p>
                )}
                {hasQuotes && (
                  <div>
                    <p className="text-xs font-semibold text-stone-400 uppercase tracking-widest mb-1.5">
                      {STRINGS.common.forExampleYouSaid}
                    </p>
                    <EvidenceQuote quote={quotes[0]} />
                  </div>
                )}
                {pattern.suggested_rewrite && (
                  <div className="mt-2">
                    <p className="text-xs font-semibold text-stone-400 uppercase tracking-widest mb-1.5">
                      {STRINGS.common.nextTimeTry}
                    </p>
                    <blockquote className="border-l-4 border-emerald-300 pl-4 py-1 my-2 bg-emerald-50 rounded-r-md">
                      <p className="text-sm text-stone-700 italic">
                        &ldquo;{pattern.suggested_rewrite}&rdquo;
                      </p>
                    </blockquote>
                  </div>
                )}
                {quotes.length > 1 && (
                  <div className="mt-2">
                    <p className="text-xs font-semibold text-stone-400 uppercase tracking-widest mb-1.5">
                      {STRINGS.common.otherMoments}
                    </p>
                    {quotes.slice(1).map((q, i) => (
                      <EvidenceQuote key={i} quote={q} />
                    ))}
                  </div>
                )}
              </div>
            </>
          )}

          {/* ── Conversational balance: summary blurb, no individual quotes ── */}
          {isConversationalBalance && isBalanced && hasNotes && (
            <div>
              <p className="text-xs font-semibold text-stone-400 uppercase tracking-widest mb-1.5">
                {STRINGS.common.whatYouDidWell}
              </p>
              <p className="text-sm text-stone-700 leading-relaxed">
                {pattern.notes}
              </p>
            </div>
          )}

          {isConversationalBalance && !isBalanced && hasCoaching && (
            <div>
              <p className="text-xs font-semibold text-stone-400 uppercase tracking-widest mb-1.5">
                {STRINGS.common.observation}
              </p>
              <p className="text-sm text-stone-700 leading-relaxed">
                {pattern.coaching_note}
              </p>
            </div>
          )}

          {/* ── Zero score or non-numeric (excluding conversational balance) ── */}
          {!isConversationalBalance && !isPerfectScore && !isMixedScore && (
            <>
              <div>
                <p className="text-xs font-semibold text-stone-400 uppercase tracking-widest mb-1.5">
                  {STRINGS.common.whereYouCanImprove}
                </p>
                {hasCoaching && (
                  <p className="text-sm text-stone-700 leading-relaxed mb-2">
                    {pattern.coaching_note}
                  </p>
                )}
                {hasQuotes && (
                  <div>
                    <p className="text-xs font-semibold text-stone-400 uppercase tracking-widest mb-1.5">
                      {STRINGS.common.forExampleYouSaid}
                    </p>
                    <EvidenceQuote quote={quotes[0]} />
                  </div>
                )}
                {pattern.suggested_rewrite && (
                  <div className="mt-2">
                    <p className="text-xs font-semibold text-stone-400 uppercase tracking-widest mb-1.5">
                      {STRINGS.common.nextTimeTry}
                    </p>
                    <blockquote className="border-l-4 border-emerald-300 pl-4 py-1 my-2 bg-emerald-50 rounded-r-md">
                      <p className="text-sm text-stone-700 italic">
                        &ldquo;{pattern.suggested_rewrite}&rdquo;
                      </p>
                    </blockquote>
                  </div>
                )}
                {quotes.length > 1 && (
                  <div className="mt-2">
                    <p className="text-xs font-semibold text-stone-400 uppercase tracking-widest mb-1.5">
                      {STRINGS.common.otherMoments}
                    </p>
                    {quotes.slice(1).map((q, i) => (
                      <EvidenceQuote key={i} quote={q} />
                    ))}
                  </div>
                )}
              </div>
            </>
          )}

        </div>
      )}
    </div>
  );
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

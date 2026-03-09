'use client';

import { useState } from 'react';
import type { PatternSnapshotItem } from '@/lib/types';
import { EvidenceQuote } from './EvidenceQuote';

interface PatternSnapshotProps {
  patterns: PatternSnapshotItem[];
}

const PATTERN_LABELS: Record<string, string> = {
  agenda_clarity: 'Agenda Clarity',
  objective_signaling: 'Objective Signaling',
  turn_allocation: 'Turn Allocation',
  facilitative_inclusion: 'Facilitative Inclusion',
  decision_closure: 'Decision Closure',
  owner_timeframe_specification: 'Owner & Timeframe',
  summary_checkback: 'Summary & Check-back',
  question_quality: 'Question Quality',
  listener_response_quality: 'Listener Response',
  conversational_balance: 'Conversational Balance',
};

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

  const hasQuotes = pattern.quotes.length > 0;
  const hasCoaching = !!pattern.coaching_note;
  const isExpandable = hasQuotes || hasCoaching;

  // Determine if this pattern has missed opportunities
  const hasMissedOpportunities =
    pattern.evaluable_status === 'evaluable' &&
    pattern.numerator != null &&
    pattern.denominator != null &&
    pattern.numerator < pattern.denominator;

  const isImbalanced =
    pattern.evaluable_status === 'evaluable' &&
    pattern.balance_assessment &&
    pattern.balance_assessment !== 'balanced';

  return (
    <div className="bg-white border border-gray-200 rounded-lg overflow-hidden">
      <button
        type="button"
        onClick={() => isExpandable && setExpanded(!expanded)}
        className={`w-full p-3 text-left ${isExpandable ? 'cursor-pointer hover:bg-stone-50 transition-colors' : 'cursor-default'}`}
      >
        <div className="flex items-center justify-between mb-1">
          <span className="text-xs font-medium text-gray-700">
            {PATTERN_LABELS[pattern.pattern_id] ?? pattern.pattern_id}
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
          <span className="text-xs text-gray-600 capitalize">
            {pattern.balance_assessment.replace('_', ' ')}
          </span>
        ) : (
          <span className="text-xs text-gray-400 capitalize">
            {pattern.evaluable_status === 'insufficient_signal'
              ? 'Insufficient signal'
              : 'Not evaluable'}
          </span>
        )}
      </button>

      {expanded && (
        <div className="border-t border-gray-100 px-3 pb-3 pt-2 space-y-3">
          {/* Evidence quotes */}
          {hasQuotes && (
            <div>
              <p className="text-xs font-semibold text-stone-400 uppercase tracking-widest mb-1.5">
                {hasMissedOpportunities || isImbalanced ? 'Evidence from this meeting' : 'What you did well'}
              </p>
              {pattern.quotes.map((q, i) => (
                <EvidenceQuote key={i} quote={q} />
              ))}
            </div>
          )}

          {/* Coaching note */}
          {hasCoaching && (
            <div>
              <p className="text-xs font-semibold text-stone-400 uppercase tracking-widest mb-1.5">
                Coaching note
              </p>
              <p className="text-sm text-stone-700 leading-relaxed">
                {pattern.coaching_note}
              </p>
            </div>
          )}

          {/* Suggested rewrite */}
          {pattern.suggested_rewrite && (
            <div>
              <p className="text-xs font-semibold text-stone-400 uppercase tracking-widest mb-1.5">
                Next time, try something like
              </p>
              <blockquote className="border-l-4 border-emerald-300 pl-4 py-1 my-2 bg-emerald-50 rounded-r-md">
                <p className="text-sm text-stone-700 italic">
                  &ldquo;{pattern.suggested_rewrite}&rdquo;
                </p>
              </blockquote>
            </div>
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

import type { QuoteObject } from '@/lib/types';

interface EvidenceQuoteProps {
  quote: QuoteObject;
}

/**
 * EvidenceQuote — renders a single piece of transcript evidence.
 *
 * Design:
 *   - Soft blue-50 background with a 3px solid blue-500 left bar
 *   - Attribution (speaker + timestamp) in stone-400, tabular numerals
 *   - Quote text in DM Sans (sans-serif), regular weight, stone-700
 *     — no italic/bold: improves legibility for long excerpts
 */
export function EvidenceQuote({ quote }: EvidenceQuoteProps) {
  let attribution: string | null = null;
  if (quote.speaker_label && quote.start_timestamp) {
    attribution = `${quote.speaker_label} · ${quote.start_timestamp}`;
  } else if (quote.speaker_label) {
    attribution = quote.speaker_label;
  } else if (quote.start_timestamp) {
    attribution = quote.start_timestamp;
  }

  return (
    <blockquote className="border-l-[3px] border-blue-500 pl-4 pr-3 py-2.5 my-2 bg-blue-50 rounded-r-lg">
      {/* Meeting label — amber small-caps */}
      {quote.meeting_label && (
        <p className="text-2xs font-semibold uppercase tracking-[0.14em] text-cv-amber-600 mb-1">
          {quote.meeting_label}
        </p>
      )}

      {/* Attribution */}
      {attribution && (
        <p className="text-2xs text-cv-stone-400 font-medium mb-1 tabular-nums">
          {attribution}
        </p>
      )}

      {/* Quote text — italic for quoted speech */}
      <p className="text-sm text-cv-stone-700 leading-relaxed italic">
        &ldquo;{quote.quote_text}&rdquo;
      </p>
    </blockquote>
  );
}

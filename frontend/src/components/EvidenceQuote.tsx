import type { QuoteObject } from '@/lib/types';

interface EvidenceQuoteProps {
  quote: QuoteObject;
}

/**
 * EvidenceQuote — renders a single piece of transcript evidence.
 *
 * Design:
 *   - Warm parchment background (cv-warm-50) with a 3px solid teal-600 left bar
 *   - Meeting label in small-tracked-caps amber
 *   - Attribution (speaker + timestamp) in stone-400, monospaced weight
 *   - Quote text in DM Serif Display italic, stone-700
 */
export function EvidenceQuote({ quote }: EvidenceQuoteProps) {
  // Build attribution: "Speaker (ts):" / "(ts):" / "Speaker:" / null
  let attribution: string | null = null;
  if (quote.speaker_label && quote.start_timestamp) {
    attribution = `${quote.speaker_label} · ${quote.start_timestamp}`;
  } else if (quote.speaker_label) {
    attribution = quote.speaker_label;
  } else if (quote.start_timestamp) {
    attribution = quote.start_timestamp;
  }

  return (
    <blockquote className="border-l-[3px] border-cv-teal-600 pl-4 pr-3 py-2.5 my-2 bg-cv-warm-50 rounded-r-lg">
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

      {/* Quote text — serif italic */}
      <p className="text-sm text-cv-stone-700 font-serif italic leading-relaxed">
        &ldquo;{quote.quote_text}&rdquo;
      </p>
    </blockquote>
  );
}

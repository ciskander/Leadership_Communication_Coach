import type { QuoteObject } from '@/lib/types';

interface EvidenceQuoteProps {
  quote: QuoteObject;
  /** When provided, quotes from non-target speakers use neutral styling. */
  targetSpeaker?: string | null;
}

/**
 * EvidenceQuote — renders a single piece of transcript evidence.
 *
 * Design:
 *   - Target speaker: blue-50 background with a 3px solid #1E3A5F left bar
 *   - Other speakers: warm-100 background with a 3px solid stone-300 left bar
 *   - Attribution (speaker + timestamp) in stone-400, tabular numerals
 *   - Quote text in sans-serif, regular weight, stone-700
 */
export function EvidenceQuote({ quote, targetSpeaker }: EvidenceQuoteProps) {
  let attribution: string | null = null;
  if (quote.speaker_label && quote.start_timestamp) {
    attribution = `${quote.speaker_label} · ${quote.start_timestamp}`;
  } else if (quote.speaker_label) {
    attribution = quote.speaker_label;
  } else if (quote.start_timestamp) {
    attribution = quote.start_timestamp;
  }

  const isOtherSpeaker =
    targetSpeaker != null &&
    quote.speaker_label != null &&
    quote.speaker_label !== targetSpeaker;

  const blockStyles = isOtherSpeaker
    ? 'border-l-[3px] border-cv-stone-300 pl-4 pr-3 py-2.5 my-2 bg-cv-warm-100 rounded-r'
    : 'border-l-[3px] border-[#1E3A5F] pl-4 pr-3 py-2.5 my-2 bg-blue-50 rounded-r';

  return (
    <blockquote className={blockStyles}>
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
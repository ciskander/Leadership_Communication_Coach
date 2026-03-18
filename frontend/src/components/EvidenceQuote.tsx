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
 *   - Target speaker: cv-blue-50 background with a 3px solid cv-navy-600 left bar
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

  // Prefer the backend-computed is_target_speaker flag (set during quote
  // resolution where the transcript turn map is available).  Fall back to
  // a client-side label comparison for backwards compatibility.
  let isOtherSpeaker = false;
  if (quote.is_target_speaker != null) {
    isOtherSpeaker = !quote.is_target_speaker;
  } else {
    const normTarget = targetSpeaker?.trim().toLowerCase() || null;
    const normLabel  = quote.speaker_label?.trim().toLowerCase() || null;
    isOtherSpeaker =
      normTarget != null &&
      normLabel != null &&
      normLabel !== normTarget;
  }

  const blockStyles = isOtherSpeaker
    ? 'border-l-[2px] border-cv-stone-300 pl-4 pr-3 py-2.5 my-2 bg-cv-warm-100 rounded-r'
    : 'border-l-[2px] border-cv-navy-600 pl-4 pr-3 py-2.5 my-2 bg-cv-blue-50 rounded-r';

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

// ─── List with span-group separators ─────────────────────────────────────────

interface EvidenceQuoteListProps {
  quotes: QuoteObject[];
  targetSpeaker?: string | null;
}

/**
 * EvidenceQuoteList — renders a list of quotes, grouped by span_id.
 * A thin horizontal separator is placed between different evidence-span groups.
 * Quotes within the same span (multi-speaker turns) are NOT separated.
 */
export function EvidenceQuoteList({ quotes, targetSpeaker }: EvidenceQuoteListProps) {
  if (quotes.length === 0) return null;

  // Group consecutive quotes by span_id, preserving order.
  const groups: QuoteObject[][] = [];
  let currentSpanId: string | null | undefined;
  for (const q of quotes) {
    if (groups.length === 0 || q.span_id !== currentSpanId) {
      groups.push([q]);
      currentSpanId = q.span_id;
    } else {
      groups[groups.length - 1].push(q);
    }
  }

  return (
    <>
      {groups.map((group, gi) => (
        <div key={gi}>
          {gi > 0 && (
            <hr className="border-t border-cv-warm-300 my-3" />
          )}
          {group.map((q, qi) => (
            <EvidenceQuote key={qi} quote={q} targetSpeaker={targetSpeaker} />
          ))}
        </div>
      ))}
    </>
  );
}
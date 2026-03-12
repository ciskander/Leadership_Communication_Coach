import type { QuoteObject } from '@/lib/types';

interface EvidenceQuoteProps {
  quote: QuoteObject;
}

export function EvidenceQuote({ quote }: EvidenceQuoteProps) {
  // Build pre-quote attribution: "Speaker (ts):" or "(ts):" or "Speaker:" or nothing
  let attribution: string | null = null;
  if (quote.speaker_label && quote.start_timestamp) {
    attribution = `${quote.speaker_label} (${quote.start_timestamp}):`;
  } else if (quote.speaker_label) {
    attribution = `${quote.speaker_label}:`;
  } else if (quote.start_timestamp) {
    attribution = `(${quote.start_timestamp}):`;
  }

  return (
    <blockquote className="border-l-4 border-indigo-300 pl-4 py-1 my-2 bg-indigo-50 rounded-r-md">
      {quote.meeting_label && (
        <p className="text-xs text-indigo-400 font-medium mb-0.5">{quote.meeting_label}</p>
      )}
      <p className="text-sm text-gray-700">
        {attribution && (
          <><span className="text-gray-500">{attribution}</span>{' '}</>
        )}
        <span className="italic">&ldquo;{quote.quote_text}&rdquo;</span>
      </p>
    </blockquote>
  );
}

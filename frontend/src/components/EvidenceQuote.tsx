import type { QuoteObject } from '@/lib/types';

interface EvidenceQuoteProps {
  quote: QuoteObject;
}

export function EvidenceQuote({ quote }: EvidenceQuoteProps) {
  // Multi-speaker spans have speaker_label set — show "Name (ts):" prefix
  if (quote.speaker_label) {
    const prefix = quote.start_timestamp
      ? `${quote.speaker_label} (${quote.start_timestamp})`
      : quote.speaker_label;
    return (
      <blockquote className="border-l-4 border-indigo-300 pl-4 py-1 my-2 bg-indigo-50 rounded-r-md">
        <p className="text-sm text-gray-700">
          <span className="font-medium text-gray-900">{prefix}:</span>{' '}
          <span className="italic">"{quote.quote_text}"</span>
        </p>
      </blockquote>
    );
  }

  // Single-speaker — just the quote, with optional timestamp underneath
  return (
    <blockquote className="border-l-4 border-indigo-300 pl-4 py-1 my-2 bg-indigo-50 rounded-r-md">
      <p className="text-sm text-gray-700 italic">"{quote.quote_text}"</p>
      {quote.start_timestamp && (
        <p className="text-xs text-gray-500 mt-1">— {quote.start_timestamp}</p>
      )}
    </blockquote>
  );
}

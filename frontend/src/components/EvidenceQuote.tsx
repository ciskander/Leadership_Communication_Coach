import type { QuoteObject } from '@/lib/types';

interface EvidenceQuoteProps {
  quote: QuoteObject;
}

export function EvidenceQuote({ quote }: EvidenceQuoteProps) {
  return (
    <blockquote className="border-l-4 border-indigo-300 pl-4 py-1 my-2 bg-indigo-50 rounded-r-md">
      <p className="text-sm text-gray-700 italic">"{quote.quote_text}"</p>
      {quote.speaker_label && (
        <p className="text-xs text-gray-500 mt-1">— {quote.speaker_label}</p>
      )}
    </blockquote>
  );
}

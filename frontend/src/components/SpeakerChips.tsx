'use client';

interface SpeakerChipsProps {
  speakers: string[];
  selected: string | null;
  onSelect: (speaker: string) => void;
}

export function SpeakerChips({ speakers, selected, onSelect }: SpeakerChipsProps) {
  return (
    <div className="flex flex-wrap gap-2">
      {speakers.map((s) => (
        <button
          key={s}
          type="button"
          onClick={() => onSelect(s)}
          className={`px-3 py-1 rounded-full text-sm border transition-colors ${
            selected === s
              ? 'bg-indigo-600 text-white border-indigo-600'
              : 'bg-white text-gray-700 border-gray-300 hover:border-indigo-400'
          }`}
        >
          {s}
        </button>
      ))}
    </div>
  );
}

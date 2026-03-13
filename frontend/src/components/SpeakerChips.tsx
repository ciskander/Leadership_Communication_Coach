'use client';

interface SpeakerChipsProps {
  speakers: string[];
  selected: string | null;
  onSelect: (speaker: string) => void;
}

export function SpeakerChips({ speakers, selected, onSelect }: SpeakerChipsProps) {
  return (
    <div className="flex flex-wrap gap-1.5">
      {speakers.map((s) => (
        <button
          key={s}
          type="button"
          onClick={() => onSelect(s)}
          className={[
            'px-3 py-1 rounded-full text-xs font-medium border transition-all duration-150',
            selected === s
              ? 'bg-cv-teal-600 text-white border-cv-teal-600 shadow-sm'
              : 'bg-white text-cv-stone-600 border-cv-warm-300 hover:border-cv-teal-400 hover:text-cv-teal-700',
          ].join(' ')}
        >
          {s}
        </button>
      ))}
    </div>
  );
}

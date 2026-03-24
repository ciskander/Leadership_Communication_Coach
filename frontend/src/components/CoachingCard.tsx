import type { CoachingItem, MicroExperiment, PatternSnapshotItem, PatternCoachingItem } from '@/lib/types';
import { EvidenceQuoteList } from './EvidenceQuote';
import { PatternCard } from './PatternSnapshot';
import type { PatternTrendData } from './PatternSnapshot';
import { STRINGS } from '@/config/strings';

// ─── Shared sub-components ───────────────────────────────────────────────────

/** Small-caps section label used before evidence blocks */
function SectionLabel({ text }: { text: string }) {
  return (
    <p className="text-2xs font-semibold uppercase tracking-[0.14em] text-cv-stone-400 mb-1.5">
      {text}
    </p>
  );
}

/** Pattern taxonomy ID rendered as readable small-caps label */
function PatternLabel({ id, className = 'text-cv-teal-600' }: { id: string; className?: string }) {
  return (
    <span className={`text-2xs font-semibold uppercase tracking-[0.14em] ${className}`}>
      {id.replace(/_/g, ' ')}
    </span>
  );
}

/** Inset box used in the micro-experiment body */
function InsetBox({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="bg-cv-warm-50 border border-cv-warm-300 rounded p-3.5">
      <SectionLabel text={label} />
      {children}
    </div>
  );
}

// ─── Main component ───────────────────────────────────────────────────────────

interface CoachingCardProps {
  strengths: CoachingItem[];
  focus: CoachingItem | null;
  microExperiment: MicroExperiment | null;
  targetSpeaker?: string | null;
  patternSnapshot?: PatternSnapshotItem[] | null;
  patternCoaching?: PatternCoachingItem[];
  trendData?: Record<string, PatternTrendData>;
}

export function CoachingCard({
  strengths,
  focus,
  microExperiment,
  targetSpeaker,
  patternSnapshot,
  patternCoaching,
  trendData,
}: CoachingCardProps) {
  /** Look up the PatternSnapshotItem for a given pattern_id. */
  function findPatternCard(patternId: string): PatternSnapshotItem | undefined {
    return patternSnapshot?.find((p) => p.pattern_id === patternId);
  }

  /** Look up the PatternCoachingItem for a given pattern_id. */
  function findPatternCoaching(patternId: string): PatternCoachingItem | undefined {
    return patternCoaching?.find((pc) => pc.pattern_id === patternId);
  }

  return (
    <div className="space-y-4">

      {/* ── Strengths ────────────────────────────────────────────────────── */}
      {strengths.length > 0 && (
        <section className="bg-white rounded border border-cv-teal-700 overflow-hidden">
          {/* Header */}
          <div className="flex items-center gap-2.5 px-5 py-3.5 border-b border-cv-warm-300 bg-cv-teal-700">
            <svg viewBox="0 0 20 20" fill="currentColor" className="w-4 h-4 text-cv-teal-50 shrink-0" aria-hidden="true">
              <path fillRule="evenodd" d="M10.868 2.884c-.321-.772-1.415-.772-1.736 0l-1.83 4.401-4.753.381c-.833.067-1.171 1.107-.536 1.651l3.62 3.102-1.106 4.637c-.194.813.691 1.456 1.405 1.02L10 15.591l4.069 2.485c.713.436 1.598-.207 1.404-1.02l-1.106-4.637 3.62-3.102c.635-.544.297-1.584-.536-1.65l-4.752-.382-1.831-4.401z" clipRule="evenodd" />
            </svg>
            <h3 className="text-sm font-semibold text-cv-teal-50">{STRINGS.coachingCard.strengthsHeading}</h3>
          </div>

          {/* Body */}
          <div className="divide-y divide-cv-warm-300">
            {strengths.map((s) => {
              const card = findPatternCard(s.pattern_id);
              const coaching = findPatternCoaching(s.pattern_id);
              return (
                <div key={s.pattern_id} className="px-5 py-4">
                  <div className={card ? 'grid grid-cols-1 lg:grid-cols-2 gap-4 items-start' : ''}>
                    <div className="space-y-2">
                      <PatternLabel id={s.pattern_id} />
                      <p className="text-sm text-cv-stone-700 leading-relaxed">{s.message}</p>
                    </div>
                    {card && (
                      <PatternCard
                        pattern={card}
                        coaching={coaching}
                        targetSpeaker={targetSpeaker ?? null}
                        trend={trendData?.[s.pattern_id]}
                      />
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        </section>
      )}

      {/* ── Focus ────────────────────────────────────────────────────────── */}
      {focus && (
        <section className="bg-white rounded border border-cv-rose-700 overflow-hidden">
          {/* Header */}
          <div className="flex items-center gap-2.5 px-5 py-3.5 border-b border-cv-warm-300 bg-cv-rose-700">
            <svg viewBox="0 0 20 20" fill="currentColor" className="w-4 h-4 text-cv-rose-50 shrink-0" aria-hidden="true">
              <path d="M10 12.5a2.5 2.5 0 100-5 2.5 2.5 0 000 5z" />
              <path fillRule="evenodd" d="M.664 10.59a1.651 1.651 0 010-1.186A10.004 10.004 0 0110 3c4.257 0 7.893 2.66 9.336 6.41.147.381.146.804 0 1.186A10.004 10.004 0 0110 17c-4.257 0-7.893-2.66-9.336-6.41zM14 10a4 4 0 11-8 0 4 4 0 018 0z" clipRule="evenodd" />
            </svg>
            <h3 className="text-sm font-semibold text-cv-rose-50">{STRINGS.coachingCard.focusHeading}</h3>
          </div>

          {/* Body */}
          <div className="px-5 py-4">
            {(() => {
              const card = findPatternCard(focus.pattern_id);
              const focusCoaching = findPatternCoaching(focus.pattern_id);
              return (
                <div className={card ? 'grid grid-cols-1 lg:grid-cols-2 gap-4 items-start' : ''}>
                  <div className="space-y-2">
                    <PatternLabel id={focus.pattern_id} className="text-cv-rose-700" />
                    <p className="text-sm text-cv-stone-700 leading-relaxed">{focus.message}</p>
                  </div>
                  {card && (
                    <PatternCard
                      pattern={card}
                      coaching={focusCoaching}
                      targetSpeaker={targetSpeaker ?? null}
                      trend={trendData?.[focus.pattern_id]}
                    />
                  )}
                </div>
              );
            })()}
          </div>
        </section>
      )}

      {/* ── Micro-experiment ─────────────────────────────────────────────── */}
      {microExperiment && (
        <section className="bg-white rounded border border-cv-warm-300 overflow-hidden">
          {/* Header */}
          <div className="flex items-center gap-2.5 px-5 py-3.5 border-b border-cv-warm-300 bg-cv-warm-100">
            <svg viewBox="0 0 20 20" fill="currentColor" className="w-4 h-4 text-cv-stone-500 shrink-0" aria-hidden="true">
              <path fillRule="evenodd" d="M8.5 3.528v4.644c0 .479-.239.927-.644 1.190L6.24 10.484A3.501 3.501 0 008 17h4a3.5 3.5 0 001.76-6.516l-1.616-1.122A1.419 1.419 0 0111.5 8.172V3.528a16.989 16.989 0 00-3 0zM7 2.80A18.45 18.45 0 0110 2.5c1.048 0 2.062.095 3 .275v5.397a2.919 2.919 0 01-1.322 2.445L10.062 11.7a2 2 0 101.876 0L10.322 10.617A2.919 2.919 0 019 8.172V2.775A18.45 18.45 0 007 2.8z" clipRule="evenodd" />
            </svg>
            <h3 className="text-sm font-semibold text-cv-stone-700">{STRINGS.coachingCard.experimentHeading}</h3>
          </div>

          {/* Body */}
          <div className="px-5 py-4 space-y-4">
            {/* Title + ID */}
            <div>
              <p className="text-base font-semibold text-cv-stone-900 leading-snug font-serif">
                {microExperiment.title}
              </p>
              <p className="text-2xs text-cv-stone-400 mt-0.5 tabular-nums">
                {microExperiment.experiment_id}
              </p>
            </div>

            {/* Instruction + Success marker */}
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              <InsetBox label={STRINGS.common.whatToDo}>
                <p className="text-sm text-cv-stone-700 leading-relaxed">
                  {microExperiment.instruction}
                </p>
              </InsetBox>
              <InsetBox label={STRINGS.common.howYoullKnowItWorked}>
                <p className="text-sm text-cv-stone-700 leading-relaxed">
                  {microExperiment.success_marker}
                </p>
              </InsetBox>
            </div>

            {/* Evidence quotes */}
            <EvidenceQuoteList quotes={microExperiment.quotes ?? []} targetSpeaker={targetSpeaker} />
          </div>
        </section>
      )}
    </div>
  );
}

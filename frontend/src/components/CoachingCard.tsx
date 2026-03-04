import type { CoachingItem, MicroExperiment } from '@/lib/types';
import { EvidenceQuote } from './EvidenceQuote';

interface CoachingCardProps {
  strengths: CoachingItem[];
  focus: CoachingItem | null;
  microExperiment: MicroExperiment | null;
}

function PatternLabel({ id }: { id: string }) {
  return (
    <span className="text-xs font-semibold text-stone-400 uppercase tracking-widest">
      {id.replace(/_/g, ' ')}
    </span>
  );
}

export function CoachingCard({ strengths, focus, microExperiment }: CoachingCardProps) {
  return (
    <div className="space-y-5">
      {/* Strengths */}
      {strengths.length > 0 && (
        <section className="bg-white rounded-2xl border border-stone-200 overflow-hidden">
          <div className="flex items-center gap-2.5 px-5 py-3.5 border-b border-stone-100 bg-emerald-50">
            <span className="text-base">✦</span>
            <h3 className="text-sm font-semibold text-emerald-800">What you do well</h3>
          </div>
          <div className="divide-y divide-stone-100">
            {strengths.map((s) => (
              <div key={s.pattern_id} className="px-5 py-4 space-y-2">
                <PatternLabel id={s.pattern_id} />
                <p className="text-sm text-stone-700 leading-relaxed">{s.message}</p>
                {(s.quotes ?? []).map((q, i) => (
                  <EvidenceQuote key={i} quote={q} />
                ))}
              </div>
            ))}
          </div>
        </section>
      )}

      {/* Focus */}
      {focus && (
        <section className="bg-white rounded-2xl border border-stone-200 overflow-hidden">
          <div className="flex items-center gap-2.5 px-5 py-3.5 border-b border-stone-100 bg-amber-50">
            <span className="text-base">◎</span>
            <h3 className="text-sm font-semibold text-amber-800">Area to focus on</h3>
          </div>
          <div className="px-5 py-4 space-y-2">
            <PatternLabel id={focus.pattern_id} />
            <p className="text-sm text-stone-700 leading-relaxed">{focus.message}</p>
            {(focus.quotes ?? []).map((q, i) => (
              <EvidenceQuote key={i} quote={q} />
            ))}
          </div>
        </section>
      )}

      {/* Micro-experiment */}
      {microExperiment && (
        <section className="bg-white rounded-2xl border border-stone-200 overflow-hidden">
          <div className="flex items-center gap-2.5 px-5 py-3.5 border-b border-stone-100 bg-violet-50">
            <span className="text-base">◈</span>
            <h3 className="text-sm font-semibold text-violet-800">Your experiment</h3>
          </div>
          <div className="px-5 py-4 space-y-4">
            <div>
              <p className="text-base font-semibold text-stone-900 leading-snug">
                {microExperiment.title}
              </p>
              <p className="text-xs text-stone-400 mt-0.5">{microExperiment.experiment_id}</p>
            </div>
            <div className="space-y-3">
              <div className="bg-stone-50 rounded-xl p-3.5">
                <p className="text-xs font-semibold text-stone-400 uppercase tracking-widest mb-1.5">
                  What to do
                </p>
                <p className="text-sm text-stone-700 leading-relaxed">
                  {microExperiment.instruction}
                </p>
              </div>
              <div className="bg-stone-50 rounded-xl p-3.5">
                <p className="text-xs font-semibold text-stone-400 uppercase tracking-widest mb-1.5">
                  How you'll know it worked
                </p>
                <p className="text-sm text-stone-700 leading-relaxed">
                  {microExperiment.success_marker}
                </p>
              </div>
            </div>
            {(microExperiment.quotes ?? []).map((q, i) => (
              <EvidenceQuote key={i} quote={q} />
            ))}
          </div>
        </section>
      )}
    </div>
  );
}

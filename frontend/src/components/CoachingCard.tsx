import type { CoachingItem, MicroExperiment } from '@/lib/types';
import { EvidenceQuote } from './EvidenceQuote';

interface CoachingCardProps {
  strengths: CoachingItem[];
  focus: CoachingItem | null;
  microExperiment: MicroExperiment | null;
}

export function CoachingCard({ strengths, focus, microExperiment }: CoachingCardProps) {
  return (
    <div className="space-y-6">
      {/* Strengths */}
      {strengths.length > 0 && (
        <section>
          <h3 className="text-sm font-semibold text-emerald-700 uppercase tracking-wide mb-3">
            Strengths
          </h3>
          <div className="space-y-4">
            {strengths.map((s) => (
              <div key={s.pattern_id} className="bg-emerald-50 border border-emerald-200 rounded-lg p-4">
                <p className="text-sm font-medium text-gray-800 mb-1 capitalize">
                  {s.pattern_id.replace(/_/g, ' ')}
                </p>
                <p className="text-sm text-gray-700">{s.message}</p>
                {s.quotes.map((q, i) => (
                  <EvidenceQuote key={i} quote={q} />
                ))}
              </div>
            ))}
          </div>
        </section>
      )}

      {/* Focus */}
      {focus && (
        <section>
          <h3 className="text-sm font-semibold text-amber-700 uppercase tracking-wide mb-3">
            Focus Area
          </h3>
          <div className="bg-amber-50 border border-amber-200 rounded-lg p-4">
            <p className="text-sm font-medium text-gray-800 mb-1 capitalize">
              {focus.pattern_id.replace(/_/g, ' ')}
            </p>
            <p className="text-sm text-gray-700">{focus.message}</p>
            {focus.quotes.map((q, i) => (
              <EvidenceQuote key={i} quote={q} />
            ))}
          </div>
        </section>
      )}

      {/* Micro-experiment */}
      {microExperiment && (
        <section>
          <h3 className="text-sm font-semibold text-indigo-700 uppercase tracking-wide mb-3">
            Micro-Experiment
          </h3>
          <div className="bg-indigo-50 border border-indigo-200 rounded-lg p-4 space-y-3">
            <div>
              <p className="text-sm font-semibold text-gray-800">{microExperiment.title}</p>
              <p className="text-xs text-gray-500">{microExperiment.experiment_id}</p>
            </div>
            <div>
              <p className="text-xs font-medium text-gray-600 uppercase mb-1">Instruction</p>
              <p className="text-sm text-gray-700">{microExperiment.instruction}</p>
            </div>
            <div>
              <p className="text-xs font-medium text-gray-600 uppercase mb-1">Success Marker</p>
              <p className="text-sm text-gray-700">{microExperiment.success_marker}</p>
            </div>
            {microExperiment.quotes.map((q, i) => (
              <EvidenceQuote key={i} quote={q} />
            ))}
          </div>
        </section>
      )}
    </div>
  );
}

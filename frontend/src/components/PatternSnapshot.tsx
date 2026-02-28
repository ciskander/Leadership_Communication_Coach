interface PatternItem {
  pattern_id: string;
  evaluable_status: string;
  numerator?: number;
  denominator?: number;
  ratio?: number;
  balance_assessment?: string;
  tier?: number;
}

interface PatternSnapshotProps {
  patterns: PatternItem[];
}

const PATTERN_LABELS: Record<string, string> = {
  agenda_clarity: 'Agenda Clarity',
  objective_signaling: 'Objective Signaling',
  turn_allocation: 'Turn Allocation',
  facilitative_inclusion: 'Facilitative Inclusion',
  decision_closure: 'Decision Closure',
  owner_timeframe_specification: 'Owner & Timeframe',
  summary_checkback: 'Summary & Check-back',
  question_quality: 'Question Quality',
  listener_response_quality: 'Listener Response',
  conversational_balance: 'Conversational Balance',
};

function RatioBar({ ratio }: { ratio: number }) {
  const pct = Math.round(ratio * 100);
  const color =
    pct >= 75 ? 'bg-emerald-500' : pct >= 50 ? 'bg-amber-400' : 'bg-rose-400';
  return (
    <div className="flex items-center gap-2">
      <div className="flex-1 bg-gray-200 rounded-full h-2">
        <div
          className={`h-2 rounded-full ${color}`}
          style={{ width: `${pct}%` }}
        />
      </div>
      <span className="text-xs text-gray-600 w-10 text-right">{pct}%</span>
    </div>
  );
}

export function PatternSnapshot({ patterns }: PatternSnapshotProps) {
  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
      {patterns.map((p) => (
        <div key={p.pattern_id} className="bg-white border border-gray-200 rounded-lg p-3">
          <div className="flex items-center justify-between mb-1">
            <span className="text-xs font-medium text-gray-700">
              {PATTERN_LABELS[p.pattern_id] ?? p.pattern_id}
            </span>
            {p.tier && (
              <span className="text-xs text-gray-400">T{p.tier}</span>
            )}
          </div>
          {p.evaluable_status === 'evaluable' && p.ratio != null ? (
            <RatioBar ratio={p.ratio} />
          ) : p.evaluable_status === 'evaluable' && p.balance_assessment ? (
            <span className="text-xs text-gray-600 capitalize">
              {p.balance_assessment.replace('_', ' ')}
            </span>
          ) : (
            <span className="text-xs text-gray-400 capitalize">
              {p.evaluable_status === 'insufficient_signal'
                ? 'Insufficient signal'
                : 'Not evaluable'}
            </span>
          )}
        </div>
      ))}
    </div>
  );
}

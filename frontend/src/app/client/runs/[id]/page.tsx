'use client';

import { useParams } from 'next/navigation';
import { RunStatusPoller } from '@/components/RunStatusPoller';

export default function RunResultsPage() {
  const { id } = useParams<{ id: string }>();

  return (
    <div className="max-w-2xl mx-auto space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-gray-900">Run Results</h1>
        <p className="text-xs text-gray-400 mt-0.5">{id}</p>
      </div>
      <RunStatusPoller runId={id} />
    </div>
  );
}

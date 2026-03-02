'use client';

import { useParams } from 'next/navigation';
import Link from 'next/link';
import { RunStatusPoller } from '@/components/RunStatusPoller';

export default function RunResultsPage() {
  const { id } = useParams<{ id: string }>();

  return (
    <div className="max-w-2xl mx-auto space-y-5 py-2">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-stone-900">Meeting Analysis</h1>
          <p className="text-xs text-stone-400 mt-0.5 font-mono">{id}</p>
        </div>
        <Link
          href="/client"
          className="text-sm text-stone-500 hover:text-stone-700 transition-colors"
        >
          ← Dashboard
        </Link>
      </div>
      <RunStatusPoller runId={id} />
    </div>
  );
}

'use client';

import { useEffect, useState } from 'react';
import { useParams } from 'next/navigation';
import Link from 'next/link';
import { api } from '@/lib/api';
import type { BaselinePack } from '@/lib/types';
import { CoachingCard } from '@/components/CoachingCard';

export default function BaselineDetailPage() {
  const { id } = useParams<{ id: string }>();
  const [pack, setPack] = useState<BaselinePack | null>(null);
  const [loading, setLoading] = useState(true);

  const fetchPack = () => {
    api.getBaselinePack(id).then(setPack).finally(() => setLoading(false));
  };

  useEffect(() => {
    fetchPack();
  }, [id]);

  // Auto-poll while building
  useEffect(() => {
    if (pack && (pack.status === 'building' || pack.status === 'intake')) {
      const t = setTimeout(fetchPack, 5000);
      return () => clearTimeout(t);
    }
  }, [pack]);

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-indigo-600" />
      </div>
    );
  }

  if (!pack) return <p className="text-sm text-gray-600">Baseline pack not found.</p>;

  return (
    <div className="max-w-2xl mx-auto space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold text-gray-900">Baseline Pack</h1>
        <span className="text-xs bg-gray-100 text-gray-600 px-2 py-1 rounded-full">
          {pack.baseline_pack_id}
        </span>
      </div>

      {(pack.status === 'building' || pack.status === 'intake') && (
        <div className="bg-blue-50 border border-blue-200 rounded-lg p-6 text-center space-y-2">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-500 mx-auto" />
          <p className="text-sm text-blue-700 font-medium">Building your baseline…</p>
          <p className="text-xs text-blue-600">This usually takes 2–5 minutes.</p>
        </div>
      )}

      {pack.status === 'baseline_ready' && (
        <div className="space-y-6">
          <div className="bg-green-50 border border-green-200 rounded-lg px-4 py-3">
            <p className="text-sm text-green-700 font-medium">✓ Baseline complete</p>
          </div>

          <CoachingCard
            strengths={pack.strengths ?? []}
            focus={pack.focus ?? null}
            microExperiment={pack.micro_experiment ?? null}
          />

          <Link
            href="/client/experiment"
            className="inline-block px-4 py-2 bg-indigo-600 text-white rounded-md text-sm hover:bg-indigo-700"
          >
            Go to Active Experiment →
          </Link>
        </div>
      )}

      {pack.status === 'error' && (
        <div className="bg-red-50 border border-red-200 rounded-lg p-6">
          <p className="text-sm text-red-700">Baseline build failed. Please try again.</p>
        </div>
      )}
    </div>
  );
}

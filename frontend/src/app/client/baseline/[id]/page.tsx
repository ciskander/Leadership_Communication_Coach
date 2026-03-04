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

  useEffect(() => {
    if (pack && (pack.status === 'building' || pack.status === 'intake')) {
      const t = setTimeout(fetchPack, 5000);
      return () => clearTimeout(t);
    }
  }, [pack]);

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-emerald-600" />
      </div>
    );
  }

  if (!pack) {
    return (
      <div className="max-w-xl mx-auto py-12 text-center">
        <p className="text-sm text-stone-500">Baseline pack not found.</p>
      </div>
    );
  }

  const isBuilding = pack.status === 'draft' || pack.status === 'building' || pack.status === 'intake';
  const isReady = pack.status === 'baseline_ready' || pack.status === 'completed';
  const isError = pack.status === 'error';

  return (
    <div className="max-w-2xl mx-auto space-y-6 py-2">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold text-stone-900">Baseline Pack</h1>
        <span className="text-xs bg-stone-100 text-stone-500 px-2.5 py-1 rounded-full font-mono">
          {pack.baseline_pack_id}
        </span>
      </div>

      {/* Building state */}
      {isBuilding && (
        <div className="bg-white rounded-2xl border border-blue-200 p-8 text-center space-y-4">
          <div className="relative mx-auto w-14 h-14">
            <div className="w-14 h-14 rounded-full border-2 border-stone-100" />
            <div className="absolute inset-0 w-14 h-14 rounded-full border-2 border-blue-500 border-t-transparent animate-spin" />
          </div>
          <div>
            <p className="text-sm font-semibold text-stone-800">Building your baseline…</p>
            <p className="text-xs text-stone-400 mt-1">This usually takes 2–5 minutes. This page will update automatically.</p>
          </div>
        </div>
      )}

      {/* Error state */}
      {isError && (
        <div className="bg-white rounded-2xl border border-rose-200 p-6 space-y-3">
          <p className="text-sm font-semibold text-rose-700">Baseline build failed</p>
          <p className="text-sm text-stone-500">
            Something went wrong during analysis. Please try creating a new baseline pack.
          </p>
          <Link
            href="/client/baseline/new"
            className="inline-block text-sm px-4 py-2 bg-emerald-600 text-white rounded-xl font-medium hover:bg-emerald-700 transition-colors"
          >
            Try again
          </Link>
        </div>
      )}

      {/* Ready state */}
      {isReady && (
        <>
          <div className="bg-emerald-50 border border-emerald-200 rounded-2xl px-5 py-3.5 flex items-center gap-3">
            <span className="text-emerald-600 text-lg">✦</span>
            <div>
              <p className="text-sm font-semibold text-emerald-800">Baseline complete</p>
              <p className="text-xs text-emerald-600">Your communication patterns have been mapped across 3 meetings</p>
            </div>
          </div>

          <CoachingCard
            strengths={pack.strengths ?? []}
            focus={pack.focus ?? null}
            microExperiment={pack.micro_experiment ?? null}
          />

          <div className="flex gap-3">
            <Link
              href="/client/experiment"
              className="flex-1 text-center py-3 bg-emerald-600 text-white rounded-xl text-sm font-semibold hover:bg-emerald-700 transition-colors shadow-sm"
            >
              View my experiment →
            </Link>
            <Link
              href="/client/analyze"
              className="px-5 py-3 bg-white border border-stone-300 text-stone-700 rounded-xl text-sm font-medium hover:bg-stone-50 transition-colors"
            >
              Analyse a meeting
            </Link>
          </div>
        </>
      )}
    </div>
  );
}

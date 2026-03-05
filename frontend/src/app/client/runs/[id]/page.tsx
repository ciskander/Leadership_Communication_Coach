'use client';

import { useEffect, useState } from 'react';
import { useParams } from 'next/navigation';
import Link from 'next/link';
import { RunStatusPoller } from '@/components/RunStatusPoller';
import { api } from '@/lib/api';

// ── Types ─────────────────────────────────────────────────────────────────────

interface RunMeta {
  run_id: string;
  analysis_type: string | null;
  title: string | null;
  transcript_id: string | null;
  meeting_date: string | null;
  meeting_type: string | null;
  target_role: string | null;
}

// ── Helpers ───────────────────────────────────────────────────────────────────

const ROLE_LABELS: Record<string, string> = {
  chair: 'Chair',
  presenter: 'Presenter',
  participant: 'Participant',
  manager_1to1: 'Manager (1:1)',
  report_1to1: 'Report (1:1)',
};

function fmtDate(dateStr: string | null | undefined): string {
  if (!dateStr) return '';
  try {
    return new Date(dateStr).toLocaleDateString('en-GB', {
      day: 'numeric', month: 'short', year: 'numeric',
    });
  } catch {
    return dateStr;
  }
}

// ── Page ──────────────────────────────────────────────────────────────────────

export default function RunResultsPage() {
  const { id } = useParams<{ id: string }>();
  const [meta, setMeta] = useState<RunMeta | null>(null);

  useEffect(() => {
    if (id) api.getRunMeta(id).then(setMeta).catch(() => setMeta(null));
  }, [id]);

  const isBaseline = meta?.analysis_type === 'baseline_pack';
  const pageTitle = isBaseline ? 'Baseline Pack Analysis' : 'Meeting Analysis';

  return (
    <div className="max-w-2xl mx-auto space-y-5 py-2">
      <div className="flex items-start justify-between gap-4">
        <div className="min-w-0">
          <h1 className="text-2xl font-bold text-stone-900">{pageTitle}</h1>

          {meta ? (
            <div className="mt-1 space-y-0.5">
              {/* Meeting title */}
              {meta.title && (
                <p className="text-sm font-medium text-stone-700 truncate">{meta.title}</p>
              )}
              {/* Meta row */}
              <div className="flex flex-wrap items-center gap-x-2 gap-y-0.5 text-xs text-stone-400">
                {meta.transcript_id && (
                  <span className="font-mono">{meta.transcript_id}</span>
                )}
                {meta.meeting_date && (
                  <>
                    {meta.transcript_id && <span>·</span>}
                    <span>{fmtDate(meta.meeting_date)}</span>
                  </>
                )}
                {meta.meeting_type && (
                  <>
                    <span>·</span>
                    <span>{meta.meeting_type}</span>
                  </>
                )}
                {meta.target_role && (
                  <>
                    <span>·</span>
                    <span>{ROLE_LABELS[meta.target_role] ?? meta.target_role}</span>
                  </>
                )}
              </div>
            </div>
          ) : (
            // Fallback while loading — show the raw run ID as before
            <p className="text-xs text-stone-400 mt-0.5 font-mono">{id}</p>
          )}
        </div>

        <Link
          href="/client"
          className="text-sm text-stone-500 hover:text-stone-700 transition-colors flex-shrink-0 mt-1"
        >
          ← Dashboard
        </Link>
      </div>

      <RunStatusPoller runId={id} />
    </div>
  );
}

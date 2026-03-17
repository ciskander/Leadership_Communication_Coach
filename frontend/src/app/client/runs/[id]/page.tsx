'use client';

import { useEffect, useState } from 'react';
import { useParams, useRouter } from 'next/navigation';
import Link from 'next/link';
import { RunStatusPoller } from '@/components/RunStatusPoller';
import { api } from '@/lib/api';
import { STRINGS } from '@/config/strings';
import type { RunMeta } from '@/lib/types';

// ─── Helpers ──────────────────────────────────────────────────────────────────

const ROLE_LABELS = STRINGS.roles;

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

// ─── Confirm delete modal ─────────────────────────────────────────────────────

function ConfirmDeleteModal({
  onConfirm,
  onCancel,
  deleting,
}: {
  onConfirm: () => void;
  onCancel: () => void;
  deleting: boolean;
}) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/40">
      <div className="bg-white rounded shadow-xl max-w-sm w-full p-6 space-y-4">
        <div className="flex items-start gap-3">
          {/* Warning icon */}
          <div className="w-9 h-9 rounded-full bg-cv-red-50 flex items-center justify-center shrink-0">
            <svg viewBox="0 0 20 20" fill="currentColor" className="w-5 h-5 text-cv-red-600" aria-hidden="true">
              <path fillRule="evenodd" d="M8.485 2.495c.673-1.167 2.357-1.167 3.03 0l6.28 10.875c.673 1.167-.17 2.625-1.516 2.625H3.72c-1.347 0-2.189-1.458-1.515-2.625L8.485 2.495zM10 5a.75.75 0 01.75.75v3.5a.75.75 0 01-1.5 0v-3.5A.75.75 0 0110 5zm0 9a1 1 0 100-2 1 1 0 000 2z" clipRule="evenodd" />
            </svg>
          </div>
          <div>
            <h3 className="font-semibold text-cv-stone-900 text-sm">{STRINGS.runResults.deleteModalTitle}</h3>
            <p className="text-xs text-cv-stone-500 mt-1 leading-relaxed">
              {STRINGS.runResults.deleteModalDesc}
            </p>
          </div>
        </div>

        <div className="flex gap-2 justify-end pt-1">
          <button
            onClick={onCancel}
            disabled={deleting}
            className="px-4 py-2 text-xs font-semibold text-cv-stone-600 bg-cv-warm-100 rounded hover:bg-cv-warm-200 transition-colors disabled:opacity-50"
          >
            {STRINGS.common.cancel}
          </button>
          <button
            onClick={onConfirm}
            disabled={deleting}
            className="px-4 py-2 text-xs font-semibold text-white bg-cv-red-600 rounded hover:bg-cv-red-700 transition-colors disabled:opacity-50 flex items-center gap-1.5"
          >
            {deleting && (
              <svg className="w-3 h-3 animate-spin" viewBox="0 0 24 24" fill="none" aria-hidden="true">
                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z" />
              </svg>
            )}
            {deleting ? STRINGS.common.deleting : STRINGS.common.delete}
          </button>
        </div>
      </div>
    </div>
  );
}

// ─── Meta pill ────────────────────────────────────────────────────────────────

function MetaPill({ children }: { children: React.ReactNode }) {
  return (
    <span className="inline-flex items-center px-2 py-0.5 rounded bg-cv-warm-100 text-2xs font-medium text-cv-stone-500 tabular-nums">
      {children}
    </span>
  );
}

// ─── Page ─────────────────────────────────────────────────────────────────────

export default function RunResultsPage() {
  const { id }      = useParams<{ id: string }>();
  const router      = useRouter();
  const [meta, setMeta]               = useState<RunMeta | null>(null);
  const [showConfirm, setShowConfirm] = useState(false);
  const [deleting, setDeleting]       = useState(false);
  const [deleteError, setDeleteError] = useState<string | null>(null);

  useEffect(() => {
    if (id) api.getRunMeta(id).then(setMeta).catch(() => setMeta(null));
  }, [id]);

  async function handleDeleteConfirmed() {
    setDeleting(true);
    setDeleteError(null);
    try {
      await api.deleteRun(id);
      router.push('/client');
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : STRINGS.runResults.deletionFailed;
      setDeleteError(msg);
      setDeleting(false);
      setShowConfirm(false);
    }
  }

  const isBaseline = meta?.analysis_type === 'baseline_pack';
  const pageTitle  = isBaseline ? STRINGS.common.baselinePackAnalysis : STRINGS.common.meetingAnalysis;
  const canDelete  = meta !== null && !isBaseline;

  return (
    <div className="max-w-5xl mx-auto space-y-6 py-2">

      {showConfirm && (
        <ConfirmDeleteModal
          onConfirm={handleDeleteConfirmed}
          onCancel={() => setShowConfirm(false)}
          deleting={deleting}
        />
      )}

      {/* ── Header ── */}
      <div className="flex items-center justify-between gap-4">
        <div className="min-w-0">
          <h1 className="font-serif text-2xl text-cv-stone-900">{pageTitle}</h1>

          {meta ? (
            <div className="mt-2 space-y-1.5">
              {meta.title && (
                <p className="text-sm font-medium text-cv-stone-700 truncate">{meta.title}</p>
              )}
              <div className="flex flex-wrap items-center gap-1.5">
                {meta.transcript_id && (
                  <MetaPill>
                    <span className="font-mono">{meta.transcript_id}</span>
                  </MetaPill>
                )}
                {meta.meeting_date && (
                  <MetaPill>{fmtDate(meta.meeting_date)}</MetaPill>
                )}
                {meta.meeting_type && (
                  <MetaPill>{meta.meeting_type}</MetaPill>
                )}
                {meta.target_role && (
                  <MetaPill>{ROLE_LABELS[meta.target_role] ?? meta.target_role}</MetaPill>
                )}
              </div>
            </div>
          ) : (
            <p className="text-xs text-cv-stone-400 mt-1 font-mono">{id}</p>
          )}
        </div>

        <Link
          href="/client"
          className="text-sm text-cv-stone-400 hover:text-cv-stone-700 transition-colors shrink-0"
        >
          {STRINGS.nav.dashboard}
        </Link>
      </div>

      {/* ── Analysis output ── */}
      <RunStatusPoller runId={id} />

      {/* ── Delete ── */}
      {canDelete && (
        <div className="pt-4 border-t border-cv-warm-200">
          {deleteError && (
            <p className="text-xs text-cv-red-600 mb-3">{deleteError}</p>
          )}
          <button
            onClick={() => setShowConfirm(true)}
            className="text-xs font-medium text-cv-stone-400 hover:text-cv-red-600 transition-colors"
          >
            {STRINGS.runResults.deleteThisMeeting}
          </button>
        </div>
      )}
    </div>
  );
}

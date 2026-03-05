'use client';

import { useEffect, useState } from 'react';
import { useParams, useRouter } from 'next/navigation';
import Link from 'next/link';
import { RunStatusPoller } from '@/components/RunStatusPoller';
import { api } from '@/lib/api';
import type { RunMeta } from '@/lib/types';

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

// ── Confirm Delete Modal ──────────────────────────────────────────────────────

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
      <div className="bg-white rounded-2xl shadow-xl max-w-sm w-full p-6 space-y-4">
        <div className="flex items-start gap-3">
          <div className="w-9 h-9 rounded-full bg-rose-100 flex items-center justify-center flex-shrink-0">
            <svg className="w-5 h-5 text-rose-600" viewBox="0 0 20 20" fill="currentColor">
              <path fillRule="evenodd" d="M8.485 2.495c.673-1.167 2.357-1.167 3.03 0l6.28 10.875c.673 1.167-.17 2.625-1.516 2.625H3.72c-1.347 0-2.189-1.458-1.515-2.625L8.485 2.495zM10 5a.75.75 0 01.75.75v3.5a.75.75 0 01-1.5 0v-3.5A.75.75 0 0110 5zm0 9a1 1 0 100-2 1 1 0 000 2z" clipRule="evenodd" />
            </svg>
          </div>
          <div>
            <h3 className="font-semibold text-stone-900 text-sm">Delete this meeting?</h3>
            <p className="text-xs text-stone-500 mt-1 leading-relaxed">
              This will permanently delete the meeting and its analysis results. This cannot be undone.
            </p>
          </div>
        </div>
        <div className="flex gap-2 justify-end pt-1">
          <button
            onClick={onCancel}
            disabled={deleting}
            className="px-4 py-2 text-xs font-semibold text-stone-600 bg-stone-100 rounded-xl hover:bg-stone-200 transition-colors disabled:opacity-50"
          >
            Cancel
          </button>
          <button
            onClick={onConfirm}
            disabled={deleting}
            className="px-4 py-2 text-xs font-semibold text-white bg-rose-600 rounded-xl hover:bg-rose-700 transition-colors disabled:opacity-50 flex items-center gap-1.5"
          >
            {deleting && (
              <svg className="w-3 h-3 animate-spin" viewBox="0 0 24 24" fill="none">
                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z" />
              </svg>
            )}
            {deleting ? 'Deleting…' : 'Delete'}
          </button>
        </div>
      </div>
    </div>
  );
}

// ── Page ──────────────────────────────────────────────────────────────────────

export default function RunResultsPage() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const [meta, setMeta] = useState<RunMeta | null>(null);
  const [showConfirm, setShowConfirm] = useState(false);
  const [deleting, setDeleting] = useState(false);
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
      const msg = err instanceof Error ? err.message : 'Deletion failed. Please try again.';
      setDeleteError(msg);
      setDeleting(false);
      setShowConfirm(false);
    }
  }

  const isBaseline = meta?.analysis_type === 'baseline_pack';
  const pageTitle = isBaseline ? 'Baseline Pack Analysis' : 'Meeting Analysis';
  const canDelete = meta !== null && !isBaseline;

  return (
    <div className="max-w-2xl mx-auto space-y-5 py-2">

      {showConfirm && (
        <ConfirmDeleteModal
          onConfirm={handleDeleteConfirmed}
          onCancel={() => setShowConfirm(false)}
          deleting={deleting}
        />
      )}

      {/* Header */}
      <div className="flex items-start justify-between gap-4">
        <div className="min-w-0">
          <h1 className="text-2xl font-bold text-stone-900">{pageTitle}</h1>
          {meta ? (
            <div className="mt-1 space-y-0.5">
              {meta.title && (
                <p className="text-sm font-medium text-stone-700 truncate">{meta.title}</p>
              )}
              <div className="flex flex-wrap items-center gap-x-2 gap-y-0.5 text-xs text-stone-400">
                {meta.transcript_id && <span className="font-mono">{meta.transcript_id}</span>}
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

      {/* Analysis output */}
      <RunStatusPoller runId={id} />

      {/* Delete section */}
      {canDelete && (
        <div className="pt-4 border-t border-stone-100">
          {deleteError && (
            <p className="text-xs text-rose-600 mb-3">{deleteError}</p>
          )}
          <button
            onClick={() => setShowConfirm(true)}
            className="text-xs font-medium text-stone-400 hover:text-rose-600 transition-colors"
          >
            Delete this meeting
          </button>
        </div>
      )}
    </div>
  );
}

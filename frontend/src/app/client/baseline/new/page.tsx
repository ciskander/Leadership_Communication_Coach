'use client';

import { useState, useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { api } from '@/lib/api';
import { TranscriptUploadPanel } from '@/components/TranscriptUpload';
import { SpeakerChips } from '@/components/SpeakerChips';
import type { TranscriptListItem, TargetRole } from '@/lib/types';

interface TranscriptConfig {
  transcript_id: string;
  speaker_labels: string[];
  target_speaker_label: string | null;
  target_speaker_name: string;
  target_role: TargetRole | '';
}

const ROLE_OPTIONS = [
  { value: 'chair',        label: 'Chair / Facilitator' },
  { value: 'presenter',    label: 'Presenter' },
  { value: 'participant',  label: 'Participant' },
  { value: 'manager_1to1', label: '1:1 Manager' },
  { value: 'report_1to1',  label: '1:1 Report' },
];

// ── Per-slot component ────────────────────────────────────────────────────────

function TranscriptSlot({
  index,
  existingTranscripts,
  onComplete,
}: {
  index: number;
  existingTranscripts: TranscriptListItem[];
  onComplete: (config: TranscriptConfig | null) => void;
}) {
  const [mode, setMode] = useState<'select' | 'upload'>(
    existingTranscripts.length > 0 ? 'select' : 'upload'
  );

  // select-mode state
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [speakerLabels, setSpeakerLabels] = useState<string[]>([]);
  const [speakerLabel, setSpeakerLabel] = useState<string | null>(null);
  const [name, setName] = useState('');
  const [role, setRole] = useState<TargetRole | ''>('');

  // Notify parent whenever select-mode fields change
  useEffect(() => {
    if (mode !== 'select') return;
    if (selectedId && speakerLabel && name && role) {
      onComplete({ transcript_id: selectedId, speaker_labels: speakerLabels, target_speaker_label: speakerLabel, target_speaker_name: name, target_role: role });
    } else {
      onComplete(null);
    }
  }, [mode, selectedId, speakerLabel, name, role]);

  const handleSelect = (t: TranscriptListItem) => {
    setSelectedId(t.transcript_id);
    setSpeakerLabels(t.speaker_labels);
    setSpeakerLabel(t.speaker_labels[0] ?? null);
    setName('');
    setRole('');
    onComplete(null);
  };

  const switchMode = (next: 'select' | 'upload') => {
    setMode(next);
    setSelectedId(null);
    setSpeakerLabel(null);
    setName('');
    setRole('');
    onComplete(null);
  };

  return (
    <div className="border border-gray-200 rounded-lg p-4 space-y-3">
      {/* Header + mode toggle */}
      <div className="flex items-center justify-between">
        <p className="text-sm font-medium text-gray-700">Meeting {index + 1} of 3</p>
        <div className="flex gap-1 text-xs bg-gray-100 rounded-md p-0.5">
          {(['select', 'upload'] as const).map((m) => (
            <button
              key={m}
              onClick={() => switchMode(m)}
              className={`px-2.5 py-1 rounded transition-colors ${
                mode === m
                  ? 'bg-white text-gray-900 shadow-sm font-medium'
                  : 'text-gray-500 hover:text-gray-700'
              }`}
            >
              {m === 'select' ? 'Select existing' : 'Upload new'}
            </button>
          ))}
        </div>
      </div>

      {/* Upload mode */}
      {mode === 'upload' && (
        <TranscriptUploadPanel label="" onComplete={(c) => onComplete(c)} />
      )}

      {/* Select mode */}
      {mode === 'select' && (
        <div className="space-y-3">
          <div className="max-h-48 overflow-y-auto rounded-md border border-gray-100 divide-y divide-gray-50">
            {existingTranscripts.length === 0 ? (
              <p className="text-xs text-gray-400 text-center py-6">
                No transcripts uploaded yet.{' '}
                <button className="text-indigo-600 underline" onClick={() => switchMode('upload')}>
                  Upload one
                </button>
              </p>
            ) : (
              existingTranscripts.map((t) => (
                <label
                  key={t.transcript_id}
                  className={`flex items-start gap-3 px-3 py-2.5 cursor-pointer hover:bg-gray-50 transition-colors ${
                    selectedId === t.transcript_id ? 'bg-indigo-50' : ''
                  }`}
                >
                  <input
                    type="radio"
                    name={`slot-${index}`}
                    value={t.transcript_id}
                    checked={selectedId === t.transcript_id}
                    onChange={() => handleSelect(t)}
                    className="mt-0.5 accent-indigo-600"
                  />
                  <div className="min-w-0">
                    <p className="text-sm text-gray-800 truncate">{t.title || 'Untitled'}</p>
                    <p className="text-xs text-gray-400">
                      {[t.meeting_type, t.meeting_date].filter(Boolean).join(' · ')}
                    </p>
                  </div>
                </label>
              ))
            )}
          </div>

          {/* Config fields — only show once a transcript is selected */}
          {selectedId && (
            <div className="space-y-2 pt-1">
              {speakerLabels.length > 0 ? (
                <div>
                  <p className="text-xs text-gray-500 mb-1">Select target speaker</p>
                  <SpeakerChips
                    speakers={speakerLabels}
                    selected={speakerLabel}
                    onSelect={setSpeakerLabel}
                  />
                </div>
              ) : (
                <div>
                  <label className="text-xs text-gray-500">Speaker label</label>
                  <input
                    type="text"
                    value={speakerLabel ?? ''}
                    onChange={(e) => setSpeakerLabel(e.target.value || null)}
                    placeholder="e.g. SPEAKER_00"
                    className="mt-1 w-full border border-gray-300 rounded-md px-3 py-1.5 text-sm"
                  />
                </div>
              )}
              <div>
                <label className="text-xs text-gray-500">Display name</label>
                <input
                  type="text"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  placeholder="e.g. Sarah"
                  className="mt-1 w-full border border-gray-300 rounded-md px-3 py-1.5 text-sm"
                />
              </div>
              <div>
                <label className="text-xs text-gray-500">Target role</label>
                <select
                  value={role}
                  onChange={(e) => setRole(e.target.value as TargetRole)}
                  className="mt-1 w-full border border-gray-300 rounded-md px-3 py-1.5 text-sm"
                >
                  <option value="">Select role…</option>
                  {ROLE_OPTIONS.map((r) => (
                    <option key={r.value} value={r.value}>{r.label}</option>
                  ))}
                </select>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// ── Page ──────────────────────────────────────────────────────────────────────

export default function BaselineNewPage() {
  const router = useRouter();
  const [existingTranscripts, setExistingTranscripts] = useState<TranscriptListItem[]>([]);
  const [loadingTranscripts, setLoadingTranscripts] = useState(true);
  const [configs, setConfigs] = useState<(TranscriptConfig | null)[]>([null, null, null]);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.listTranscripts()
      .then(setExistingTranscripts)
      .catch(() => {}) // non-fatal — slots still work in upload mode
      .finally(() => setLoadingTranscripts(false));
  }, []);

  const setConfig = (i: number, config: TranscriptConfig | null) => {
    setConfigs((prev) => {
      const next = [...prev];
      next[i] = config;
      return next;
    });
  };

  const allReady = configs.every(
    (c) => c && c.target_speaker_label && c.target_role && c.target_speaker_name
  );

  const handleSubmit = async () => {
    if (!allReady) return;
    setSubmitting(true);
    setError(null);
    try {
      const first = configs[0]!;
      const created = await api.createBaselinePack({
        transcript_ids: configs.map((c) => c!.transcript_id),
        target_speaker_name: first.target_speaker_name,
        target_speaker_label: first.target_speaker_label!,
        target_role: first.target_role as TargetRole,
      });
      await api.buildBaselinePack(created.baseline_pack_id);
      router.push(`/client/baseline/${created.baseline_pack_id}`);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Submission failed');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="max-w-2xl mx-auto space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-gray-900">Create Baseline Pack</h1>
        <p className="text-sm text-gray-500 mt-1">
          Choose 3 transcripts from past meetings to build your communication baseline.
        </p>
      </div>

      {loadingTranscripts ? (
        <p className="text-sm text-gray-400">Loading your transcripts…</p>
      ) : (
        <div className="space-y-4">
          {[0, 1, 2].map((i) => (
            <TranscriptSlot
              key={i}
              index={i}
              existingTranscripts={existingTranscripts}
              onComplete={(config) => setConfig(i, config)}
            />
          ))}
        </div>
      )}

      {error && <p className="text-sm text-red-600">{error}</p>}

      <button
        onClick={handleSubmit}
        disabled={!allReady || submitting}
        className="w-full py-3 bg-indigo-600 text-white rounded-lg font-medium text-sm hover:bg-indigo-700 disabled:opacity-40 disabled:cursor-not-allowed"
      >
        {submitting ? 'Building baseline…' : 'Build Baseline Pack'}
      </button>
    </div>
  );
}
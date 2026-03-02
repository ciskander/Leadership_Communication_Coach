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
  const [transcriptId, setTranscriptId] = useState<string | null>(null);
  const [speakerLabels, setSpeakerLabels] = useState<string[]>([]);
  const [speakerLabel, setSpeakerLabel] = useState<string | null>(null);
  const [name, setName] = useState('');
  const [role, setRole] = useState<TargetRole | ''>('');

  const notify = (tid: string | null, sl: string | null, n: string, r: TargetRole | '', labels: string[]) => {
    if (tid && sl && n && r) {
      onComplete({ transcript_id: tid, speaker_labels: labels, target_speaker_label: sl, target_speaker_name: n, target_role: r });
    } else {
      onComplete(null);
    }
  };

  const setField = (patch: { speakerLabel?: string | null; name?: string; role?: TargetRole | '' }) => {
    const sl = patch.speakerLabel !== undefined ? patch.speakerLabel : speakerLabel;
    const n = patch.name !== undefined ? patch.name : name;
    const r = patch.role !== undefined ? patch.role : role;
    if (patch.speakerLabel !== undefined) setSpeakerLabel(sl);
    if (patch.name !== undefined) setName(n);
    if (patch.role !== undefined) setRole(r);
    notify(transcriptId, sl, n, r, speakerLabels);
  };

  const applyTranscript = (tid: string, labels: string[]) => {
    setTranscriptId(tid);
    setSpeakerLabels(labels);
    setSpeakerLabel(labels[0] ?? null);
    setName('');
    setRole('');
    notify(tid, labels[0] ?? null, '', '', labels);
  };

  const switchMode = (next: 'select' | 'upload') => {
    setMode(next);
    setTranscriptId(null);
    setSpeakerLabels([]);
    setSpeakerLabel(null);
    setName('');
    setRole('');
    onComplete(null);
  };

  const isComplete = !!(transcriptId && speakerLabel && name && role);

  return (
    <div className={`bg-white rounded-2xl border transition-colors ${
      isComplete ? 'border-emerald-300' : 'border-stone-200'
    } overflow-hidden`}>
      {/* Header */}
      <div className={`flex items-center justify-between px-5 py-3.5 border-b ${
        isComplete ? 'bg-emerald-50 border-emerald-200' : 'bg-stone-50 border-stone-100'
      }`}>
        <div className="flex items-center gap-2.5">
          <div className={`w-6 h-6 rounded-full flex items-center justify-center text-xs font-bold ${
            isComplete ? 'bg-emerald-600 text-white' : 'bg-stone-200 text-stone-600'
          }`}>
            {isComplete ? '✓' : index + 1}
          </div>
          <p className="text-sm font-semibold text-stone-800">Meeting {index + 1}</p>
        </div>
        <div className="flex gap-0.5 bg-white rounded-lg p-0.5 border border-stone-200">
          {(['select', 'upload'] as const).map((m) => (
            <button
              key={m}
              onClick={() => switchMode(m)}
              className={`px-3 py-1 rounded-md text-xs font-medium transition-colors ${
                mode === m ? 'bg-stone-900 text-white' : 'text-stone-500 hover:text-stone-700'
              }`}
            >
              {m === 'select' ? 'Existing' : 'Upload new'}
            </button>
          ))}
        </div>
      </div>

      {/* Content */}
      <div className="px-5 py-4 space-y-4">
        {mode === 'upload' && (
          <TranscriptUploadPanel
            onUploaded={({ transcript_id, speaker_labels }) =>
              applyTranscript(transcript_id, speaker_labels)
            }
          />
        )}

        {mode === 'select' && (
          <div className="max-h-44 overflow-y-auto rounded-xl border border-stone-100 divide-y divide-stone-50">
            {existingTranscripts.length === 0 ? (
              <p className="text-xs text-stone-400 text-center py-6">
                No transcripts yet.{' '}
                <button className="text-emerald-600 underline" onClick={() => switchMode('upload')}>
                  Upload one
                </button>
              </p>
            ) : (
              existingTranscripts.map((t) => (
                <label
                  key={t.transcript_id}
                  className={`flex items-start gap-3 px-3 py-2.5 cursor-pointer hover:bg-stone-50 transition-colors ${
                    transcriptId === t.transcript_id ? 'bg-emerald-50' : ''
                  }`}
                >
                  <input
                    type="radio"
                    name={`slot-${index}`}
                    value={t.transcript_id}
                    checked={transcriptId === t.transcript_id}
                    onChange={() => applyTranscript(t.transcript_id, t.speaker_labels)}
                    className="mt-0.5 accent-emerald-600"
                  />
                  <div className="min-w-0">
                    <p className="text-sm text-stone-800 truncate font-medium">{t.title || 'Untitled'}</p>
                    <p className="text-xs text-stone-400">
                      {[t.meeting_type, t.meeting_date].filter(Boolean).join(' · ')}
                    </p>
                  </div>
                </label>
              ))
            )}
          </div>
        )}

        {/* Config fields — shown after transcript selected */}
        {transcriptId && (
          <div className="space-y-3 pt-1 border-t border-stone-100">
            {speakerLabels.length > 0 ? (
              <div>
                <p className="text-xs text-stone-500 mb-2">Target speaker</p>
                <SpeakerChips
                  speakers={speakerLabels}
                  selected={speakerLabel}
                  onSelect={(s) => setField({ speakerLabel: s })}
                />
              </div>
            ) : (
              <div>
                <label className="text-xs text-stone-500">Speaker label</label>
                <input
                  type="text"
                  value={speakerLabel ?? ''}
                  onChange={(e) => setField({ speakerLabel: e.target.value || null })}
                  placeholder="e.g. SPEAKER_00"
                  className="mt-1 w-full border border-stone-300 rounded-xl px-3 py-2 text-sm focus:outline-none focus:border-emerald-400"
                />
              </div>
            )}
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="text-xs text-stone-500">Speaker's name</label>
                <input
                  type="text"
                  value={name}
                  onChange={(e) => setField({ name: e.target.value })}
                  placeholder="Full name"
                  className="mt-1 w-full border border-stone-300 rounded-xl px-3 py-2 text-sm focus:outline-none focus:border-emerald-400"
                />
              </div>
              <div>
                <label className="text-xs text-stone-500">Role</label>
                <select
                  value={role}
                  onChange={(e) => setField({ role: e.target.value as TargetRole })}
                  className="mt-1 w-full border border-stone-300 rounded-xl px-3 py-2 text-sm focus:outline-none focus:border-emerald-400"
                >
                  <option value="">Select…</option>
                  {ROLE_OPTIONS.map((r) => (
                    <option key={r.value} value={r.value}>{r.label}</option>
                  ))}
                </select>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

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
      .catch(() => {})
      .finally(() => setLoadingTranscripts(false));
  }, []);

  const setConfig = (i: number, config: TranscriptConfig | null) => {
    setConfigs((prev) => {
      const next = [...prev];
      next[i] = config;
      return next;
    });
  };

  const completedCount = configs.filter((c) => c && c.target_speaker_label && c.target_role && c.target_speaker_name).length;
  const allReady = completedCount === 3;

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
    <div className="max-w-2xl mx-auto space-y-5 py-2">
      <div>
        <h1 className="text-2xl font-bold text-stone-900">Create Baseline Pack</h1>
        <p className="text-sm text-stone-500 mt-1">
          Select 3 past meeting transcripts to build your communication baseline.
        </p>
      </div>

      {/* Progress */}
      <div className="flex items-center gap-2 bg-white rounded-2xl border border-stone-200 px-5 py-3.5">
        <div className="flex gap-1.5">
          {[0, 1, 2].map((i) => (
            <div
              key={i}
              className={`h-1.5 w-8 rounded-full transition-colors ${
                configs[i] && (configs[i]!.target_speaker_label && configs[i]!.target_speaker_name && configs[i]!.target_role)
                  ? 'bg-emerald-500'
                  : 'bg-stone-200'
              }`}
            />
          ))}
        </div>
        <p className="text-xs text-stone-500 ml-1">{completedCount} of 3 meetings configured</p>
      </div>

      {loadingTranscripts ? (
        <div className="flex items-center gap-3 py-4">
          <div className="w-4 h-4 border-2 border-emerald-500 border-t-transparent rounded-full animate-spin" />
          <p className="text-sm text-stone-400">Loading your transcripts…</p>
        </div>
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

      {error && (
        <p className="text-sm text-rose-600 bg-rose-50 rounded-xl px-4 py-3">{error}</p>
      )}

      <button
        onClick={handleSubmit}
        disabled={!allReady || submitting}
        className="w-full py-3.5 bg-emerald-600 text-white rounded-xl font-semibold text-sm hover:bg-emerald-700 disabled:opacity-40 disabled:cursor-not-allowed transition-colors shadow-sm"
      >
        {submitting ? (
          <span className="flex items-center justify-center gap-2">
            <span className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin" />
            Building baseline…
          </span>
        ) : (
          'Build Baseline Pack →'
        )}
      </button>
    </div>
  );
}

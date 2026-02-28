'use client';

import { useState, useRef } from 'react';
import { api } from '@/lib/api';
import { SpeakerChips } from './SpeakerChips';
import type { MeetingType, TargetRole } from '@/lib/types';

interface TranscriptConfig {
  transcript_id: string;
  speaker_labels: string[];
  target_speaker_label: string | null;
  target_speaker_name: string;
  target_role: TargetRole | '';
}

interface TranscriptUploadProps {
  label: string;
  onComplete: (config: TranscriptConfig) => void;
}

const ROLE_OPTIONS: { value: TargetRole; label: string }[] = [
  { value: 'chair', label: 'Chair / Facilitator' },
  { value: 'presenter', label: 'Presenter' },
  { value: 'participant', label: 'Participant' },
  { value: 'manager_1to1', label: '1:1 Manager' },
  { value: 'report_1to1', label: '1:1 Report' },
];

export function TranscriptUploadPanel({ label, onComplete }: TranscriptUploadProps) {
  const [uploading, setUploading] = useState(false);
  const [config, setConfig] = useState<TranscriptConfig | null>(null);
  const [error, setError] = useState<string | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  const handleFile = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    setUploading(true);
    setError(null);
    try {
      const fd = new FormData();
      fd.append('file', file);
      const result = await api.uploadTranscript(fd);
      setConfig({
        transcript_id: result.transcript_id,
        speaker_labels: result.speaker_labels,
        target_speaker_label: result.speaker_labels[0] ?? null,
        target_speaker_name: '',
        target_role: '',
      });
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Upload failed');
    } finally {
      setUploading(false);
    }
  };

  const update = (patch: Partial<TranscriptConfig>) => {
    if (!config) return;
    const next = { ...config, ...patch };
    setConfig(next);
    if (next.target_speaker_label && next.target_role && next.target_speaker_name) {
      onComplete(next);
    }
  };

  return (
    <div className="border border-gray-200 rounded-lg p-4 space-y-3">
      <p className="text-sm font-medium text-gray-700">{label}</p>

      {!config ? (
        <>
          <input
            ref={fileRef}
            type="file"
            accept=".vtt,.srt,.txt,.docx,.pdf"
            className="hidden"
            onChange={handleFile}
          />
          <button
            type="button"
            disabled={uploading}
            onClick={() => fileRef.current?.click()}
            className="w-full border-2 border-dashed border-gray-300 rounded-lg py-8 text-sm text-gray-500 hover:border-indigo-400 hover:text-indigo-600 transition-colors"
          >
            {uploading ? 'Uploading…' : 'Click to upload transcript (.vtt, .srt, .txt)'}
          </button>
          {error && <p className="text-sm text-red-600">{error}</p>}
        </>
      ) : (
        <div className="space-y-3">
          <div>
            <p className="text-xs text-gray-500 mb-1">Select target speaker</p>
            <SpeakerChips
              speakers={config.speaker_labels}
              selected={config.target_speaker_label}
              onSelect={(s) => update({ target_speaker_label: s })}
            />
          </div>
          <div>
            <label className="text-xs text-gray-500">Display name</label>
            <input
              type="text"
              value={config.target_speaker_name}
              onChange={(e) => update({ target_speaker_name: e.target.value })}
              placeholder="e.g. Sarah"
              className="mt-1 w-full border border-gray-300 rounded-md px-3 py-1.5 text-sm"
            />
          </div>
          <div>
            <label className="text-xs text-gray-500">Target role</label>
            <select
              value={config.target_role}
              onChange={(e) => update({ target_role: e.target.value as TargetRole })}
              className="mt-1 w-full border border-gray-300 rounded-md px-3 py-1.5 text-sm"
            >
              <option value="">Select role…</option>
              {ROLE_OPTIONS.map((r) => (
                <option key={r.value} value={r.value}>
                  {r.label}
                </option>
              ))}
            </select>
          </div>
          <p className="text-xs text-green-600">✓ Transcript uploaded</p>
        </div>
      )}
    </div>
  );
}

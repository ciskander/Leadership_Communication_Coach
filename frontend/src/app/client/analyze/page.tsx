'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { api } from '@/lib/api';
import { TranscriptUploadPanel } from '@/components/TranscriptUpload';
import { SpeakerChips } from '@/components/SpeakerChips';
import type { TargetRole } from '@/lib/types';

const ROLE_OPTIONS = [
  { value: 'chair',        label: 'Chair / Facilitator' },
  { value: 'presenter',    label: 'Presenter' },
  { value: 'participant',  label: 'Participant' },
  { value: 'manager_1to1', label: '1:1 Manager' },
  { value: 'report_1to1',  label: '1:1 Report' },
];

export default function AnalyzePage() {
  const router = useRouter();

  // Upload result
  const [transcriptId, setTranscriptId] = useState<string | null>(null);
  const [speakerLabels, setSpeakerLabels] = useState<string[]>([]);

  // Config fields
  const [speakerLabel, setSpeakerLabel] = useState<string | null>(null);
  const [name, setName] = useState('');
  const [role, setRole] = useState<TargetRole | ''>('');

  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleUploaded = ({ transcript_id, speaker_labels }: { transcript_id: string; speaker_labels: string[] }) => {
    setTranscriptId(transcript_id);
    setSpeakerLabels(speaker_labels);
    setSpeakerLabel(speaker_labels[0] ?? null);
    setName('');
    setRole('');
  };

  const ready = transcriptId && speakerLabel && name && role;

  const handleSubmit = async () => {
    if (!ready) return;
    setSubmitting(true);
    setError(null);
    try {
      const result = await api.enqueueSingleMeeting({
        transcript_id: transcriptId,
        target_speaker_name: name,
        target_speaker_label: speakerLabel,
        target_role: role,
      });
      if (result.run_id) {
        router.push(`/client/runs/${result.run_id}`);
      } else {
        pollRunRequest(result.run_request_id);
      }
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Failed to enqueue');
      setSubmitting(false);
    }
  };

  const pollRunRequest = async (rrId: string) => {
    let count = 0;
    const poll = async () => {
      count++;
      try {
        const status = await api.getRunRequest(rrId);
        if (status.run_id) {
          router.push(`/client/runs/${status.run_id}`);
          return;
        }
        if (status.status === 'error') {
          setError('Analysis failed to start.');
          setSubmitting(false);
          return;
        }
        if (count < 30) setTimeout(poll, 2000);
        else {
          setError('Timed out waiting for analysis to start.');
          setSubmitting(false);
        }
      } catch {
        setError('Failed to poll status.');
        setSubmitting(false);
      }
    };
    poll();
  };

  return (
    <div className="max-w-xl mx-auto space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-gray-900">Analyze a Meeting</h1>
        <p className="text-sm text-gray-500 mt-1">
          Upload a transcript to get coaching insights for a specific speaker.
        </p>
      </div>

      <TranscriptUploadPanel onUploaded={handleUploaded} />

      {transcriptId && (
        <div className="border border-gray-200 rounded-lg p-4 space-y-3">
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
            <label className="text-xs text-gray-500">Speaker's full name</label>
            <input
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="e.g. Sarah Johnson"
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
          {speakerLabel && name && role
            ? <p className="text-xs text-green-600">✓ Ready</p>
            : <p className="text-xs text-amber-600">↑ Complete the fields above to continue</p>
          }
        </div>
      )}

      {error && <p className="text-sm text-red-600">{error}</p>}

      <button
        onClick={handleSubmit}
        disabled={!ready || submitting}
        className="w-full py-3 bg-indigo-600 text-white rounded-lg font-medium text-sm hover:bg-indigo-700 disabled:opacity-40 disabled:cursor-not-allowed"
      >
        {submitting ? 'Analyzing…' : 'Analyze Meeting'}
      </button>
    </div>
  );
}
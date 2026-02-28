'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { api } from '@/lib/api';
import { TranscriptUploadPanel } from '@/components/TranscriptUpload';
import type { TargetRole } from '@/lib/types';

interface TranscriptConfig {
  transcript_id: string;
  speaker_labels: string[];
  target_speaker_label: string | null;
  target_speaker_name: string;
  target_role: TargetRole | '';
}

export default function AnalyzePage() {
  const router = useRouter();
  const [config, setConfig] = useState<TranscriptConfig | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async () => {
    if (!config?.target_speaker_label || !config.target_role) return;
    setSubmitting(true);
    setError(null);
    try {
      const result = await api.enqueueSingleMeeting({
        transcript_id: config.transcript_id,
        target_speaker_name: config.target_speaker_name,
        target_speaker_label: config.target_speaker_label,
        target_role: config.target_role,
      });
      // Poll via run_request until run_id is available, then navigate
      const runId = result.run_id;
      if (runId) {
        router.push(`/client/runs/${runId}`);
      } else {
        // Poll run_request
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

  const ready = config?.target_speaker_label && config?.target_role && config?.target_speaker_name;

  return (
    <div className="max-w-xl mx-auto space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-gray-900">Analyze a Meeting</h1>
        <p className="text-sm text-gray-500 mt-1">
          Upload a transcript to get coaching insights for a specific speaker.
        </p>
      </div>

      <TranscriptUploadPanel
        label="Upload transcript"
        onComplete={(c) => setConfig(c as TranscriptConfig)}
      />

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

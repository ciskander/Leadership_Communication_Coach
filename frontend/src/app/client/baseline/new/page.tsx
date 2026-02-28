'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { api } from '@/lib/api';
import { TranscriptUploadPanel } from '@/components/TranscriptUpload';

interface TranscriptConfig {
  transcript_id: string;
  speaker_labels: string[];
  target_speaker_label: string | null;
  target_speaker_name: string;
  target_role: string;
}

export default function BaselineNewPage() {
  const router = useRouter();
  const [configs, setConfigs] = useState<(TranscriptConfig | null)[]>([null, null, null]);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const setConfig = (i: number, config: TranscriptConfig) => {
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
        target_role: first.target_role,
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
          Upload 3 transcripts from past meetings to build your communication baseline.
        </p>
      </div>

      <div className="space-y-4">
        {[0, 1, 2].map((i) => (
          <TranscriptUploadPanel
            key={i}
            label={`Meeting ${i + 1} of 3`}
            onComplete={(config) => setConfig(i, config)}
          />
        ))}
      </div>

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

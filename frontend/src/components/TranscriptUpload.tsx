'use client';

import { useRef, useState } from 'react';
import { api } from '@/lib/api';

interface UploadResult {
  transcript_id: string;
  speaker_labels: string[];
}

interface TranscriptUploadPanelProps {
  onUploaded: (result: UploadResult) => void;
}

export function TranscriptUploadPanel({ onUploaded }: TranscriptUploadPanelProps) {
  const [uploading, setUploading] = useState(false);
  const [uploaded, setUploaded] = useState(false);
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
      setUploaded(true);
      onUploaded({ transcript_id: result.transcript_id, speaker_labels: result.speaker_labels });
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Upload failed');
    } finally {
      setUploading(false);
    }
  };

  return (
    <div>
      <input
        ref={fileRef}
        type="file"
        accept=".vtt,.srt,.txt,.docx,.pdf"
        className="hidden"
        onChange={handleFile}
      />
      <button
        type="button"
        disabled={uploading || uploaded}
        onClick={() => fileRef.current?.click()}
        className="w-full border-2 border-dashed border-gray-300 rounded-lg py-8 text-sm text-gray-500 hover:border-indigo-400 hover:text-indigo-600 transition-colors disabled:opacity-50"
      >
        {uploading ? 'Uploading…' : uploaded ? '✓ File uploaded' : 'Click to upload transcript (.vtt, .srt, .txt, .docx, .pdf)'}
      </button>
      {error && <p className="text-sm text-red-600 mt-1">{error}</p>}
    </div>
  );
}
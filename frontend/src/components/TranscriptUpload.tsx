'use client';

import { useRef, useState } from 'react';
import { api } from '@/lib/api';
import { STRINGS } from '@/config/strings';

const MEETING_TYPE_OPTIONS = [
  'exec_staff',
  'board',
  'all_hands',
  'cross_functional',
  'project_review',
  'sprint_planning',
  'sprint_retrospective',
  'stand_up',
  'incident_review',
  'client_call',
  'one_on_one',
  'other',
];

function isGenericLabel(label: string): boolean {
  return /^SPEAKER_\d+/i.test(label) || /^UNKNOWN$/i.test(label);
}

interface UploadResult {
  transcript_id: string;
  speaker_labels: string[];
  meeting_date?: string | null;
  detected_date?: string | null;
  meeting_type?: string | null;
  title?: string | null;
  speaker_previews?: Record<string, string[]>;
}

interface TranscriptUploadPanelProps {
  onUploaded: (result: UploadResult) => void;
  withMetadata?: boolean;
}

export function TranscriptUploadPanel({ onUploaded, withMetadata = false }: TranscriptUploadPanelProps) {
  const [uploading, setUploading] = useState(false);
  const [uploaded, setUploaded] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);

  const [title, setTitle] = useState('');
  const [meetingType, setMeetingType] = useState('');
  const [meetingTypeCustom, setMeetingTypeCustom] = useState('');
  const [meetingDate, setMeetingDate] = useState('');

  const fileRef = useRef<HTMLInputElement>(null);

  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setSelectedFile(file);
    const nameWithoutExt = file.name.replace(/\.[^/.]+$/, '');
    setTitle(nameWithoutExt);
    if (!withMetadata) {
      doUpload(file, '', '', '');
    }
  };

  const doUpload = async (file: File, titleVal: string, typeVal: string, dateVal: string) => {
    setUploading(true);
    setError(null);
    try {
      const fd = new FormData();
      fd.append('file', file);
      if (titleVal) fd.append('title', titleVal);
      if (typeVal) fd.append('meeting_type', typeVal);
      if (dateVal) fd.append('meeting_date', dateVal);

      const result = await api.uploadTranscript(fd);
      setUploaded(true);
		onUploaded({
		  transcript_id: result.transcript_id,
		  speaker_labels: result.speaker_labels,
		  meeting_date: result.meeting_date,
		  detected_date: result.detected_date ?? null,
		  speaker_previews: result.speaker_previews ?? {},
		  meeting_type: result.meeting_type,
		  title: titleVal || file.name,
		});
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Upload failed');
    } finally {
      setUploading(false);
    }
  };

  const handleUploadClick = () => {
    if (!selectedFile) return;
    const effectiveType = meetingType === '__custom__' ? meetingTypeCustom : meetingType;
    doUpload(selectedFile, title, effectiveType, meetingDate);
  };

  if (!withMetadata) {
    return (
      <div>
        <input ref={fileRef} type="file" accept=".vtt,.srt,.txt,.docx,.pdf" className="hidden" onChange={handleFileSelect} />
        <button
          type="button"
          disabled={uploading || uploaded}
          onClick={() => fileRef.current?.click()}
          className="w-full border-2 border-dashed border-stone-300 rounded-xl py-7 text-sm text-stone-400 hover:border-emerald-400 hover:text-emerald-600 transition-colors disabled:opacity-50"
        >
          {uploading
            ? STRINGS.common.uploading
            : uploaded
            ? STRINGS.transcriptUpload.fileUploaded
            : STRINGS.transcriptUpload.clickToUpload}
        </button>
        {error && <p className="text-sm text-rose-600 mt-1">{error}</p>}
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <input ref={fileRef} type="file" accept=".vtt,.srt,.txt,.docx,.pdf" className="hidden" onChange={handleFileSelect} />

      {!uploaded ? (
        <button
          type="button"
          disabled={uploading}
          onClick={() => fileRef.current?.click()}
          className={`w-full border-2 border-dashed rounded-xl py-6 text-sm transition-colors ${
            selectedFile
              ? 'border-emerald-300 bg-emerald-50 text-emerald-700'
              : 'border-stone-300 text-stone-400 hover:border-emerald-400 hover:text-emerald-600'
          }`}
        >
          {selectedFile ? `📄 ${selectedFile.name}` : STRINGS.transcriptUpload.clickToSelect}
        </button>
      ) : (
        <div className="flex items-center gap-2 bg-emerald-50 border border-emerald-200 rounded-xl px-4 py-3">
          <span className="text-emerald-600">✓</span>
          <span className="text-sm text-emerald-700 font-medium">{STRINGS.transcriptUpload.fileUploadedSuccess}</span>
        </div>
      )}

      {selectedFile && !uploaded && (
        <div className="space-y-3">
          <div>
            <label className="text-xs text-stone-500">{STRINGS.transcriptUpload.meetingTitle}</label>
            <input
              type="text"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder={STRINGS.transcriptUpload.meetingTitlePlaceholder}
              className="mt-1 w-full border border-stone-300 rounded-xl px-3 py-2.5 text-sm focus:outline-none focus:border-emerald-400"
            />
          </div>

          <div>
            <label className="text-xs text-stone-500">{STRINGS.transcriptUpload.meetingType}</label>
            <select
              value={meetingType}
              onChange={(e) => setMeetingType(e.target.value)}
              className="mt-1 w-full border border-stone-300 rounded-xl px-3 py-2.5 text-sm focus:outline-none focus:border-emerald-400"
            >
              <option value="">{STRINGS.transcriptUpload.selectType}</option>
              {MEETING_TYPE_OPTIONS.map((t) => (
                <option key={t} value={t}>{t.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase())}</option>
              ))}
              <option value="__custom__">{STRINGS.transcriptUpload.otherTypeBelow}</option>
            </select>
            {meetingType === '__custom__' && (
              <input
                type="text"
                value={meetingTypeCustom}
                onChange={(e) => setMeetingTypeCustom(e.target.value)}
                placeholder={STRINGS.transcriptUpload.enterMeetingType}
                className="mt-2 w-full border border-stone-300 rounded-xl px-3 py-2.5 text-sm focus:outline-none focus:border-emerald-400"
              />
            )}
          </div>

          <div>
            <label className="text-xs text-stone-500">
              {STRINGS.transcriptUpload.meetingDate}
              <span className="ml-1.5 text-stone-400 font-normal">{STRINGS.transcriptUpload.meetingDateAutodetect}</span>
            </label>
            <input
              type="date"
              value={meetingDate}
              onChange={(e) => setMeetingDate(e.target.value)}
              className="mt-1 w-full border border-stone-300 rounded-xl px-3 py-2.5 text-sm focus:outline-none focus:border-emerald-400"
            />
          </div>

          {error && <p className="text-sm text-rose-600 bg-rose-50 rounded-xl px-3 py-2">{error}</p>}

          <button
            type="button"
            onClick={handleUploadClick}
            disabled={uploading}
            className="w-full py-2.5 bg-emerald-600 text-white rounded-xl text-sm font-semibold hover:bg-emerald-700 disabled:opacity-50 transition-colors"
          >
            {uploading ? STRINGS.common.uploading : STRINGS.transcriptUpload.uploadTranscript}
          </button>
        </div>
      )}
    </div>
  );
}

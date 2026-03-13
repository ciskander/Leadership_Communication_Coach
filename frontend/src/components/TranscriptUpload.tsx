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

// ─── Shared input class (matches analyze page) ────────────────────────────────
const inputCls =
  'mt-1 w-full border border-cv-warm-300 rounded-xl px-3 py-2.5 text-sm text-cv-stone-800 bg-white focus:outline-none focus:border-cv-teal-400 focus:ring-1 focus:ring-cv-teal-400/30 transition-colors placeholder:text-cv-stone-400';

// ─── Field label ──────────────────────────────────────────────────────────────
function FieldLabel({ text, suffix }: { text: string; suffix?: React.ReactNode }) {
  return (
    <label className="flex items-center gap-1.5 text-2xs font-semibold uppercase tracking-[0.12em] text-cv-stone-400">
      {text}
      {suffix && <span className="font-normal normal-case tracking-normal text-cv-stone-400">{suffix}</span>}
    </label>
  );
}

// ─── Upload drop zone ─────────────────────────────────────────────────────────
function DropZone({
  uploading,
  uploaded,
  selectedFile,
  onClick,
}: {
  uploading: boolean;
  uploaded: boolean;
  selectedFile: File | null;
  onClick: () => void;
}) {
  if (uploaded) {
    return (
      <div className="flex items-center gap-2.5 bg-cv-teal-50 border border-cv-teal-200 rounded-xl px-4 py-3">
        <svg viewBox="0 0 20 20" fill="currentColor" className="w-4 h-4 text-cv-teal-600 shrink-0" aria-hidden="true">
          <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.857-9.809a.75.75 0 00-1.214-.882l-3.483 4.79-1.88-1.88a.75.75 0 10-1.06 1.061l2.5 2.5a.75.75 0 001.137-.089l4-5.5z" clipRule="evenodd" />
        </svg>
        <span className="text-sm text-cv-teal-700 font-medium">{STRINGS.transcriptUpload.fileUploadedSuccess}</span>
      </div>
    );
  }

  return (
    <button
      type="button"
      disabled={uploading}
      onClick={onClick}
      className={[
        'w-full border-2 border-dashed rounded-xl transition-colors disabled:opacity-50',
        selectedFile
          ? 'border-cv-teal-300 bg-cv-teal-50 py-4'
          : 'border-cv-warm-300 py-7 hover:border-cv-teal-400',
      ].join(' ')}
    >
      {uploading ? (
        <span className="flex items-center justify-center gap-2 text-sm text-cv-stone-500">
          <span className="w-4 h-4 border-2 border-cv-teal-400 border-t-transparent rounded-full animate-spin" />
          {STRINGS.common.uploading}
        </span>
      ) : selectedFile ? (
        <span className="flex items-center justify-center gap-2 text-sm text-cv-teal-700">
          {/* Document icon */}
          <svg viewBox="0 0 20 20" fill="currentColor" className="w-4 h-4 shrink-0 text-cv-teal-500" aria-hidden="true">
            <path d="M3 3.5A1.5 1.5 0 014.5 2h6.879a1.5 1.5 0 011.06.44l2.122 2.12a1.5 1.5 0 01.439 1.061V16.5A1.5 1.5 0 0113.5 18h-9A1.5 1.5 0 013 16.5v-13z" />
          </svg>
          <span className="font-medium truncate max-w-xs">{selectedFile.name}</span>
        </span>
      ) : (
        <span className="flex flex-col items-center gap-1.5">
          {/* Upload cloud icon */}
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.5} strokeLinecap="round" strokeLinejoin="round" className="w-6 h-6 text-cv-stone-400" aria-hidden="true">
            <path d="M12 16V8m0 0l-3 3m3-3l3 3" />
            <path d="M20.39 18.39A5 5 0 0018 9h-1.26A8 8 0 103 16.3" />
          </svg>
          <span className="text-sm text-cv-stone-400">{STRINGS.transcriptUpload.clickToSelect}</span>
        </span>
      )}
    </button>
  );
}

// ─── Main component ───────────────────────────────────────────────────────────

export function TranscriptUploadPanel({ onUploaded, withMetadata = false }: TranscriptUploadPanelProps) {
  const [uploading, setUploading]                 = useState(false);
  const [uploaded, setUploaded]                   = useState(false);
  const [error, setError]                         = useState<string | null>(null);
  const [selectedFile, setSelectedFile]           = useState<File | null>(null);

  const [title, setTitle]                         = useState('');
  const [meetingType, setMeetingType]             = useState('');
  const [meetingTypeCustom, setMeetingTypeCustom] = useState('');
  const [meetingDate, setMeetingDate]             = useState('');

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
      if (typeVal)  fd.append('meeting_type', typeVal);
      if (dateVal)  fd.append('meeting_date', dateVal);

      const result = await api.uploadTranscript(fd);
      setUploaded(true);
      onUploaded({
        transcript_id:   result.transcript_id,
        speaker_labels:  result.speaker_labels,
        meeting_date:    result.meeting_date,
        detected_date:   result.detected_date ?? null,
        speaker_previews: result.speaker_previews ?? {},
        meeting_type:    result.meeting_type,
        title:           titleVal || file.name,
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

  // ── Simple variant (no metadata) ──────────────────────────────────────────
  if (!withMetadata) {
    return (
      <div>
        <input
          ref={fileRef}
          type="file"
          accept=".vtt,.srt,.txt,.docx,.pdf"
          className="hidden"
          onChange={handleFileSelect}
        />
        <DropZone
          uploading={uploading}
          uploaded={uploaded}
          selectedFile={selectedFile}
          onClick={() => fileRef.current?.click()}
        />
        {error && (
          <p className="text-xs text-cv-red-600 bg-cv-red-50 border border-cv-red-200 rounded-xl px-3 py-2 mt-2">
            {error}
          </p>
        )}
      </div>
    );
  }

  // ── Full variant (with metadata fields) ───────────────────────────────────
  return (
    <div className="space-y-4">
      <input
        ref={fileRef}
        type="file"
        accept=".vtt,.srt,.txt,.docx,.pdf"
        className="hidden"
        onChange={handleFileSelect}
      />

      <DropZone
        uploading={uploading}
        uploaded={uploaded}
        selectedFile={selectedFile}
        onClick={() => fileRef.current?.click()}
      />

      {selectedFile && !uploaded && (
        <div className="space-y-3">
          {/* Meeting title */}
          <div>
            <FieldLabel text={STRINGS.transcriptUpload.meetingTitle} />
            <input
              type="text"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder={STRINGS.transcriptUpload.meetingTitlePlaceholder}
              className={inputCls}
            />
          </div>

          {/* Meeting type */}
          <div>
            <FieldLabel text={STRINGS.transcriptUpload.meetingType} />
            <select
              value={meetingType}
              onChange={(e) => setMeetingType(e.target.value)}
              className={inputCls}
            >
              <option value="">{STRINGS.transcriptUpload.selectType}</option>
              {MEETING_TYPE_OPTIONS.map((t) => (
                <option key={t} value={t}>
                  {t.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase())}
                </option>
              ))}
              <option value="__custom__">{STRINGS.transcriptUpload.otherTypeBelow}</option>
            </select>
            {meetingType === '__custom__' && (
              <input
                type="text"
                value={meetingTypeCustom}
                onChange={(e) => setMeetingTypeCustom(e.target.value)}
                placeholder={STRINGS.transcriptUpload.enterMeetingType}
                className={`${inputCls} mt-2`}
              />
            )}
          </div>

          {/* Meeting date */}
          <div>
            <FieldLabel
              text={STRINGS.transcriptUpload.meetingDate}
              suffix={STRINGS.transcriptUpload.meetingDateAutodetect}
            />
            <input
              type="date"
              value={meetingDate}
              onChange={(e) => setMeetingDate(e.target.value)}
              className={inputCls}
            />
          </div>

          {/* Error */}
          {error && (
            <p className="text-xs text-cv-red-600 bg-cv-red-50 border border-cv-red-200 rounded-xl px-3 py-2">
              {error}
            </p>
          )}

          {/* Upload button */}
          <button
            type="button"
            onClick={handleUploadClick}
            disabled={uploading}
            className="w-full py-2.5 bg-cv-teal-600 text-white rounded-xl text-sm font-semibold hover:bg-cv-teal-700 disabled:opacity-50 transition-colors"
          >
            {uploading ? (
              <span className="flex items-center justify-center gap-2">
                <span className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin" />
                {STRINGS.common.uploading}
              </span>
            ) : (
              STRINGS.transcriptUpload.uploadTranscript
            )}
          </button>
        </div>
      )}
    </div>
  );
}

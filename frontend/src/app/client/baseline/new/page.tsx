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
  target_role: TargetRole | '';
  meeting_date: string | null;
}

const ROLE_OPTIONS = [
  { value: 'chair',        label: 'Chair / Facilitator' },
  { value: 'presenter',    label: 'Presenter' },
  { value: 'participant',  label: 'Participant' },
  { value: 'manager_1to1', label: '1:1 Manager' },
  { value: 'report_1to1',  label: '1:1 Report' },
];

function getFirstName(displayName: string): string {
  return displayName.trim().split(/\s+/)[0].toLowerCase();
}

function matchSpeakerByFirstName(speakers: string[], firstName: string): string | null {
  const lower = firstName.toLowerCase();
  return speakers.find((s) => s.toLowerCase().startsWith(lower)) ?? null;
}

function isGenericLabel(label: string): boolean {
  return /^SPEAKER_\d+/i.test(label) || /^UNKNOWN$/i.test(label);
}

function TranscriptSlot({
  index,
  existingTranscripts,
  currentUserName,
  onComplete,
}: {
  index: number;
  existingTranscripts: TranscriptListItem[];
  currentUserName: string;
  onComplete: (config: TranscriptConfig | null) => void;
}) {
  const [mode, setMode] = useState<'select' | 'upload'>(
    existingTranscripts.length > 0 ? 'select' : 'upload'
  );
  const [transcriptId, setTranscriptId] = useState<string | null>(null);
  const [speakerLabels, setSpeakerLabels] = useState<string[]>([]);
  const [speakerPreviews, setSpeakerPreviews] = useState<Record<string, string[]>>({});
  const [needsSpeakerPick, setNeedsSpeakerPick] = useState(false);
  const [speakerLabel, setSpeakerLabel] = useState<string | null>(null);
  const [role, setRole] = useState<TargetRole | ''>('');
  const [meetingDate, setMeetingDate] = useState<string | null>(null);

  const notify = (tid: string | null, sl: string | null, r: TargetRole | '', labels: string[], date: string | null) => {
    if (tid && sl && r) {
      onComplete({ transcript_id: tid, speaker_labels: labels, target_speaker_label: sl, target_role: r, meeting_date: date });
    } else {
      onComplete(null);
    }
  };

  const applyTranscript = (tid: string, labels: string[], previews: Record<string, string[]> = {}, date: string | null = null) => {
    setTranscriptId(tid);
    setSpeakerLabels(labels);
    setSpeakerPreviews(previews);
    setMeetingDate(date);

    const allGeneric = labels.every(isGenericLabel);
    const firstName = currentUserName ? getFirstName(currentUserName) : '';
    const matched = !allGeneric && firstName ? matchSpeakerByFirstName(labels, firstName) : null;

    if (matched) {
      setSpeakerLabel(matched);
      setNeedsSpeakerPick(false);
      notify(tid, matched, role, labels, date);
    } else if (allGeneric && labels.length > 1) {
      setSpeakerLabel(null);
      setNeedsSpeakerPick(true);
      notify(tid, null, role, labels, date);
    } else {
      const first = labels[0] ?? null;
      setSpeakerLabel(first);
      setNeedsSpeakerPick(false);
      notify(tid, first, role, labels, date);
    }

    setRole('');
  };

  const switchMode = (next: 'select' | 'upload') => {
    setMode(next);
    setTranscriptId(null);
    setSpeakerLabels([]);
    setSpeakerPreviews({});
    setSpeakerLabel(null);
    setNeedsSpeakerPick(false);
    setRole('');
    setMeetingDate(null);
    onComplete(null);
  };

  const pickSpeaker = (label: string) => {
    setSpeakerLabel(label);
    setNeedsSpeakerPick(false);
    notify(transcriptId, label, role, speakerLabels, meetingDate);
  };

  const setRoleField = (r: TargetRole | '') => {
    setRole(r);
    notify(transcriptId, speakerLabel, r, speakerLabels, meetingDate);
  };

  const setDateField = (d: string) => {
    const date = d || null;
    setMeetingDate(date);
    notify(transcriptId, speakerLabel, role, speakerLabels, date);
  };

  const isComplete = !!(transcriptId && speakerLabel && role);

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
            withMetadata={true}
            onUploaded={({ transcript_id, speaker_labels, speaker_previews = {}, meeting_date, detected_date }) =>
              applyTranscript(transcript_id, speaker_labels, speaker_previews, meeting_date || detected_date || null)
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
                    onChange={() => applyTranscript(t.transcript_id, t.speaker_labels, {}, t.meeting_date || null)}
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
            {needsSpeakerPick ? (
              <div className="space-y-2">
                <p className="text-xs text-stone-500 font-medium">Which speaker are you?</p>
                <div className="grid grid-cols-1 gap-2">
                  {speakerLabels.map((label) => {
                    const quotes = speakerPreviews[label] ?? [];
                    return (
                      <button
                        key={label}
                        onClick={() => pickSpeaker(label)}
                        className={`text-left p-3.5 rounded-xl border transition-colors ${
                          speakerLabel === label
                            ? 'border-emerald-500 bg-emerald-50'
                            : 'border-stone-200 bg-white hover:border-stone-300'
                        }`}
                      >
                        <p className="text-xs font-semibold text-stone-500 uppercase tracking-widest mb-1.5">
                          {label}
                        </p>
                        {quotes.map((q, i) => (
                          <p key={i} className="text-sm text-stone-600 leading-snug">"{q}"</p>
                        ))}
                      </button>
                    );
                  })}
                </div>
              </div>
            ) : speakerLabels.length > 0 ? (
              <div>
                <p className="text-xs text-stone-500 mb-2">Your speaker label in this transcript</p>
                <SpeakerChips
                  speakers={speakerLabels}
                  selected={speakerLabel}
                  onSelect={(s) => {
                    setSpeakerLabel(s);
                    notify(transcriptId, s, role, speakerLabels);
                  }}
                />
              </div>
            ) : (
              <div>
                <label className="text-xs text-stone-500">Speaker label</label>
                <input
                  type="text"
                  value={speakerLabel ?? ''}
                  onChange={(e) => {
                    const s = e.target.value || null;
                    setSpeakerLabel(s);
                    notify(transcriptId, s, role, speakerLabels);
                  }}
                  placeholder="e.g. SPEAKER_00"
                  className="mt-1 w-full border border-stone-300 rounded-xl px-3 py-2 text-sm focus:outline-none focus:border-emerald-400"
                />
              </div>
            )}

            <div>
              <label className="text-xs text-stone-500">Meeting date</label>
              <input
                type="date"
                value={meetingDate ?? ''}
                onChange={(e) => setDateField(e.target.value)}
                className="mt-1 w-full border border-stone-300 rounded-xl px-3 py-2 text-sm focus:outline-none focus:border-emerald-400"
              />
              {!meetingDate && (
                <p className="text-xs text-amber-600 mt-1">
                  ⚠ No date set — required for correct ordering in your progress chart.
                </p>
              )}
            </div>

            <div>
              <label className="text-xs text-stone-500">Your role in this meeting</label>
              <select
                value={role}
                onChange={(e) => setRoleField(e.target.value as TargetRole)}
                className="mt-1 w-full border border-stone-300 rounded-xl px-3 py-2 text-sm focus:outline-none focus:border-emerald-400"
              >
                <option value="">Select…</option>
                {ROLE_OPTIONS.map((r) => (
                  <option key={r.value} value={r.value}>{r.label}</option>
                ))}
              </select>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

export default function BaselineNewPage() {
  const router = useRouter();
  const [currentUserName, setCurrentUserName] = useState('');
  const [speakerName, setSpeakerName] = useState('');
  const [existingTranscripts, setExistingTranscripts] = useState<TranscriptListItem[]>([]);
  const [loadingTranscripts, setLoadingTranscripts] = useState(true);
  const [configs, setConfigs] = useState<(TranscriptConfig | null)[]>([null, null, null]);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.me().then((user) => {
      if (user.display_name) {
        setCurrentUserName(user.display_name);
        setSpeakerName(user.display_name);
      }
    }).catch(() => {});

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

  const completedCount = configs.filter(
    (c) => c && c.target_speaker_label && c.target_role
  ).length;
  const allReady = completedCount === 3 && !!speakerName.trim();

  const handleSubmit = async () => {
    if (!allReady) return;
    setSubmitting(true);
    setError(null);
    try {
      // Update meeting dates on transcript records before building.
      // This ensures the baseline_pack's Last Meeting Date rollup is correct,
      // which is used as the anchor point on the progress chart.
      await Promise.all(
        configs
          .filter((c): c is TranscriptConfig => !!c && !!c.meeting_date)
          .map((c) => api.updateTranscriptDate(c.transcript_id, c.meeting_date))
      );

      const first = configs[0]!;
      const created = await api.createBaselinePack({
        transcript_ids: configs.map((c) => c!.transcript_id),
        target_speaker_name: speakerName.trim(),
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

      {/* Speaker name — single field for all 3 transcripts */}
      <div className="bg-white rounded-2xl border border-stone-200 p-5">
        <label className="text-xs font-semibold text-stone-400 uppercase tracking-widest">
          Your full name
        </label>
        <p className="text-xs text-stone-400 mt-0.5 mb-2">
          Used to identify you across all three transcripts.
        </p>
        <input
          type="text"
          value={speakerName}
          onChange={(e) => setSpeakerName(e.target.value)}
          placeholder="e.g. Sarah Johnson"
          className="w-full border border-stone-300 rounded-xl px-3 py-2.5 text-sm focus:outline-none focus:border-emerald-400"
        />
      </div>

      {/* Progress */}
      <div className="flex items-center gap-2 bg-white rounded-2xl border border-stone-200 px-5 py-3.5">
        <div className="flex gap-1.5">
          {[0, 1, 2].map((i) => (
            <div
              key={i}
              className={`h-1.5 w-8 rounded-full transition-colors ${
                configs[i] && configs[i]!.target_speaker_label && configs[i]!.target_role
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
              currentUserName={currentUserName}
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

'use client';

import { useState, useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { api } from '@/lib/api';
import { TranscriptUploadPanel } from '@/components/TranscriptUpload';
import { SpeakerChips } from '@/components/SpeakerChips';
import type { TranscriptListItem, TargetRole } from '@/lib/types';
import { STRINGS } from '@/config/strings';
import { OnboardingTip } from '@/components/OnboardingTip';

// ─── Types ────────────────────────────────────────────────────────────────────

interface TranscriptConfig {
  transcript_id: string;
  speaker_labels: string[];
  target_speaker_label: string | null;
  target_role: TargetRole | '';
  meeting_date: string | null;
}

const ROLE_OPTIONS = STRINGS.roleOptions;

// ─── Helpers (unchanged) ──────────────────────────────────────────────────────

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

// ─── TranscriptSlot ───────────────────────────────────────────────────────────

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

  // All logic functions are identical to original — only class names change below
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
    <div className={`bg-white rounded border transition-colors overflow-hidden ${
      isComplete ? 'border-cv-teal-200' : 'border-cv-warm-200'
    }`}>

      {/* Slot header */}
      <div className={`flex items-center justify-between px-5 py-3.5 border-b ${
        isComplete
          ? 'bg-cv-teal-50 border-cv-teal-100'
          : 'bg-cv-warm border-cv-warm-200'
      }`}>
        <div className="flex items-center gap-2.5">
          <div className={`w-6 h-6 rounded-full flex items-center justify-center text-xs font-medium ${
            isComplete
              ? 'bg-cv-teal-600 text-cv-teal-50'
              : 'bg-cv-stone-100 text-cv-stone-600'
          }`}>
            {isComplete ? '✓' : index + 1}
          </div>
          <p className="text-sm font-medium text-cv-stone-900">
            {STRINGS.baselineNew.meetingN(index + 1)}
          </p>
        </div>

        {/* Mode toggle */}
        <div className="flex gap-0.5 bg-white rounded p-0.5 border border-cv-warm-200">
          {(['select', 'upload'] as const).map((m) => (
            <button
              key={m}
              onClick={() => switchMode(m)}
              className={`px-3 py-1 rounded text-xs font-medium transition-colors ${
                mode === m
                  ? 'bg-cv-stone-900 text-white'
                  : 'text-cv-stone-400 hover:text-cv-stone-600'
              }`}
            >
              {m === 'select' ? STRINGS.baselineNew.existing : STRINGS.baselineNew.uploadNew}
            </button>
          ))}
        </div>
      </div>

      {/* Slot content */}
      <div className="px-5 py-4 space-y-4">

        {/* Upload mode */}
        {mode === 'upload' && (
          <TranscriptUploadPanel
            withMetadata={true}
            onUploaded={({ transcript_id, speaker_labels, speaker_previews = {}, meeting_date, detected_date }) =>
              applyTranscript(transcript_id, speaker_labels, speaker_previews, meeting_date || detected_date || null)
            }
          />
        )}

        {/* Select mode */}
        {mode === 'select' && (
          <div className="max-h-44 overflow-y-auto rounded border border-cv-warm-200 divide-y divide-cv-warm-200">
            {existingTranscripts.length === 0 ? (
              <p className="text-xs text-cv-stone-400 text-center py-6">
                {STRINGS.baselineNew.noTranscripts}{' '}
                <button
                  className="text-cv-teal-600 underline"
                  onClick={() => switchMode('upload')}
                >
                  {STRINGS.baselineNew.uploadOne}
                </button>
              </p>
            ) : (
              existingTranscripts.map((t) => (
                <label
                  key={t.transcript_id}
                  className={`flex items-start gap-3 px-3 py-2.5 cursor-pointer hover:bg-cv-warm transition-colors ${
                    transcriptId === t.transcript_id ? 'bg-cv-teal-50' : ''
                  }`}
                >
                  <input
                    type="radio"
                    name={`slot-${index}`}
                    value={t.transcript_id}
                    checked={transcriptId === t.transcript_id}
                    onChange={() => applyTranscript(t.transcript_id, t.speaker_labels, {}, t.meeting_date || null)}
                    className="mt-0.5 accent-cv-teal-600"
                  />
                  <div className="min-w-0">
                    <p className="text-sm text-cv-stone-900 truncate font-medium">
                      {t.title || STRINGS.common.untitled}
                    </p>
                    <p className="text-xs text-cv-stone-400">
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
          <div className="space-y-3 pt-1 border-t border-cv-warm-200">

            {/* Speaker pick: generic labels need manual selection */}
            {needsSpeakerPick ? (
              <div className="space-y-2">
                <p className="text-xs text-cv-stone-600 font-medium">
                  {STRINGS.analyzePage.whichSpeaker}
                </p>
                <div className="grid grid-cols-1 gap-2">
                  {speakerLabels.map((label) => {
                    const quotes = speakerPreviews[label] ?? [];
                    return (
                      <button
                        key={label}
                        onClick={() => pickSpeaker(label)}
                        className={`text-left p-3.5 rounded border transition-colors ${
                          speakerLabel === label
                            ? 'border-cv-teal-400 bg-cv-teal-50'
                            : 'border-cv-warm-200 bg-white hover:border-cv-stone-100'
                        }`}
                      >
                        <p className="text-2xs font-medium text-cv-stone-400 uppercase tracking-widest mb-1.5">
                          {label}
                        </p>
                        {quotes.map((q, i) => (
                          <p key={i} className="text-sm text-cv-stone-600 leading-snug italic">"{q}"</p>
                        ))}
                      </button>
                    );
                  })}
                </div>
              </div>
            ) : speakerLabels.length > 0 ? (
              <div>
                <p className="text-xs text-cv-stone-400 mb-2">
                  {STRINGS.baselineNew.yourSpeakerLabel}
                </p>
                <SpeakerChips
                  speakers={speakerLabels}
                  selected={speakerLabel}
                  onSelect={(s) => {
                    setSpeakerLabel(s);
                    notify(transcriptId, s, role, speakerLabels, meetingDate);
                  }}
                />
              </div>
            ) : (
              <div>
                <label className="text-xs text-cv-stone-400">
                  {STRINGS.analyzePage.speakerLabel}
                </label>
                <input
                  type="text"
                  value={speakerLabel ?? ''}
                  onChange={(e) => {
                    const s = e.target.value || null;
                    setSpeakerLabel(s);
                    notify(transcriptId, s, role, speakerLabels, meetingDate);
                  }}
                  placeholder={STRINGS.analyzePage.speakerLabelPlaceholder}
                  className="mt-1 w-full border border-cv-warm-200 rounded px-3 py-2 text-sm focus:outline-none focus:border-cv-teal-400 bg-white"
                />
              </div>
            )}

            {/* Meeting date */}
            <div>
              <label className="text-xs text-cv-stone-400">
                {STRINGS.transcriptUpload.meetingDate}
              </label>
              <input
                type="date"
                value={meetingDate ?? ''}
                onChange={(e) => setDateField(e.target.value)}
                className="mt-1 w-full border border-cv-warm-200 rounded px-3 py-2 text-sm focus:outline-none focus:border-cv-teal-400 bg-white"
              />
              {!meetingDate && (
                <p className="text-xs text-cv-amber-600 mt-1">
                  {STRINGS.baselineNew.noDateWarning}
                </p>
              )}
            </div>

            {/* Role select */}
            <div>
              <label className="text-xs text-cv-stone-400">
                {STRINGS.baselineNew.yourRole}
              </label>
              <select
                value={role}
                onChange={(e) => setRoleField(e.target.value as TargetRole)}
                className="mt-1 w-full border border-cv-warm-200 rounded px-3 py-2 text-sm focus:outline-none focus:border-cv-teal-400 bg-white text-cv-stone-900"
              >
                <option value="">{STRINGS.baselineNew.selectPlaceholder}</option>
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

// ─── BaselineNewPage ──────────────────────────────────────────────────────────

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

  // Unchanged submit logic
  const handleSubmit = async () => {
    if (!allReady) return;
    setSubmitting(true);
    setError(null);
    try {
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

      <OnboardingTip tipId="baseline-new" message={STRINGS.onboarding.tipBaselineNew} />

      {/* Page heading */}
      <div>
        <h1 className="font-serif text-2xl text-cv-stone-900">
          {STRINGS.baselineNew.heading}
        </h1>
        <p className="text-sm text-cv-stone-400 font-light mt-1">
          {STRINGS.baselineNew.subtitle}
        </p>
      </div>

      {/* Speaker name */}
      <div className="bg-white rounded border border-cv-warm-200 p-5">
        <label className="text-2xs font-medium text-cv-stone-400 uppercase tracking-widest">
          {STRINGS.baselineNew.yourFullName}
        </label>
        <p className="text-xs text-cv-stone-400 font-light mt-0.5 mb-3">
          {STRINGS.baselineNew.nameHint}
        </p>
        <input
          type="text"
          value={speakerName}
          onChange={(e) => setSpeakerName(e.target.value)}
          placeholder={STRINGS.baselineNew.namePlaceholder}
          className="w-full border border-cv-warm-200 rounded px-3 py-2.5 text-sm focus:outline-none focus:border-cv-teal-400 bg-white text-cv-stone-900"
        />
      </div>

      {/* Progress indicator */}
      <div className="flex items-center gap-3 bg-white rounded border border-cv-warm-200 px-5 py-3.5">
        <div className="flex gap-1.5">
          {[0, 1, 2].map((i) => (
            <div
              key={i}
              className={`h-1 w-10 rounded-full transition-colors ${
                configs[i] && configs[i]!.target_speaker_label && configs[i]!.target_role
                  ? 'bg-cv-teal-400'
                  : 'bg-cv-stone-100'
              }`}
            />
          ))}
        </div>
        <p className="text-xs text-cv-stone-400 font-light">
          {STRINGS.baselineNew.meetingsConfigured(completedCount)}
        </p>
      </div>

      {/* Transcript slots */}
      {loadingTranscripts ? (
        <div className="flex items-center gap-3 py-4">
          <div className="w-4 h-4 border-2 border-cv-teal-400 border-t-transparent rounded-full animate-spin" />
          <p className="text-sm text-cv-stone-400 font-light">
            {STRINGS.baselineNew.loadingTranscripts}
          </p>
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

      {/* Error */}
      {error && (
        <p className="text-sm text-cv-red-600 bg-cv-red-100/40 rounded px-4 py-3">
          {error}
        </p>
      )}

      {/* Submit */}
      <button
        onClick={handleSubmit}
        disabled={!allReady || submitting}
        className="w-full py-3.5 bg-cv-teal-600 text-cv-teal-50 rounded font-medium text-sm hover:bg-cv-teal-800 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
      >
        {submitting ? (
          <span className="flex items-center justify-center gap-2">
            <span className="w-4 h-4 border-2 border-cv-teal-100 border-t-transparent rounded-full animate-spin" />
            {STRINGS.baselineNew.buildingBaseline}
          </span>
        ) : (
          STRINGS.baselineNew.buildBaselineBtn
        )}
      </button>

    </div>
  );
}

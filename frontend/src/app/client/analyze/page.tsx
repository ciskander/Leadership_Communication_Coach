'use client';

import { useState, useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { api } from '@/lib/api';
import { STRINGS } from '@/config/strings';
import { OnboardingTip } from '@/components/OnboardingTip';
import { TranscriptUploadPanel } from '@/components/TranscriptUpload';
import { SpeakerChips } from '@/components/SpeakerChips';
import type { TargetRole } from '@/lib/types';

const ROLE_OPTIONS = STRINGS.roleOptions;

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

export default function AnalyzePage() {
  const router = useRouter();
  const [currentUserName, setCurrentUserName] = useState('');
  const [transcriptId, setTranscriptId] = useState<string | null>(null);
  const [speakerLabels, setSpeakerLabels] = useState<string[]>([]);
  const [speakerLabel, setSpeakerLabel] = useState<string | null>(null);
  const [name, setName] = useState('');
  const [role, setRole] = useState<TargetRole | ''>('');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [speakerPreviews, setSpeakerPreviews] = useState<Record<string, string[]>>({});
  const [needsSpeakerPick, setNeedsSpeakerPick] = useState(false);

  useEffect(() => {
    api.me().then((user) => {
      if (user.display_name) setCurrentUserName(user.display_name);
    }).catch(() => {});
  }, []);

	const handleUploaded = ({
	  transcript_id,
	  speaker_labels,
	  speaker_previews = {},
	}: {
	  transcript_id: string;
	  speaker_labels: string[];
	  speaker_previews?: Record<string, string[]>;
	  meeting_date?: string | null;
	  detected_date?: string | null;
	}) => {
	  setTranscriptId(transcript_id);
	  setSpeakerLabels(speaker_labels);
	  setSpeakerPreviews(speaker_previews);

	  const allGeneric = speaker_labels.every(isGenericLabel);
	  const firstName = currentUserName ? getFirstName(currentUserName) : '';
	  const matched = !allGeneric && firstName
		? matchSpeakerByFirstName(speaker_labels, firstName)
		: null;

	  if (matched) {
		setSpeakerLabel(matched);
		setNeedsSpeakerPick(false);
	  } else if (allGeneric && speaker_labels.length > 1) {
		setSpeakerLabel(null);
		setNeedsSpeakerPick(true);
	  } else {
		setSpeakerLabel(speaker_labels[0] ?? null);
		setNeedsSpeakerPick(false);
	  }

	  setName(currentUserName || '');
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
      setError(e instanceof Error ? e.message : STRINGS.analyzePage.failedToEnqueue);
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
          setError(STRINGS.analyzePage.analysisFailedToStart);
          setSubmitting(false);
          return;
        }
        if (count < 30) setTimeout(poll, 2000);
        else {
          setError(STRINGS.analyzePage.timedOutWaiting);
          setSubmitting(false);
        }
      } catch {
        setError(STRINGS.analyzePage.failedToPollStatus);
        setSubmitting(false);
      }
    };
    poll();
  };

  const step = !transcriptId ? 1 : !speakerLabel || !name || !role ? 2 : 3;

  return (
    <div className="max-w-xl mx-auto space-y-5 py-2">
      <OnboardingTip tipId="analyze" message={STRINGS.onboarding.tipAnalyze} />
      <div>
        <h1 className="text-2xl font-bold text-stone-900">{STRINGS.analyzePage.heading}</h1>
        <p className="text-sm text-stone-500 mt-1">
          {STRINGS.analyzePage.subtitle}
        </p>
      </div>

      <div className="bg-white rounded-2xl border border-stone-200 p-5 space-y-3">
        <div className="flex items-center gap-2.5">
          <div className={`w-6 h-6 rounded-full flex items-center justify-center text-xs font-bold ${
            step > 1 ? 'bg-emerald-600 text-white' : 'bg-stone-900 text-white'
          }`}>
            {step > 1 ? '✓' : '1'}
          </div>
          <p className="text-sm font-semibold text-stone-800">{STRINGS.analyzePage.step1}</p>
        </div>
        <TranscriptUploadPanel onUploaded={handleUploaded} withMetadata={true} />
      </div>

      {transcriptId && (
        <div className="bg-white rounded-2xl border border-stone-200 p-5 space-y-4">
          <div className="flex items-center gap-2.5">
            <div className={`w-6 h-6 rounded-full flex items-center justify-center text-xs font-bold ${
              step > 2 ? 'bg-emerald-600 text-white' : 'bg-stone-900 text-white'
            }`}>
              {step > 2 ? '✓' : '2'}
            </div>
            <p className="text-sm font-semibold text-stone-800">{STRINGS.analyzePage.step2}</p>
          </div>

          {needsSpeakerPick ? (
			  <div className="space-y-3">
				<p className="text-xs text-stone-500 font-medium">{STRINGS.analyzePage.whichSpeaker}</p>
				<div className="grid grid-cols-1 gap-2">
				  {speakerLabels.map((label) => {
					const quotes = speakerPreviews[label] ?? [];
					return (
					  <button
						key={label}
						onClick={() => { setSpeakerLabel(label); setNeedsSpeakerPick(false); }}
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
						  <p key={i} className="text-sm text-stone-600 leading-snug">
							"{q}"
						  </p>
						))}
					  </button>
					);
				  })}
				</div>
			  </div>
			) : speakerLabels.length > 0 ? (
			  <div>
				<p className="text-xs text-stone-500 mb-2">{STRINGS.analyzePage.whoAreWeAnalysing}</p>
				<SpeakerChips
				  speakers={speakerLabels}
				  selected={speakerLabel}
				  onSelect={setSpeakerLabel}
				/>
			  </div>
			) : (
			  <div>
				<label className="text-xs text-stone-500">{STRINGS.analyzePage.speakerLabel}</label>
				<input
				  type="text"
				  value={speakerLabel ?? ''}
				  onChange={(e) => setSpeakerLabel(e.target.value || null)}
				  placeholder={STRINGS.analyzePage.speakerLabelPlaceholder}
				  className="mt-1 w-full border border-stone-300 rounded-xl px-3 py-2.5 text-sm focus:outline-none focus:border-emerald-400"
				/>
			  </div>
		    )}

          <div>
            <label className="text-xs text-stone-500">{STRINGS.analyzePage.fullName}</label>
            <input
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder={STRINGS.analyzePage.fullNamePlaceholder}
              className="mt-1 w-full border border-stone-300 rounded-xl px-3 py-2.5 text-sm focus:outline-none focus:border-emerald-400"
            />
          </div>

          <div>
            <label className="text-xs text-stone-500">{STRINGS.analyzePage.roleInMeeting}</label>
            <select
              value={role}
              onChange={(e) => setRole(e.target.value as TargetRole)}
              className="mt-1 w-full border border-stone-300 rounded-xl px-3 py-2.5 text-sm focus:outline-none focus:border-emerald-400"
            >
              <option value="">{STRINGS.analyzePage.selectRole}</option>
              {ROLE_OPTIONS.map((r) => (
                <option key={r.value} value={r.value}>{r.label}</option>
              ))}
            </select>
          </div>
        </div>
      )}

      {error && (
        <p className="text-sm text-rose-600 bg-rose-50 rounded-xl px-4 py-3">{error}</p>
      )}

      <button
        onClick={handleSubmit}
        disabled={!ready || submitting}
        className="w-full py-3.5 bg-[#1E3A5F] text-white rounded-xl font-semibold text-sm hover:bg-[#162D4A] disabled:opacity-40 disabled:cursor-not-allowed transition-colors shadow-sm"
      >
        {submitting ? (
          <span className="flex items-center justify-center gap-2">
            <span className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin" />
            {STRINGS.analyzePage.startingAnalysis}
          </span>
        ) : (
          <span className="flex items-center justify-center gap-2">
            <span className="shrink-0"><svg viewBox="0 0 16 16" fill="none" className="w-4 h-4 shrink-0" aria-hidden="true"><path d="M8 1v3M8 12v3M1 8h3M12 8h3M3.05 3.05l2.12 2.12M10.83 10.83l2.12 2.12M3.05 12.95l2.12-2.12M10.83 5.17l2.12-2.12" stroke="currentColor" strokeWidth={1.4} strokeLinecap="round"/></svg></span>
            {STRINGS.analyzePage.submitBtn}
          </span>
        )}
      </button>
    </div>
  );
}

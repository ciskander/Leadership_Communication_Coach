'use client';

import { useEffect, useState, useCallback } from 'react';
import Link from 'next/link';
import { api } from '@/lib/api';
import type { CoacheeListItem, CoacheeSummary } from '@/lib/types';
import { STRINGS } from '@/config/strings';

// ─── Status helpers ───────────────────────────────────────────────────────────

function getJourneyStage(summary: CoacheeSummary): {
  label: string;
  color: string;
  dotColor: string;
  borderColor: string;
} {
  const bp  = summary.active_baseline_pack;
  const exp = summary.active_experiment;

  if (exp) {
    return {
      label:       STRINGS.coachCard.experimenting,
      color:       'bg-cv-teal-50 text-cv-teal-700',
      dotColor:    'bg-cv-teal-500',
      borderColor: 'border-cv-teal-700',
    };
  }
  if (bp) {
    const status = (bp as Record<string, unknown>).status as string;
    if (status === 'completed' || status === 'baseline_ready') {
      return {
        label:       STRINGS.coachCard.baselineReady,
        color:       'bg-cv-teal-50 text-cv-teal-700',
        dotColor:    'bg-cv-teal-500',
        borderColor: 'border-cv-teal-700',
      };
    }
    return {
      label:       STRINGS.coachCard.baselineBuilding,
      color:       'bg-cv-amber-50 text-cv-amber-700',
      dotColor:    'bg-cv-amber-500',
      borderColor: 'border-cv-amber-700',
    };
  }
  if (summary.recent_runs.length > 0) {
    return {
      label:       STRINGS.coachCard.baselineReady,
      color:       'bg-cv-teal-50 text-cv-teal-700',
      dotColor:    'bg-cv-teal-500',
      borderColor: 'border-cv-teal-700',
    };
  }
  return {
    label:       STRINGS.coachCard.noActivity,
    color:       'bg-cv-warm-100 text-cv-stone-500',
    dotColor:    'bg-cv-stone-400',
    borderColor: 'border-cv-stone-700',
  };
}

function getDaysAgo(dateStr: string | undefined): number | null {
  if (!dateStr) return null;
  try {
    return Math.floor((Date.now() - new Date(dateStr).getTime()) / 86_400_000);
  } catch {
    return null;
  }
}

// ─── Avatar color cycle — all cv-warm based ───────────────────────────────────
const AVATAR_COLORS = [
  'bg-cv-teal-100 text-cv-teal-700',
  'bg-cv-amber-100 text-cv-amber-700',
  'bg-cv-teal-100 text-cv-navy-600',
  'bg-cv-warm-200 text-cv-stone-700',
  'bg-cv-stone-200 text-cv-stone-700',
  'bg-cv-red-100 text-cv-red-700',
];

// ─── Coachee card ─────────────────────────────────────────────────────────────

function CoacheeCard({
  coachee,
  summary,
  colorClass,
}: {
  coachee: CoacheeListItem;
  summary: CoacheeSummary | null;
  colorClass: string;
}) {
  const initials = (() => {
    const name = coachee.display_name ?? coachee.email;
    return name.split(' ').map((n: string) => n[0]).join('').toUpperCase().slice(0, 2);
  })();

  const stage = summary ? getJourneyStage(summary) : null;

  const lastRunDate  = summary?.recent_runs?.[0]?.created_at as string | undefined;
  const daysAgo      = getDaysAgo(lastRunDate);
  const stalenessColor =
    daysAgo === null    ? 'text-cv-stone-400'
    : daysAgo <= 7      ? 'text-cv-teal-600'
    : daysAgo <= 21     ? 'text-cv-amber-600'
    : 'text-cv-red-500';

  const exp = summary?.active_experiment;

  return (
    <Link
      href={`/coach/coachees/${coachee.id}`}
      className="bg-white rounded border border-cv-warm-300 p-5 hover:border-cv-teal-300 hover:shadow-sm transition-all group space-y-3"
    >
      {/* Avatar + name */}
      <div className="flex items-center gap-3">
        <div className={`w-10 h-10 rounded-full flex items-center justify-center text-sm font-bold shrink-0 ${colorClass}`}>
          {initials}
        </div>
        <div className="min-w-0 flex-1">
          <p className="font-semibold text-cv-stone-800 text-sm truncate">
            {coachee.display_name ?? STRINGS.coachDashboard.unnamed}
          </p>
          <p className="text-xs text-cv-stone-400 truncate">{coachee.email}</p>
        </div>
      </div>

      {/* Status row */}
      {stage && (
        <div className="flex items-center justify-between">
          <span className={`inline-flex items-center gap-1.5 text-xs font-medium px-2.5 py-1 rounded-full border ${stage.color} ${stage.borderColor}`}>
            <span className={`w-1.5 h-1.5 rounded-full ${stage.dotColor}`} />
            {stage.label}
          </span>
          <span className={`text-xs ${stalenessColor}`}>
            {daysAgo !== null
              ? STRINGS.coachCard.lastAnalysis(daysAgo)
              : STRINGS.coachCard.noAnalyses}
          </span>
        </div>
      )}

      {/* Active experiment */}
      {exp && (
        <div className="bg-cv-warm-100 rounded px-3 py-2">
          <p className="text-xs font-medium text-cv-stone-700 truncate">{exp.title}</p>
          {exp.attempt_count != null && exp.attempt_count > 0 && (
            <p className="text-xs text-cv-stone-500 mt-0.5">
              {STRINGS.coachCard.attempts(exp.attempt_count)}
              {exp.meeting_count ? ` / ${exp.meeting_count} meetings` : ''}
            </p>
          )}
        </div>
      )}

      {/* Footer */}
      <div className="flex items-center justify-between pt-1 border-t border-cv-warm-300">
        <span className="text-xs text-cv-stone-400">{STRINGS.coachDashboard.viewProfile}</span>
        <svg
          viewBox="0 0 20 20"
          fill="none"
          stroke="currentColor"
          strokeWidth={1.75}
          strokeLinecap="round"
          strokeLinejoin="round"
          className="w-4 h-4 text-cv-teal-500 group-hover:translate-x-0.5 transition-transform"
          aria-hidden="true"
        >
          <path d="M4 10h12M12 5l5 5-5 5" />
        </svg>
      </div>
    </Link>
  );
}

// ─── Add coachee modal ────────────────────────────────────────────────────────

function AddCoacheeModal({
  onClose,
  onAdded,
}: {
  onClose: () => void;
  onAdded: (c: CoacheeListItem) => void;
}) {
  const [tab, setTab]             = useState<'search' | 'invite'>('search');
  const [query, setQuery]         = useState('');
  const [results, setResults]     = useState<CoacheeListItem[]>([]);
  const [searching, setSearching] = useState(false);
  const [searchError, setSearchError] = useState<string | null>(null);
  const [assigning, setAssigning] = useState<string | null>(null);
  const [inviteUrl, setInviteUrl] = useState<string | null>(null);
  const [inviting, setInviting]   = useState(false);
  const [copied, setCopied]       = useState(false);

  const handleSearch = useCallback(async () => {
    if (query.length < 2) return;
    setSearching(true);
    setSearchError(null);
    try {
      const data = await api.searchUsers(query);
      setResults(data);
      if (data.length === 0) setSearchError(STRINGS.coachDashboard.noUsersFound);
    } catch {
      setSearchError(STRINGS.coachDashboard.searchFailed);
    } finally {
      setSearching(false);
    }
  }, [query]);

  useEffect(() => {
    const t = setTimeout(() => { if (query.length >= 2) handleSearch(); }, 400);
    return () => clearTimeout(t);
  }, [query, handleSearch]);

  const handleAssign = async (userId: string) => {
    setAssigning(userId);
    try {
      const coachee = await api.assignCoachee(userId);
      onAdded(coachee);
      onClose();
    } catch {
      setSearchError(STRINGS.coachDashboard.failedToAssign);
    } finally {
      setAssigning(null);
    }
  };

  const handleInvite = async () => {
    setInviting(true);
    try {
      const data = await api.createCoacheeInvite();
      setInviteUrl(data.invite_url);
    } catch {} finally {
      setInviting(false);
    }
  };

  const handleCopy = () => {
    if (!inviteUrl) return;
    navigator.clipboard.writeText(inviteUrl);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const inputCls = 'w-full border border-cv-warm-300 rounded px-4 py-2.5 text-sm text-cv-stone-800 bg-white focus:outline-none focus:border-cv-teal-400 focus:ring-1 focus:ring-cv-teal-400/30 transition-colors placeholder:text-cv-stone-400';

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm">
      <div className="bg-white rounded shadow-xl w-full max-w-md mx-4 overflow-hidden">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-cv-warm-300">
          <h2 className="font-semibold text-cv-stone-800">{STRINGS.coachDashboard.addCoacheeModalTitle}</h2>
          <button
            onClick={onClose}
            className="text-cv-stone-400 hover:text-cv-stone-600 transition-colors"
            aria-label="Close"
          >
            <svg viewBox="0 0 20 20" fill="currentColor" className="w-4 h-4" aria-hidden="true">
              <path d="M6.28 5.22a.75.75 0 00-1.06 1.06L8.94 10l-3.72 3.72a.75.75 0 101.06 1.06L10 11.06l3.72 3.72a.75.75 0 101.06-1.06L11.06 10l3.72-3.72a.75.75 0 00-1.06-1.06L10 8.94 6.28 5.22z" />
            </svg>
          </button>
        </div>

        {/* Tabs */}
        <div className="flex border-b border-cv-warm-300">
          {(['search', 'invite'] as const).map((t) => (
            <button
              key={t}
              onClick={() => setTab(t)}
              className={[
                'flex-1 py-3 text-sm font-medium transition-colors',
                tab === t
                  ? 'text-cv-teal-700 border-b-2 border-cv-teal-600'
                  : 'text-cv-stone-500 hover:text-cv-stone-700',
              ].join(' ')}
            >
              {t === 'search' ? STRINGS.coachDashboard.findExistingUser : STRINGS.coachDashboard.inviteNewUser}
            </button>
          ))}
        </div>

        <div className="p-6 space-y-4">
          {/* Search tab */}
          {tab === 'search' && (
            <>
              <div className="relative">
                <input
                  type="text"
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  placeholder={STRINGS.coachDashboard.searchPlaceholder}
                  className={inputCls}
                  autoFocus
                />
                {searching && (
                  <span className="absolute right-3 top-3 w-4 h-4 border-2 border-cv-teal-500 border-t-transparent rounded-full animate-spin" />
                )}
              </div>

              {searchError && <p className="text-xs text-cv-stone-500">{searchError}</p>}

              {results.length > 0 && (
                <ul className="space-y-2 max-h-56 overflow-y-auto">
                  {results.map((r) => (
                    <li
                      key={r.id}
                      className="flex items-center justify-between px-3 py-2.5 rounded border border-cv-warm-300 hover:border-cv-warm-300 transition-colors"
                    >
                      <div>
                        <p className="text-sm font-medium text-cv-stone-800">
                          {r.display_name ?? STRINGS.coachDashboard.unnamed}
                        </p>
                        <p className="text-xs text-cv-stone-400">{r.email}</p>
                      </div>
                      <button
                        onClick={() => handleAssign(r.id)}
                        disabled={assigning === r.id}
                        className="text-xs px-3 py-1.5 bg-cv-teal-600 text-white rounded font-medium hover:bg-cv-teal-700 disabled:opacity-50 transition-colors"
                      >
                        {assigning === r.id ? '…' : STRINGS.coachDashboard.add}
                      </button>
                    </li>
                  ))}
                </ul>
              )}

              {query.length > 0 && query.length < 2 && (
                <p className="text-xs text-cv-stone-400">{STRINGS.coachDashboard.typeAtLeast2}</p>
              )}
            </>
          )}

          {/* Invite tab */}
          {tab === 'invite' && (
            <>
              <p className="text-sm text-cv-stone-600">{STRINGS.coachDashboard.inviteDesc}</p>

              {!inviteUrl ? (
                <button
                  onClick={handleInvite}
                  disabled={inviting}
                  className="w-full py-2.5 bg-cv-teal-600 text-white rounded text-sm font-medium hover:bg-cv-teal-700 disabled:opacity-50 transition-colors"
                >
                  {inviting ? (
                    <span className="flex items-center justify-center gap-2">
                      <span className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin" />
                      {STRINGS.coachDashboard.generating}
                    </span>
                  ) : STRINGS.coachDashboard.generateInviteLink}
                </button>
              ) : (
                <div className="space-y-3">
                  <div className="bg-cv-warm-50 border border-cv-warm-300 rounded p-3">
                    <p className="text-xs font-mono text-cv-stone-600 break-all">{inviteUrl}</p>
                  </div>
                  <div className="flex gap-2">
                    <button
                      onClick={handleCopy}
                      className="flex-1 py-2 bg-cv-teal-600 text-white rounded text-sm font-medium hover:bg-cv-teal-700 transition-colors"
                    >
                      {copied ? STRINGS.coachDashboard.copied : STRINGS.coachDashboard.copyLink}
                    </button>
                    <button
                      onClick={() => setInviteUrl(null)}
                      className="px-4 py-2 border border-cv-warm-300 text-cv-stone-600 rounded text-sm font-medium hover:bg-cv-warm-50 transition-colors"
                    >
                      {STRINGS.coachDashboard.new}
                    </button>
                  </div>
                </div>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  );
}

// ─── Page ─────────────────────────────────────────────────────────────────────

export default function CoachDashboard() {
  const [coachees, setCoachees]   = useState<CoacheeListItem[]>([]);
  const [summaries, setSummaries] = useState<Record<string, CoacheeSummary>>({});
  const [loading, setLoading]     = useState(true);
  const [showModal, setShowModal] = useState(false);

  useEffect(() => {
    api.listCoachees().then((list) => {
      setCoachees(list);
      setLoading(false);
      list.forEach((c) => {
        api.getCoacheeSummary(c.id)
          .then((s) => setSummaries((prev) => ({ ...prev, [c.id]: s })))
          .catch(() => {});
      });
    }).catch(() => setLoading(false));
  }, []);

  const handleAdded = (c: CoacheeListItem) => {
    setCoachees((prev) => [...prev, c]);
    api.getCoacheeSummary(c.id)
      .then((s) => setSummaries((prev) => ({ ...prev, [c.id]: s })))
      .catch(() => {});
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <span className="w-8 h-8 border-2 border-cv-teal-600 border-t-transparent rounded-full animate-spin" />
      </div>
    );
  }

  return (
    <div className="max-w-6xl mx-auto space-y-6 py-2">
      {showModal && (
        <AddCoacheeModal onClose={() => setShowModal(false)} onAdded={handleAdded} />
      )}

      {/* Header */}
      <div className="flex items-start justify-between">
        <div>
          <h1 className="font-serif text-2xl text-cv-stone-900">
            {STRINGS.coachDashboard.heading}
          </h1>
          <p className="text-cv-stone-500 text-sm mt-1">
            {coachees.length === 0
              ? STRINGS.coachDashboard.emptySubtitle
              : STRINGS.coachDashboard.subtitle(coachees.length)}
          </p>
        </div>
        <button
          onClick={() => setShowModal(true)}
          className="flex items-center gap-2 px-4 py-2 bg-cv-teal-600 text-white rounded text-sm font-medium hover:bg-cv-teal-700 transition-colors shadow-sm"
        >
          <svg viewBox="0 0 20 20" fill="currentColor" className="w-4 h-4" aria-hidden="true">
            <path d="M10.75 4.75a.75.75 0 00-1.5 0v4.5h-4.5a.75.75 0 000 1.5h4.5v4.5a.75.75 0 001.5 0v-4.5h4.5a.75.75 0 000-1.5h-4.5v-4.5z" />
          </svg>
          {STRINGS.coachDashboard.addCoachee}
        </button>
      </div>

      {/* Grid / empty state */}
      {coachees.length === 0 ? (
        <div className="bg-white rounded border border-dashed border-cv-warm-300 p-12 text-center space-y-3">
          <div className="flex justify-center">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.5} strokeLinecap="round" strokeLinejoin="round" className="w-10 h-10 text-cv-stone-300" aria-hidden="true">
              <path d="M17 20C17 18 14.76 16 12 16C9.24 16 7 18 7 20M12 13C13.66 13 15 11.66 15 10C15 8.34 13.66 7 12 7C10.34 7 9 8.34 9 10C9 11.66 10.34 13 12 13Z" />
              <path d="M21 20C21 18.5 19.5 17.25 17.5 16.75M17.5 10C17.5 11.38 16.72 12.58 15.57 13.19" />
            </svg>
          </div>
          <p className="text-cv-stone-600 font-semibold">{STRINGS.coachDashboard.noCoacheesTitle}</p>
          <p className="text-sm text-cv-stone-400">{STRINGS.coachDashboard.noCoacheesDesc}</p>
          <button
            onClick={() => setShowModal(true)}
            className="mt-2 px-4 py-2 bg-cv-teal-600 text-white rounded text-sm font-medium hover:bg-cv-teal-700 transition-colors"
          >
            {STRINGS.coachDashboard.addCoachee}
          </button>
        </div>
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {coachees.map((c, i) => (
            <CoacheeCard
              key={c.id}
              coachee={c}
              summary={summaries[c.id] ?? null}
              colorClass={AVATAR_COLORS[i % AVATAR_COLORS.length]}
            />
          ))}
        </div>
      )}
    </div>
  );
}

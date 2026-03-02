'use client';

import { useEffect, useState, useCallback } from 'react';
import Link from 'next/link';
import { api } from '@/lib/api';
import type { CoacheeListItem } from '@/lib/types';

const BASE_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

// ── Add Coachee Modal ─────────────────────────────────────────────────────────

function AddCoacheeModal({
  onClose,
  onAdded,
}: {
  onClose: () => void;
  onAdded: (c: CoacheeListItem) => void;
}) {
  const [tab, setTab] = useState<'search' | 'invite'>('search');

  // Search state
  const [query, setQuery] = useState('');
  const [results, setResults] = useState<CoacheeListItem[]>([]);
  const [searching, setSearching] = useState(false);
  const [searchError, setSearchError] = useState<string | null>(null);
  const [assigning, setAssigning] = useState<string | null>(null);

  // Invite state
  const [inviteUrl, setInviteUrl] = useState<string | null>(null);
  const [inviting, setInviting] = useState(false);
  const [copied, setCopied] = useState(false);

  const handleSearch = useCallback(async () => {
    if (query.length < 2) return;
    setSearching(true);
    setSearchError(null);
    try {
      const data = await api.searchUsers(query);
      setResults(data);
      if (data.length === 0) setSearchError('No users found matching that search.');
    } catch {
      setSearchError('Search failed. Please try again.');
    } finally {
      setSearching(false);
    }
  }, [query]);

  useEffect(() => {
    const t = setTimeout(() => {
      if (query.length >= 2) handleSearch();
    }, 400);
    return () => clearTimeout(t);
  }, [query, handleSearch]);

  const handleAssign = async (userId: string) => {
    setAssigning(userId);
    try {
      const coachee = await api.assignCoachee(userId);
      onAdded(coachee);
      onClose();
    } catch {
      setSearchError('Failed to assign coachee.');
    } finally {
      setAssigning(null);
    }
  };

  const handleInvite = async () => {
    setInviting(true);
    try {
      const data = await api.createCoacheeInvite();
      setInviteUrl(data.invite_url);
    } catch {
      // ignore
    } finally {
      setInviting(false);
    }
  };

  const handleCopy = () => {
    if (!inviteUrl) return;
    navigator.clipboard.writeText(inviteUrl);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm">
      <div className="bg-white rounded-2xl shadow-xl w-full max-w-md mx-4 overflow-hidden">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-stone-200">
          <h2 className="font-semibold text-stone-800">Add Coachee</h2>
          <button
            onClick={onClose}
            className="text-stone-400 hover:text-stone-600 transition-colors text-lg leading-none"
          >
            ✕
          </button>
        </div>

        {/* Tabs */}
        <div className="flex border-b border-stone-200">
          {(['search', 'invite'] as const).map((t) => (
            <button
              key={t}
              onClick={() => setTab(t)}
              className={`flex-1 py-3 text-sm font-medium transition-colors ${
                tab === t
                  ? 'text-emerald-700 border-b-2 border-emerald-600'
                  : 'text-stone-500 hover:text-stone-700'
              }`}
            >
              {t === 'search' ? 'Find Existing User' : 'Invite New User'}
            </button>
          ))}
        </div>

        <div className="p-6 space-y-4">
          {tab === 'search' && (
            <>
              <div className="relative">
                <input
                  type="text"
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  placeholder="Search by name or email…"
                  className="w-full border border-stone-300 rounded-xl px-4 py-2.5 text-sm pr-10 focus:outline-none focus:border-emerald-400"
                  autoFocus
                />
                {searching && (
                  <div className="absolute right-3 top-3 w-4 h-4 border-2 border-emerald-500 border-t-transparent rounded-full animate-spin" />
                )}
              </div>

              {searchError && (
                <p className="text-xs text-stone-500">{searchError}</p>
              )}

              {results.length > 0 && (
                <ul className="space-y-2 max-h-56 overflow-y-auto">
                  {results.map((r) => (
                    <li
                      key={r.id}
                      className="flex items-center justify-between px-3 py-2.5 rounded-xl border border-stone-200 hover:border-stone-300 transition-colors"
                    >
                      <div>
                        <p className="text-sm font-medium text-stone-800">
                          {r.display_name ?? 'Unnamed'}
                        </p>
                        <p className="text-xs text-stone-400">{r.email}</p>
                      </div>
                      <button
                        onClick={() => handleAssign(r.id)}
                        disabled={assigning === r.id}
                        className="text-xs px-3 py-1.5 bg-emerald-600 text-white rounded-lg font-medium hover:bg-emerald-700 disabled:opacity-50 transition-colors"
                      >
                        {assigning === r.id ? '…' : 'Add'}
                      </button>
                    </li>
                  ))}
                </ul>
              )}

              {query.length > 0 && query.length < 2 && (
                <p className="text-xs text-stone-400">Type at least 2 characters to search.</p>
              )}
            </>
          )}

          {tab === 'invite' && (
            <>
              <p className="text-sm text-stone-600">
                Generate a single-use invite link to send to a new coachee. They'll be linked to your account when they sign up.
              </p>

              {!inviteUrl ? (
                <button
                  onClick={handleInvite}
                  disabled={inviting}
                  className="w-full py-2.5 bg-emerald-600 text-white rounded-xl text-sm font-medium hover:bg-emerald-700 disabled:opacity-50 transition-colors"
                >
                  {inviting ? (
                    <span className="flex items-center justify-center gap-2">
                      <span className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin" />
                      Generating…
                    </span>
                  ) : (
                    'Generate Invite Link'
                  )}
                </button>
              ) : (
                <div className="space-y-3">
                  <div className="bg-stone-50 border border-stone-200 rounded-xl p-3">
                    <p className="text-xs font-mono text-stone-600 break-all">{inviteUrl}</p>
                  </div>
                  <div className="flex gap-2">
                    <button
                      onClick={handleCopy}
                      className="flex-1 py-2 bg-emerald-600 text-white rounded-xl text-sm font-medium hover:bg-emerald-700 transition-colors"
                    >
                      {copied ? '✓ Copied!' : 'Copy Link'}
                    </button>
                    <button
                      onClick={() => setInviteUrl(null)}
                      className="px-4 py-2 border border-stone-300 text-stone-600 rounded-xl text-sm font-medium hover:bg-stone-50 transition-colors"
                    >
                      New
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

// ── Page ──────────────────────────────────────────────────────────────────────

export default function CoachDashboard() {
  const [coachees, setCoachees] = useState<CoacheeListItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [showModal, setShowModal] = useState(false);

  useEffect(() => {
    api.listCoachees().then(setCoachees).finally(() => setLoading(false));
  }, []);

  const handleAdded = (c: CoacheeListItem) => {
    setCoachees((prev) => [...prev, c]);
  };

  const initials = (c: CoacheeListItem) => {
    const name = c.display_name ?? c.email;
    return name.split(' ').map((n: string) => n[0]).join('').toUpperCase().slice(0, 2);
  };

  const colors = [
    'bg-emerald-100 text-emerald-700',
    'bg-blue-100 text-blue-700',
    'bg-violet-100 text-violet-700',
    'bg-amber-100 text-amber-700',
    'bg-rose-100 text-rose-700',
    'bg-teal-100 text-teal-700',
  ];

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-emerald-600" />
      </div>
    );
  }

  return (
    <div className="max-w-4xl mx-auto space-y-6 py-2">
      {showModal && (
        <AddCoacheeModal
          onClose={() => setShowModal(false)}
          onAdded={handleAdded}
        />
      )}

      {/* Header */}
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-2xl font-bold text-stone-900">My Coachees</h1>
          <p className="text-stone-500 text-sm mt-1">
            {coachees.length === 0
              ? 'Add your first coachee to get started.'
              : `${coachees.length} coachee${coachees.length !== 1 ? 's' : ''} in your programme.`}
          </p>
        </div>
        <button
          onClick={() => setShowModal(true)}
          className="flex items-center gap-2 px-4 py-2 bg-emerald-600 text-white rounded-xl text-sm font-medium hover:bg-emerald-700 transition-colors shadow-sm"
        >
          <span>+</span> Add Coachee
        </button>
      </div>

      {/* Coachee grid */}
      {coachees.length === 0 ? (
        <div className="bg-white rounded-2xl border border-dashed border-stone-300 p-12 text-center space-y-3">
          <div className="text-4xl">◫</div>
          <p className="text-stone-600 font-medium">No coachees yet</p>
          <p className="text-sm text-stone-400">
            Search for existing users or invite new ones.
          </p>
          <button
            onClick={() => setShowModal(true)}
            className="mt-2 px-4 py-2 bg-emerald-600 text-white rounded-xl text-sm font-medium hover:bg-emerald-700 transition-colors"
          >
            Add Coachee
          </button>
        </div>
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {coachees.map((c, i) => (
            <Link
              key={c.id}
              href={`/coach/coachees/${c.id}`}
              className="bg-white rounded-2xl border border-stone-200 p-5 hover:border-emerald-300 hover:shadow-md transition-all group space-y-4"
            >
              <div className="flex items-center gap-3">
                <div
                  className={`w-10 h-10 rounded-full flex items-center justify-center text-sm font-bold flex-shrink-0 ${
                    colors[i % colors.length]
                  }`}
                >
                  {initials(c)}
                </div>
                <div className="min-w-0">
                  <p className="font-semibold text-stone-800 text-sm truncate">
                    {c.display_name ?? 'Unnamed'}
                  </p>
                  <p className="text-xs text-stone-400 truncate">{c.email}</p>
                </div>
              </div>
              <div className="flex items-center justify-between pt-2 border-t border-stone-100">
                <span className="text-xs text-stone-400">View profile</span>
                <span className="text-emerald-500 group-hover:translate-x-0.5 transition-transform">→</span>
              </div>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}

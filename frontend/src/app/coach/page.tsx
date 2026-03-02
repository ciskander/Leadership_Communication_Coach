'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { api } from '@/lib/api';
import type { CoacheeListItem } from '@/lib/types';

export default function CoachDashboard() {
  const [coachees, setCoachees] = useState<CoacheeListItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [inviteUrl, setInviteUrl] = useState<string | null>(null);
  const [inviting, setInviting] = useState(false);
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    api.listCoachees().then(setCoachees).finally(() => setLoading(false));
  }, []);

  const handleInvite = async () => {
	setInviting(true);
	try {
		const data = await api.createCoacheeInvite();
		setInviteUrl(data.invite_url);
	} catch {
		setError('Failed to generate invite link.');
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
      {/* Header */}
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-2xl font-bold text-stone-900">My Coachees</h1>
          <p className="text-stone-500 text-sm mt-1">
            {coachees.length === 0
              ? 'Invite your first coachee to get started.'
              : `${coachees.length} coachee${coachees.length !== 1 ? 's' : ''} in your programme.`}
          </p>
        </div>
        <button
          onClick={handleInvite}
          disabled={inviting}
          className="flex items-center gap-2 px-4 py-2 bg-emerald-600 text-white rounded-xl text-sm font-medium hover:bg-emerald-700 transition-colors shadow-sm disabled:opacity-50"
        >
          {inviting ? (
            <span className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin" />
          ) : (
            <span>+</span>
          )}
          Invite Coachee
        </button>
      </div>

      {/* Invite URL box */}
      {inviteUrl && (
        <div className="bg-emerald-50 border border-emerald-200 rounded-xl p-4 flex items-center gap-3">
          <div className="flex-1 min-w-0">
            <p className="text-xs font-semibold text-emerald-700 mb-1">Invite link (single use)</p>
            <p className="text-xs text-stone-600 truncate font-mono">{inviteUrl}</p>
          </div>
          <button
            onClick={handleCopy}
            className="px-3 py-1.5 bg-white border border-emerald-300 text-emerald-700 rounded-lg text-xs font-semibold hover:bg-emerald-50 transition-colors whitespace-nowrap"
          >
            {copied ? '✓ Copied' : 'Copy link'}
          </button>
        </div>
      )}

      {/* Coachee grid */}
      {coachees.length === 0 ? (
        <div className="bg-white rounded-2xl border border-dashed border-stone-300 p-12 text-center space-y-3">
          <div className="text-4xl">◫</div>
          <p className="text-stone-600 font-medium">No coachees yet</p>
          <p className="text-sm text-stone-400">
            Use the invite button above to add your first coachee.
          </p>
        </div>
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {coachees.map((c, i) => (
            <Link
              key={c.id}
              href={`/coach/coachees/${c.id}`}
              className="bg-white rounded-2xl border border-stone-200 p-5 hover:border-emerald-300 hover:shadow-md transition-all group space-y-4"
            >
              {/* Avatar + name */}
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

              {/* View link */}
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

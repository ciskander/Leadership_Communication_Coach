'use client';

import { useEffect, useState } from 'react';
import { api } from '@/lib/api';
import { STRINGS } from '@/config/strings';
import type { AdminUser } from '@/lib/types';

export default function AdminPage() {
  const [users, setUsers]       = useState<AdminUser[]>([]);
  const [loading, setLoading]   = useState(true);
  const [promoting, setPromoting] = useState<string | null>(null);

  const fetchUsers = () => {
    api.listAdminUsers().then(setUsers).finally(() => setLoading(false));
  };

  useEffect(() => { fetchUsers(); }, []);

  const promote = async (userId: string) => {
    setPromoting(userId);
    try {
      await api.promoteToCoach(userId);
      fetchUsers();
    } finally {
      setPromoting(null);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <span className="w-8 h-8 border-2 border-cv-teal-600 border-t-transparent rounded-full animate-spin" />
      </div>
    );
  }

  return (
    <div className="max-w-4xl mx-auto space-y-6">
      <h1 className="text-2xl font-semibold text-cv-stone-900 font-serif">{STRINGS.admin.heading}</h1>

      <div className="bg-white rounded border border-cv-warm-200 overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-cv-warm-50 border-b border-cv-warm-200">
            <tr>
              <th className="text-left px-4 py-3 text-2xs font-semibold text-cv-stone-400 uppercase tracking-[0.12em]">
                {STRINGS.admin.userColumn}
              </th>
              <th className="text-left px-4 py-3 text-2xs font-semibold text-cv-stone-400 uppercase tracking-[0.12em]">
                {STRINGS.admin.roleColumn}
              </th>
              <th className="text-left px-4 py-3 text-2xs font-semibold text-cv-stone-400 uppercase tracking-[0.12em]">
                {STRINGS.admin.lastLoginColumn}
              </th>
              <th className="px-4 py-3" />
            </tr>
          </thead>
          <tbody className="divide-y divide-cv-warm-100">
            {users.map((u) => (
              <tr key={u.id} className="hover:bg-cv-warm-50 transition-colors">
                <td className="px-4 py-3">
                  <p className="font-medium text-cv-stone-900">{u.display_name ?? u.email}</p>
                  <p className="text-xs text-cv-stone-500">{u.email}</p>
                </td>
                <td className="px-4 py-3">
                  <span className={[
                    'text-2xs px-2 py-0.5 rounded-full capitalize font-semibold',
                    u.role === 'admin'   ? 'bg-cv-red-100 text-cv-red-700'
                    : u.role === 'coach' ? 'bg-cv-teal-100 text-cv-teal-700'
                    : 'bg-cv-warm-100 text-cv-stone-600',
                  ].join(' ')}>
                    {u.role}
                  </span>
                </td>
                <td className="px-4 py-3 text-cv-stone-500 text-xs tabular-nums">
                  {u.last_login ? new Date(u.last_login).toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' }) : '—'}
                </td>
                <td className="px-4 py-3 text-right">
                  {u.role === 'coachee' && (
                    <button
                      onClick={() => promote(u.id)}
                      disabled={promoting === u.id}
                      className="text-xs px-3 py-1.5 bg-cv-teal-600 text-white rounded font-medium hover:bg-cv-teal-700 disabled:opacity-50 transition-colors"
                    >
                      {promoting === u.id ? '…' : STRINGS.admin.promoteToCoach}
                    </button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

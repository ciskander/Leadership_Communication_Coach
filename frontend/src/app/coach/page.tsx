'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { api } from '@/lib/api';
import type { CoacheeListItem } from '@/lib/types';

export default function CoachPage() {
  const [coachees, setCoachees] = useState<CoacheeListItem[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api.listCoachees().then(setCoachees).finally(() => setLoading(false));
  }, []);

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-indigo-600" />
      </div>
    );
  }

  return (
    <div className="max-w-3xl mx-auto space-y-6">
      <h1 className="text-2xl font-bold text-gray-900">My Coachees</h1>

      {coachees.length === 0 ? (
        <p className="text-sm text-gray-500">No coachees assigned yet.</p>
      ) : (
        <ul className="space-y-3">
          {coachees.map((c) => (
            <li key={c.id}>
              <Link
                href={`/coach/coachees/${c.id}`}
                className="flex items-center justify-between bg-white border border-gray-200 rounded-lg px-5 py-4 hover:border-indigo-300 transition-colors"
              >
                <div>
                  <p className="font-medium text-gray-900">
                    {c.display_name ?? c.email}
                  </p>
                  <p className="text-sm text-gray-500">{c.email}</p>
                </div>
                <span className="text-indigo-400">→</span>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

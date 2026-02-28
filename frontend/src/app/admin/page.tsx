'use client';

import { useEffect, useState } from 'react';
import { api } from '@/lib/api';
import type { AdminUser } from '@/lib/types';

export default function AdminPage() {
  const [users, setUsers] = useState<AdminUser[]>([]);
  const [loading, setLoading] = useState(true);
  const [promoting, setPromoting] = useState<string | null>(null);

  const fetchUsers = () => {
    api.listAdminUsers().then(setUsers).finally(() => setLoading(false));
  };

  useEffect(() => {
    fetchUsers();
  }, []);

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
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-indigo-600" />
      </div>
    );
  }

  return (
    <div className="max-w-4xl mx-auto space-y-6">
      <h1 className="text-2xl font-bold text-gray-900">User Management</h1>

      <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-gray-50 border-b border-gray-200">
            <tr>
              <th className="text-left px-4 py-3 text-xs font-semibold text-gray-600 uppercase">User</th>
              <th className="text-left px-4 py-3 text-xs font-semibold text-gray-600 uppercase">Role</th>
              <th className="text-left px-4 py-3 text-xs font-semibold text-gray-600 uppercase">Last Login</th>
              <th className="px-4 py-3" />
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100">
            {users.map((u) => (
              <tr key={u.id} className="hover:bg-gray-50">
                <td className="px-4 py-3">
                  <p className="font-medium text-gray-900">{u.display_name ?? u.email}</p>
                  <p className="text-xs text-gray-500">{u.email}</p>
                </td>
                <td className="px-4 py-3">
                  <span
                    className={`text-xs px-2 py-0.5 rounded-full capitalize font-medium ${
                      u.role === 'admin'
                        ? 'bg-red-100 text-red-700'
                        : u.role === 'coach'
                        ? 'bg-indigo-100 text-indigo-700'
                        : 'bg-gray-100 text-gray-600'
                    }`}
                  >
                    {u.role}
                  </span>
                </td>
                <td className="px-4 py-3 text-gray-500 text-xs">
                  {u.last_login ? new Date(u.last_login).toLocaleDateString() : '—'}
                </td>
                <td className="px-4 py-3 text-right">
                  {u.role === 'coachee' && (
                    <button
                      onClick={() => promote(u.id)}
                      disabled={promoting === u.id}
                      className="text-xs px-3 py-1.5 bg-indigo-600 text-white rounded-md hover:bg-indigo-700 disabled:opacity-50"
                    >
                      {promoting === u.id ? '…' : 'Promote to Coach'}
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

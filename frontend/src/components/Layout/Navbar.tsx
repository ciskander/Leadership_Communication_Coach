'use client';

import Link from 'next/link';
import { useAuth } from '@/hooks/useAuth';
import { api } from '@/lib/api';
import { useRouter } from 'next/navigation';

export function Navbar() {
  const { user } = useAuth();
  const router = useRouter();

  const handleLogout = async () => {
    await api.logout();
    router.push('/');
  };

  const initials = user?.display_name
    ? user.display_name.split(' ').map((n) => n[0]).join('').toUpperCase().slice(0, 2)
    : user?.email?.[0]?.toUpperCase() ?? '?';

  return (
    <nav className="bg-white border-b border-stone-200 px-6 py-0 flex items-center justify-between h-14 sticky top-0 z-30">
      <Link href="/" className="flex items-center gap-2.5 group">
        <div className="w-7 h-7 bg-emerald-600 rounded-lg flex items-center justify-center shadow-sm group-hover:bg-emerald-700 transition-colors">
          <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
            <path d="M7 1L9.5 5.5H12.5L10 8.5L11 13L7 10.5L3 13L4 8.5L1.5 5.5H4.5L7 1Z" fill="white" fillOpacity="0.9"/>
          </svg>
        </div>
        <span className="text-stone-800 font-semibold text-base tracking-tight">
          ClearVoice
        </span>
      </Link>

      <div className="flex items-center gap-3">
        {user && (
          <>
            <div className="flex items-center gap-2.5">
              <div className="w-8 h-8 rounded-full bg-emerald-100 flex items-center justify-center">
                <span className="text-xs font-semibold text-emerald-700">{initials}</span>
              </div>
              <div className="hidden sm:block text-right">
                <p className="text-sm font-medium text-stone-800 leading-tight">
                  {user.display_name ?? user.email}
                </p>
                <p className="text-xs text-stone-400 capitalize leading-tight">{user.role}</p>
              </div>
            </div>
            <div className="w-px h-5 bg-stone-200" />
            <button
              onClick={handleLogout}
              className="text-xs text-stone-400 hover:text-stone-600 transition-colors font-medium"
            >
              Sign out
            </button>
          </>
        )}
      </div>
    </nav>
  );
}

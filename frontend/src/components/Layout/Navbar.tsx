'use client';

import Link from 'next/link';
import { useAuth } from '@/hooks/useAuth';
import { api } from '@/lib/api';
import { useRouter } from 'next/navigation';
import Image from 'next/image';
import { STRINGS } from '@/config/strings';
import { ClearVoiceLogo } from '@/components/ClearVoiceLogo';

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
		<Link href="/">
		  <ClearVoiceLogo className="h-9 w-auto" />
		</Link>

      <div className="flex items-center gap-3">
        {user && (
          <>
            <div className="flex items-center gap-2.5">
              {user.profile_photo_url ? (
                <img
                  src={user.profile_photo_url}
                  alt={user.display_name ?? user.email}
                  className="w-8 h-8 rounded-full object-cover"
                  referrerPolicy="no-referrer"
                />
              ) : (
                <div className="w-8 h-8 rounded-full bg-emerald-100 flex items-center justify-center">
                  <span className="text-xs font-semibold text-emerald-700">{initials}</span>
                </div>
              )}
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
              {STRINGS.app.signOut}
            </button>
          </>
        )}
      </div>
    </nav>
  );
}

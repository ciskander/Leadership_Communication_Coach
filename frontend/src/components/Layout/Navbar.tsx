'use client';

import Link from 'next/link';
import { useAuth } from '@/hooks/useAuth';
import { api } from '@/lib/api';
import { useRouter } from 'next/navigation';
import { STRINGS } from '@/config/strings';
import { ClearVoiceLogo } from '@/components/ClearVoiceLogo';

export function Navbar() {
  const { user }  = useAuth();
  const router    = useRouter();

  const handleLogout = async () => {
    await api.logout();
    router.push('/');
  };

  // Derive initials: first letter of each name word, max two
  const initials = user?.display_name
    ? user.display_name
        .split(' ')
        .map((n) => n[0])
        .join('')
        .toUpperCase()
        .slice(0, 2)
    : user?.email?.[0]?.toUpperCase() ?? '?';

  return (
    <nav className="bg-white border-b border-cv-warm-200 px-6 py-0 flex items-center justify-between h-14 sticky top-0 z-30">

      {/* ── Logo ── */}
      <Link href="/" className="flex items-center">
        <ClearVoiceLogo className="h-8 w-auto" />
      </Link>

      {/* ── Right side: avatar + name + sign-out ── */}
      {user && (
        <div className="flex items-center gap-3">

          {/* Avatar + name block */}
          <div className="flex items-center gap-2.5">
            {user.profile_photo_url ? (
              <img
                src={user.profile_photo_url}
                alt={user.display_name ?? user.email}
                className="w-7 h-7 rounded-full object-cover ring-1 ring-cv-warm-200"
                referrerPolicy="no-referrer"
              />
            ) : (
              /* Initials avatar — teal bg when coachee, blue when coach */
              <div className="w-7 h-7 rounded-full bg-cv-teal-50 ring-1 ring-cv-teal-200 flex items-center justify-center">
                <span className="text-[10px] font-semibold text-cv-teal-700 leading-none tracking-wide">
                  {initials}
                </span>
              </div>
            )}

            {/* Name + role — hidden on very small screens */}
            <div className="hidden sm:block text-right leading-none">
              <p className="text-[13px] font-medium text-cv-stone-800 leading-snug">
                {user.display_name ?? user.email}
              </p>
              <p className="text-2xs text-cv-stone-400 capitalize leading-snug mt-px">
                {user.role}
              </p>
            </div>
          </div>

          {/* Divider */}
          <div className="w-px h-4 bg-cv-warm-200" />

          {/* Sign out */}
          <button
            onClick={handleLogout}
            className="text-2xs font-medium text-cv-stone-400 hover:text-cv-stone-700 transition-colors"
          >
            {STRINGS.app.signOut}
          </button>
        </div>
      )}
    </nav>
  );
}

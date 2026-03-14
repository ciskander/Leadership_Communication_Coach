'use client';

import { useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { api, ApiError } from '@/lib/api';
import { getGoogleLoginUrl } from '@/lib/auth';
import { STRINGS } from '@/config/strings';
import { ClearVoiceLogo } from '@/components/ClearVoiceLogo';

export default function RootPage() {
  const router = useRouter();

  useEffect(() => {
    api
      .me()
      .then((user) => {
        if (user.role === 'coach') router.push('/coach');
        else if (user.role === 'admin') router.push('/admin');
        else router.push('/client');
      })
      .catch((e) => {
        if (e instanceof ApiError && e.status === 401) {
          // Not authenticated — show login
        }
      });
  }, [router]);

  return (
    <main className="min-h-screen flex items-center justify-center bg-cv-warm-100">
      <div className="bg-white rounded border border-cv-warm-200 shadow-sm p-10 max-w-sm w-full text-center space-y-7">

        {/* Logo */}
        <div className="flex justify-center">
          <ClearVoiceLogo className="h-10 w-auto" />
        </div>

        {/* Heading + subheading */}
        <div className="space-y-2">
          <h1 className="text-xl font-semibold text-cv-stone-900 font-serif">
            {STRINGS.app.loginHeading}
          </h1>
          <p className="text-sm text-cv-stone-500 leading-relaxed">
            {STRINGS.app.loginSubheading}
          </p>
        </div>

        {/* Divider */}
        <div className="border-t border-cv-warm-200" />

        {/* Google sign-in */}
        <a
          href={getGoogleLoginUrl('/client')}
          className="inline-flex items-center justify-center gap-3 w-full border border-cv-warm-300 rounded px-5 py-3 text-sm font-medium text-cv-stone-700 hover:bg-cv-warm-50 transition-colors"
        >
          {/* Google logo — unchanged, brand-required colours */}
          <svg className="w-4 h-4 shrink-0" viewBox="0 0 48 48" aria-hidden="true">
            <path fill="#4285F4" d="M45.12 24.5c0-1.56-.14-3.06-.4-4.5H24v8.51h11.84c-.51 2.75-2.06 5.08-4.39 6.64v5.52h7.11c4.16-3.83 6.56-9.47 6.56-16.17z" />
            <path fill="#34A853" d="M24 46c5.94 0 10.92-1.97 14.56-5.33l-7.11-5.52c-1.97 1.32-4.49 2.1-7.45 2.1-5.73 0-10.58-3.87-12.31-9.07H4.34v5.7C7.96 41.07 15.4 46 24 46z" />
            <path fill="#FBBC05" d="M11.69 28.18C11.25 26.86 11 25.45 11 24s.25-2.86.69-4.18v-5.7H4.34C2.85 17.09 2 20.45 2 24c0 3.55.85 6.91 2.34 9.88l7.35-5.7z" />
            <path fill="#EA4335" d="M24 10.75c3.23 0 6.13 1.11 8.41 3.29l6.31-6.31C34.91 4.18 29.93 2 24 2 15.4 2 7.96 6.93 4.34 14.12l7.35 5.7c1.73-5.2 6.58-9.07 12.31-9.07z" />
          </svg>
          {STRINGS.app.continueWithGoogle}
        </a>
      </div>
    </main>
  );
}

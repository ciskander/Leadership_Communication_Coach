'use client';

import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { api, ApiError } from '@/lib/api';
import { getGoogleLoginUrl, getMicrosoftLoginUrl } from '@/lib/auth';
import { STRINGS } from '@/config/strings';
import { ClearVoiceLogo } from '@/components/ClearVoiceLogo';

export default function RootPage() {
  const router = useRouter();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

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

  const handleEmailLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      const result = await api.loginEmail(email, password);
      if (result.user) {
        const role = result.user.role;
        if (role === 'coach') router.push('/coach');
        else if (role === 'admin') router.push('/admin');
        else router.push('/client');
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Sign in failed.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <main className="min-h-screen flex items-center justify-center bg-cv-warm-100">
      <div className="bg-white rounded border border-cv-warm-300 shadow-sm p-10 max-w-sm w-full text-center space-y-6">

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

        {/* OAuth buttons */}
        <div className="space-y-3">
          {/* Google */}
          <a
            href={getGoogleLoginUrl('/client')}
            className="inline-flex items-center justify-center gap-3 w-full border border-cv-warm-300 rounded px-5 py-3 text-sm font-medium text-cv-stone-700 hover:bg-cv-warm-50 transition-colors"
          >
            <svg className="w-4 h-4 shrink-0" viewBox="0 0 48 48" aria-hidden="true">
              <path fill="#4285F4" d="M45.12 24.5c0-1.56-.14-3.06-.4-4.5H24v8.51h11.84c-.51 2.75-2.06 5.08-4.39 6.64v5.52h7.11c4.16-3.83 6.56-9.47 6.56-16.17z" />
              <path fill="#34A853" d="M24 46c5.94 0 10.92-1.97 14.56-5.33l-7.11-5.52c-1.97 1.32-4.49 2.1-7.45 2.1-5.73 0-10.58-3.87-12.31-9.07H4.34v5.7C7.96 41.07 15.4 46 24 46z" />
              <path fill="#FBBC05" d="M11.69 28.18C11.25 26.86 11 25.45 11 24s.25-2.86.69-4.18v-5.7H4.34C2.85 17.09 2 20.45 2 24c0 3.55.85 6.91 2.34 9.88l7.35-5.7z" />
              <path fill="#EA4335" d="M24 10.75c3.23 0 6.13 1.11 8.41 3.29l6.31-6.31C34.91 4.18 29.93 2 24 2 15.4 2 7.96 6.93 4.34 14.12l7.35 5.7c1.73-5.2 6.58-9.07 12.31-9.07z" />
            </svg>
            {STRINGS.app.continueWithGoogle}
          </a>

          {/* Microsoft */}
          <a
            href={getMicrosoftLoginUrl('/client')}
            className="inline-flex items-center justify-center gap-3 w-full border border-cv-warm-300 rounded px-5 py-3 text-sm font-medium text-cv-stone-700 hover:bg-cv-warm-50 transition-colors"
          >
            <svg className="w-4 h-4 shrink-0" viewBox="0 0 21 21" aria-hidden="true">
              <rect x="1" y="1" width="9" height="9" fill="#f25022" />
              <rect x="1" y="11" width="9" height="9" fill="#00a4ef" />
              <rect x="11" y="1" width="9" height="9" fill="#7fba00" />
              <rect x="11" y="11" width="9" height="9" fill="#ffb900" />
            </svg>
            {STRINGS.app.continueWithMicrosoft}
          </a>
        </div>

        {/* Divider */}
        <div className="flex items-center gap-3">
          <div className="flex-1 border-t border-cv-warm-300" />
          <span className="text-xs text-cv-stone-400">{STRINGS.app.orSignInWithEmail}</span>
          <div className="flex-1 border-t border-cv-warm-300" />
        </div>

        {/* Email/password form */}
        <form onSubmit={handleEmailLogin} className="space-y-4 text-left">
          <div>
            <label htmlFor="email" className="block text-xs font-medium text-cv-stone-600 mb-1">
              {STRINGS.app.email}
            </label>
            <input
              id="email"
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
              className="w-full border border-cv-warm-300 rounded px-3 py-2 text-sm text-cv-stone-900 focus:outline-none focus:ring-2 focus:ring-cv-teal-500 focus:border-transparent"
            />
          </div>
          <div>
            <label htmlFor="password" className="block text-xs font-medium text-cv-stone-600 mb-1">
              {STRINGS.app.password}
            </label>
            <input
              id="password"
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
              className="w-full border border-cv-warm-300 rounded px-3 py-2 text-sm text-cv-stone-900 focus:outline-none focus:ring-2 focus:ring-cv-teal-500 focus:border-transparent"
            />
          </div>

          {error && (
            <p className="text-xs text-cv-red-600 bg-cv-red-50 border border-cv-red-200 rounded px-3 py-2">
              {error}
            </p>
          )}

          <button
            type="submit"
            disabled={loading}
            className="w-full bg-cv-teal-600 text-white rounded px-5 py-2.5 text-sm font-medium hover:bg-cv-teal-700 transition-colors disabled:opacity-50"
          >
            {loading ? 'Signing in\u2026' : STRINGS.app.signIn}
          </button>
        </form>

        {/* Links */}
        <div className="space-y-2 text-xs text-cv-stone-500">
          <a href="/auth/forgot-password" className="hover:text-cv-teal-600 transition-colors">
            {STRINGS.app.forgotPassword}
          </a>
          <p>
            {STRINGS.app.noAccount}{' '}
            <a href="/auth/register" className="text-cv-teal-600 hover:text-cv-teal-700 font-medium">
              {STRINGS.app.registerLink}
            </a>
          </p>
        </div>
      </div>
    </main>
  );
}

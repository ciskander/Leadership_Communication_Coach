'use client';

import { useState, Suspense } from 'react';
import { useSearchParams } from 'next/navigation';
import { api } from '@/lib/api';
import { STRINGS } from '@/config/strings';
import { ClearVoiceLogo } from '@/components/ClearVoiceLogo';

function RegisterForm() {
  const params = useSearchParams();
  const inviteToken = params.get('invite_token');

  const [email, setEmail] = useState('');
  const [displayName, setDisplayName] = useState('');
  const [password, setPassword] = useState('');
  const [confirmPw, setConfirmPw] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);

    if (password.length < 8) {
      setError(STRINGS.app.passwordTooShort);
      return;
    }
    if (password !== confirmPw) {
      setError(STRINGS.app.passwordMismatch);
      return;
    }

    setLoading(true);
    try {
      const result = await api.register({
        email,
        password,
        display_name: displayName || undefined,
        invite_token: inviteToken || undefined,
      });
      setSuccess(result.message);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Registration failed.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <main className="min-h-screen flex items-center justify-center bg-cv-warm-100">
      <div className="bg-white rounded border border-cv-warm-300 shadow-sm p-10 max-w-sm w-full text-center space-y-6">
        <div className="flex justify-center">
          <ClearVoiceLogo className="h-10 w-auto" />
        </div>

        <h1 className="text-xl font-semibold text-cv-stone-900 font-serif">
          {STRINGS.app.createAccount}
        </h1>

        {success ? (
          <div className="space-y-4">
            <p className="text-sm text-cv-emerald-700 bg-cv-emerald-50 border border-cv-emerald-200 rounded px-4 py-3">
              {success}
            </p>
            <a href="/" className="text-sm text-cv-emerald-600 hover:text-cv-emerald-700 font-medium">
              {STRINGS.app.signInLink}
            </a>
          </div>
        ) : (
          <form onSubmit={handleSubmit} className="space-y-4 text-left">
            <div>
              <label htmlFor="email" className="block text-xs font-medium text-cv-stone-600 mb-1">
                {STRINGS.app.email}
              </label>
              <input
                id="email" type="email" value={email} onChange={(e) => setEmail(e.target.value)}
                required
                className="w-full border border-cv-warm-300 rounded px-3 py-2 text-sm text-cv-stone-900 focus:outline-none focus:ring-2 focus:ring-cv-emerald-500 focus:border-transparent"
              />
            </div>
            <div>
              <label htmlFor="name" className="block text-xs font-medium text-cv-stone-600 mb-1">
                {STRINGS.app.displayName}
              </label>
              <input
                id="name" type="text" value={displayName} onChange={(e) => setDisplayName(e.target.value)}
                className="w-full border border-cv-warm-300 rounded px-3 py-2 text-sm text-cv-stone-900 focus:outline-none focus:ring-2 focus:ring-cv-emerald-500 focus:border-transparent"
              />
            </div>
            <div>
              <label htmlFor="password" className="block text-xs font-medium text-cv-stone-600 mb-1">
                {STRINGS.app.password}
              </label>
              <input
                id="password" type="password" value={password} onChange={(e) => setPassword(e.target.value)}
                required minLength={8}
                className="w-full border border-cv-warm-300 rounded px-3 py-2 text-sm text-cv-stone-900 focus:outline-none focus:ring-2 focus:ring-cv-emerald-500 focus:border-transparent"
              />
            </div>
            <div>
              <label htmlFor="confirmPw" className="block text-xs font-medium text-cv-stone-600 mb-1">
                {STRINGS.app.confirmPassword}
              </label>
              <input
                id="confirmPw" type="password" value={confirmPw} onChange={(e) => setConfirmPw(e.target.value)}
                required minLength={8}
                className="w-full border border-cv-warm-300 rounded px-3 py-2 text-sm text-cv-stone-900 focus:outline-none focus:ring-2 focus:ring-cv-emerald-500 focus:border-transparent"
              />
            </div>

            {error && (
              <p className="text-xs text-cv-red-600 bg-cv-red-50 border border-cv-red-200 rounded px-3 py-2">
                {error}
              </p>
            )}

            <button
              type="submit" disabled={loading}
              className="w-full bg-cv-emerald-600 text-white rounded px-5 py-2.5 text-sm font-medium hover:bg-cv-emerald-700 transition-colors disabled:opacity-50"
            >
              {loading ? 'Creating account\u2026' : STRINGS.app.createAccountButton}
            </button>
          </form>
        )}

        <p className="text-xs text-cv-stone-500">
          {STRINGS.app.alreadyHaveAccount}{' '}
          <a href="/" className="text-cv-emerald-600 hover:text-cv-emerald-700 font-medium">
            {STRINGS.app.signInLink}
          </a>
        </p>
      </div>
    </main>
  );
}

export default function RegisterPage() {
  return (
    <Suspense fallback={<div className="min-h-screen flex items-center justify-center bg-cv-warm-100"><p className="text-cv-stone-500">Loading...</p></div>}>
      <RegisterForm />
    </Suspense>
  );
}

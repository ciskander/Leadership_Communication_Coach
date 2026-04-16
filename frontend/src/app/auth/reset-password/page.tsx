'use client';

import { useState, Suspense } from 'react';
import { useSearchParams } from 'next/navigation';
import { api } from '@/lib/api';
import { STRINGS } from '@/config/strings';
import { ClearVoiceLogo } from '@/components/ClearVoiceLogo';

function ResetPasswordForm() {
  const params = useSearchParams();
  const token = params.get('token');

  const [password, setPassword] = useState('');
  const [confirmPw, setConfirmPw] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState(false);
  const [loading, setLoading] = useState(false);

  if (!token) {
    return (
      <main className="min-h-screen flex items-center justify-center bg-cv-warm-100">
        <div className="bg-white rounded border border-cv-warm-300 shadow-sm p-10 max-w-sm w-full text-center space-y-6">
          <p className="text-sm text-cv-red-600">{STRINGS.app.resetPasswordError}</p>
          <a href="/" className="text-sm text-cv-teal-600 hover:text-cv-teal-700 font-medium">
            {STRINGS.app.backToSignIn}
          </a>
        </div>
      </main>
    );
  }

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
      await api.resetPassword(token, password);
      setSuccess(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : STRINGS.app.resetPasswordError);
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
          {STRINGS.app.resetPasswordHeading}
        </h1>

        {success ? (
          <div className="space-y-4">
            <p className="text-sm text-cv-teal-700 bg-cv-teal-50 border border-cv-teal-200 rounded px-4 py-3">
              {STRINGS.app.resetPasswordSuccess}
            </p>
            <a href="/" className="inline-block text-sm text-cv-teal-600 hover:text-cv-teal-700 font-medium">
              {STRINGS.app.signInLink}
            </a>
          </div>
        ) : (
          <form onSubmit={handleSubmit} className="space-y-4 text-left">
            <div>
              <label htmlFor="password" className="block text-xs font-medium text-cv-stone-600 mb-1">
                {STRINGS.app.newPassword}
              </label>
              <input
                id="password" type="password" value={password} onChange={(e) => setPassword(e.target.value)}
                required minLength={8}
                className="w-full border border-cv-warm-300 rounded px-3 py-2 text-sm text-cv-stone-900 focus:outline-none focus:ring-2 focus:ring-cv-teal-500 focus:border-transparent"
              />
            </div>
            <div>
              <label htmlFor="confirmPw" className="block text-xs font-medium text-cv-stone-600 mb-1">
                {STRINGS.app.confirmNewPassword}
              </label>
              <input
                id="confirmPw" type="password" value={confirmPw} onChange={(e) => setConfirmPw(e.target.value)}
                required minLength={8}
                className="w-full border border-cv-warm-300 rounded px-3 py-2 text-sm text-cv-stone-900 focus:outline-none focus:ring-2 focus:ring-cv-teal-500 focus:border-transparent"
              />
            </div>

            {error && (
              <p className="text-xs text-cv-red-600 bg-cv-red-50 border border-cv-red-200 rounded px-3 py-2">
                {error}
              </p>
            )}

            <button
              type="submit" disabled={loading}
              className="w-full bg-cv-teal-600 text-white rounded px-5 py-2.5 text-sm font-medium hover:bg-cv-teal-700 transition-colors disabled:opacity-50"
            >
              {loading ? 'Resetting\u2026' : STRINGS.app.resetPasswordButton}
            </button>
          </form>
        )}

        <a href="/" className="inline-block text-xs text-cv-stone-500 hover:text-cv-teal-600 transition-colors">
          {STRINGS.app.backToSignIn}
        </a>
      </div>
    </main>
  );
}

export default function ResetPasswordPage() {
  return (
    <Suspense fallback={<div className="min-h-screen flex items-center justify-center bg-cv-warm-100"><p className="text-cv-stone-500">Loading...</p></div>}>
      <ResetPasswordForm />
    </Suspense>
  );
}

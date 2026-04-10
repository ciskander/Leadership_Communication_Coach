'use client';

import { useState } from 'react';
import { api } from '@/lib/api';
import { STRINGS } from '@/config/strings';
import { ClearVoiceLogo } from '@/components/ClearVoiceLogo';

export default function ForgotPasswordPage() {
  const [email, setEmail] = useState('');
  const [sent, setSent] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      await api.forgotPassword(email);
      setSent(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Something went wrong.');
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

        <div className="space-y-2">
          <h1 className="text-xl font-semibold text-cv-stone-900 font-serif">
            {STRINGS.app.forgotPasswordHeading}
          </h1>
          <p className="text-sm text-cv-stone-500">
            {STRINGS.app.forgotPasswordSubheading}
          </p>
        </div>

        {sent ? (
          <div className="space-y-4">
            <p className="text-sm text-cv-emerald-700 bg-cv-emerald-50 border border-cv-emerald-200 rounded px-4 py-3">
              {STRINGS.app.forgotPasswordSent}
            </p>
            <a href="/" className="inline-block text-sm text-cv-emerald-600 hover:text-cv-emerald-700 font-medium">
              {STRINGS.app.backToSignIn}
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

            {error && (
              <p className="text-xs text-cv-red-600 bg-cv-red-50 border border-cv-red-200 rounded px-3 py-2">
                {error}
              </p>
            )}

            <button
              type="submit" disabled={loading}
              className="w-full bg-cv-emerald-600 text-white rounded px-5 py-2.5 text-sm font-medium hover:bg-cv-emerald-700 transition-colors disabled:opacity-50"
            >
              {loading ? 'Sending\u2026' : STRINGS.app.sendResetLink}
            </button>
          </form>
        )}

        <a href="/" className="inline-block text-xs text-cv-stone-500 hover:text-cv-emerald-600 transition-colors">
          {STRINGS.app.backToSignIn}
        </a>
      </div>
    </main>
  );
}

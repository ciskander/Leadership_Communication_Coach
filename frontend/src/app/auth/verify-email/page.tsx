'use client';

import { useEffect, useState, Suspense } from 'react';
import { useSearchParams } from 'next/navigation';
import { api } from '@/lib/api';
import { STRINGS } from '@/config/strings';
import { ClearVoiceLogo } from '@/components/ClearVoiceLogo';

function VerifyEmailContent() {
  const params = useSearchParams();
  const token = params.get('token');
  const [status, setStatus] = useState<'loading' | 'success' | 'error'>('loading');
  const [message, setMessage] = useState('');

  useEffect(() => {
    if (!token) {
      setStatus('error');
      setMessage(STRINGS.app.verifyEmailError);
      return;
    }
    api.verifyEmail(token)
      .then((r) => {
        setStatus('success');
        setMessage(r.message || STRINGS.app.verifyEmailSuccess);
      })
      .catch((e) => {
        setStatus('error');
        setMessage(e instanceof Error ? e.message : STRINGS.app.verifyEmailError);
      });
  }, [token]);

  return (
    <main className="min-h-screen flex items-center justify-center bg-cv-warm-100">
      <div className="bg-white rounded border border-cv-warm-300 shadow-sm p-10 max-w-sm w-full text-center space-y-6">
        <div className="flex justify-center">
          <ClearVoiceLogo className="h-10 w-auto" />
        </div>

        <h1 className="text-xl font-semibold text-cv-stone-900 font-serif">
          {STRINGS.app.verifyEmailHeading}
        </h1>

        {status === 'loading' && (
          <p className="text-sm text-cv-stone-500">{STRINGS.app.verifyingEmail}</p>
        )}

        {status === 'success' && (
          <div className="space-y-4">
            <p className="text-sm text-cv-teal-700 bg-cv-teal-50 border border-cv-teal-200 rounded px-4 py-3">
              {message}
            </p>
            <a href="/" className="inline-block text-sm text-cv-teal-600 hover:text-cv-teal-700 font-medium">
              {STRINGS.app.signInLink}
            </a>
          </div>
        )}

        {status === 'error' && (
          <div className="space-y-4">
            <p className="text-sm text-cv-red-600 bg-cv-red-50 border border-cv-red-200 rounded px-4 py-3">
              {message}
            </p>
            <a href="/" className="inline-block text-sm text-cv-teal-600 hover:text-cv-teal-700 font-medium">
              {STRINGS.app.backToSignIn}
            </a>
          </div>
        )}
      </div>
    </main>
  );
}

export default function VerifyEmailPage() {
  return (
    <Suspense fallback={<div className="min-h-screen flex items-center justify-center bg-cv-warm-100"><p className="text-cv-stone-500">Loading...</p></div>}>
      <VerifyEmailContent />
    </Suspense>
  );
}

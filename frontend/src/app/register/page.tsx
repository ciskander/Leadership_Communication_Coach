'use client';

import { useEffect, Suspense } from 'react';
import { useSearchParams } from 'next/navigation';

function RegisterRedirect() {
  const searchParams = useSearchParams();
  const inviteToken = searchParams.get('invite_token');

  useEffect(() => {
    // Same-origin — Next.js proxy forwards to backend
    const loginUrl = inviteToken
      ? `/api/auth/login?invite_token=${encodeURIComponent(inviteToken)}`
      : `/api/auth/login`;
    window.location.href = loginUrl;
  }, [inviteToken]);

  return null;
}

export default function RegisterPage() {
  return (
    <div className="flex items-center justify-center min-h-screen bg-stone-50">
      <div className="text-center space-y-3">
        <div className="w-8 h-8 border-2 border-emerald-600 border-t-transparent rounded-full animate-spin mx-auto" />
        <p className="text-sm text-stone-500">Redirecting to sign in…</p>
        <Suspense>
          <RegisterRedirect />
        </Suspense>
      </div>
    </div>
  );
}
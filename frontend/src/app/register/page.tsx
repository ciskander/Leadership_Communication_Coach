'use client';

import { useEffect, Suspense } from 'react';
import { useSearchParams } from 'next/navigation';

function RegisterRedirect() {
  const searchParams = useSearchParams();
  const inviteToken  = searchParams.get('invite_token');

  useEffect(() => {
    // Redirect to the new registration page (supports email/password + OAuth)
    const registerUrl = inviteToken
      ? `/auth/register?invite_token=${encodeURIComponent(inviteToken)}`
      : `/auth/register`;
    window.location.href = registerUrl;
  }, [inviteToken]);

  return null;
}

export default function RegisterPage() {
  return (
    <div className="flex items-center justify-center min-h-screen bg-cv-warm-100">
      <div className="text-center space-y-3">
        <span className="w-8 h-8 border-2 border-cv-teal-600 border-t-transparent rounded-full animate-spin mx-auto block" />
        <p className="text-sm text-cv-stone-500">Redirecting...</p>
        <Suspense>
          <RegisterRedirect />
        </Suspense>
      </div>
    </div>
  );
}

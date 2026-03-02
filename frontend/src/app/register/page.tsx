'use client';

import { useEffect } from 'react';
import { useSearchParams } from 'next/navigation';

const BASE_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

export default function RegisterPage() {
  const searchParams = useSearchParams();
  const inviteToken = searchParams.get('invite_token');

  useEffect(() => {
    // Redirect to backend OAuth login, carrying the invite token
    const loginUrl = inviteToken
      ? `${BASE_URL}/api/auth/login?invite_token=${encodeURIComponent(inviteToken)}`
      : `${BASE_URL}/api/auth/login`;
    window.location.href = loginUrl;
  }, [inviteToken]);

  return (
    <div className="flex items-center justify-center min-h-screen bg-stone-50">
      <div className="text-center space-y-3">
        <div className="w-8 h-8 border-2 border-emerald-600 border-t-transparent rounded-full animate-spin mx-auto" />
        <p className="text-sm text-stone-500">Redirecting to sign in…</p>
      </div>
    </div>
  );
}
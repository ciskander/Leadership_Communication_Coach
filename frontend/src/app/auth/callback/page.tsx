'use client';

import { useEffect } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { api } from '@/lib/api';

export default function AuthCallbackPage() {
  const router = useRouter();
  const params = useSearchParams();

  useEffect(() => {
    api.me().then((user) => {
      const returnTo = params.get('return_to');
      if (returnTo && returnTo.startsWith('/')) {
        router.push(returnTo);
      } else if (user.role === 'coach') {
        router.push('/coach');
      } else if (user.role === 'admin') {
        router.push('/admin');
      } else {
        router.push('/client');
      }
    }).catch(() => {
      router.push('/');
    });
  }, [router, params]);

  return (
    <div className="min-h-screen flex items-center justify-center">
      <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-indigo-600" />
    </div>
  );
}

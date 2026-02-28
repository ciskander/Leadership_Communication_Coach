'use client';

import { AuthContext, useAuthFetch } from '@/hooks/useAuth';
import { Navbar } from '@/components/Layout/Navbar';
import { Sidebar } from '@/components/Layout/Sidebar';
import { useEffect } from 'react';
import { useRouter } from 'next/navigation';

export default function CoachLayout({ children }: { children: React.ReactNode }) {
  const auth = useAuthFetch();
  const router = useRouter();

  useEffect(() => {
    if (!auth.loading) {
      if (!auth.user) router.push('/');
      else if (auth.user.role !== 'coach' && auth.user.role !== 'admin') router.push('/client');
    }
  }, [auth.loading, auth.user, router]);

  return (
    <AuthContext.Provider value={auth}>
      <div className="flex flex-col min-h-screen">
        <Navbar />
        <div className="flex flex-1">
          <Sidebar />
          <main className="flex-1 p-6 bg-gray-50 overflow-y-auto">{children}</main>
        </div>
      </div>
    </AuthContext.Provider>
  );
}

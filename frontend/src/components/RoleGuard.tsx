'use client';

import { useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { useAuth } from '@/hooks/useAuth';
import type { User } from '@/lib/types';

interface RoleGuardProps {
  allowedRoles: User['role'][];
  children: React.ReactNode;
  fallbackPath?: string;
}

export function RoleGuard({
  allowedRoles,
  children,
  fallbackPath = '/',
}: RoleGuardProps) {
  const { user, loading } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (!loading) {
      if (!user) {
        router.push('/');
      } else if (!allowedRoles.includes(user.role)) {
        router.push(fallbackPath);
      }
    }
  }, [user, loading, allowedRoles, fallbackPath, router]);

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-screen">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-indigo-600" />
      </div>
    );
  }

  if (!user || !allowedRoles.includes(user.role)) return null;

  return <>{children}</>;
}

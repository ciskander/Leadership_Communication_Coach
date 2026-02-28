'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { useAuth } from '@/hooks/useAuth';
import { clsx } from 'clsx';

interface NavItem {
  href: string;
  label: string;
  roles: string[];
}

const navItems: NavItem[] = [
  { href: '/client', label: 'Dashboard', roles: ['coachee'] },
  { href: '/client/analyze', label: 'Analyze Meeting', roles: ['coachee'] },
  { href: '/client/experiment', label: 'My Experiment', roles: ['coachee'] },
  { href: '/coach', label: 'Coachees', roles: ['coach'] },
  { href: '/admin', label: 'Users', roles: ['admin'] },
];

export function Sidebar() {
  const { user } = useAuth();
  const pathname = usePathname();

  const items = navItems.filter((item) =>
    user ? item.roles.includes(user.role) : false
  );

  return (
    <aside className="w-56 min-h-screen bg-gray-50 border-r border-gray-200 pt-6 px-3 flex flex-col gap-1">
      {items.map((item) => (
        <Link
          key={item.href}
          href={item.href}
          className={clsx(
            'px-3 py-2 rounded-md text-sm font-medium transition-colors',
            pathname === item.href || pathname.startsWith(item.href + '/')
              ? 'bg-indigo-100 text-indigo-700'
              : 'text-gray-600 hover:bg-gray-100'
          )}
        >
          {item.label}
        </Link>
      ))}
    </aside>
  );
}

'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { useAuth } from '@/hooks/useAuth';

interface NavItem {
  href: string;
  label: string;
  icon: string;
  roles: string[];
}

const navItems: NavItem[] = [
  { href: '/client',            label: 'Home',            icon: '🏠',  roles: ['coachee'] },
  { href: '/client/baseline',   label: 'Baseline Pack',   icon: '📚',  roles: ['coachee'] },
  { href: '/client/analyze',    label: 'Analyze Meeting', icon: '✨',  roles: ['coachee'] },
  { href: '/client/experiment', label: 'My Experiment',   icon: '🧪',  roles: ['coachee'] },
  { href: '/client/progress',   label: 'Progress',        icon: '📈',  roles: ['coachee'] },
  { href: '/coach',             label: 'My Coachees',     icon: '🧑‍🎓',  roles: ['coach'] },
  { href: '/coach/analyze',     label: 'Run Analysis',    icon: '✨',  roles: ['coach'] },
  { href: '/admin',             label: 'Users',           icon: '👥',  roles: ['admin'] },
];

const roleColors: Record<string, { dot: string; label: string }> = {
  coachee: { dot: 'bg-emerald-500', label: 'text-emerald-700' },
  coach:   { dot: 'bg-blue-500',   label: 'text-blue-700' },
  admin:   { dot: 'bg-amber-500',  label: 'text-amber-700' },
};

export function Sidebar() {
  const { user } = useAuth();
  const pathname = usePathname();

  const items = navItems.filter((item) =>
    user ? item.roles.includes(user.role) : false
  );

  const colors = roleColors[user?.role ?? 'coachee'];

  return (
    <aside className="w-52 min-h-screen bg-stone-50 border-r border-stone-200 flex flex-col">
      {/* Role badge */}
      <div className="px-4 pt-5 pb-4">
        <div className="flex items-center gap-2">
          <span className={`w-1.5 h-1.5 rounded-full ${colors.dot}`} />
          <span className={`text-xs font-semibold uppercase tracking-widest ${colors.label}`}>
            {user?.role ?? ''}
          </span>
        </div>
      </div>

      {/* Nav items */}
      <nav className="flex-1 px-2 space-y-0.5">
        {items.map((item) => {
          const active =
            pathname === item.href ||
            (item.href !== '/client' && item.href !== '/coach' && item.href !== '/admin' &&
              pathname.startsWith(item.href));
          return (
            <Link
              key={item.href}
              href={item.href}
              className={`flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm transition-all ${
                active
                  ? 'bg-emerald-600 text-white shadow-sm'
                  : 'text-stone-600 hover:bg-stone-100 hover:text-stone-900'
              }`}
            >
              <span className="text-base leading-none opacity-75">{item.icon}</span>
              <span className="font-medium">{item.label}</span>
            </Link>
          );
        })}
      </nav>

      {/* Bottom hint */}
      <div className="px-4 py-5">
        <p className="text-xs text-stone-400 leading-relaxed">
          ClearVoice helps you become a more effective communicator, one meeting at a time.
        </p>
      </div>
    </aside>
  );
}

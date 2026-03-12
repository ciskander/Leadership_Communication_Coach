'use client';

import Link from 'next/link';
import { usePathname, useRouter } from 'next/navigation';
import { useAuth } from '@/hooks/useAuth';
import { STRINGS } from '@/config/strings';
import { resetOnboarding } from '@/lib/onboarding';

interface NavItem {
  href: string;
  label: string;
  icon: string;
  roles: string[];
}

const navItems: NavItem[] = [
  { href: '/client',            label: STRINGS.nav.home,            icon: '🏠',  roles: ['coachee'] },
  { href: '/client/baseline',   label: STRINGS.nav.baselinePack,   icon: '📚',  roles: ['coachee'] },
  { href: '/client/analyze',    label: STRINGS.nav.analyzeMeeting, icon: '✨',  roles: ['coachee'] },
  { href: '/client/experiment', label: STRINGS.nav.myExperiment,   icon: '🧪',  roles: ['coachee'] },
  { href: '/client/progress',   label: STRINGS.nav.progress,        icon: '📈',  roles: ['coachee'] },
  { href: '/coach',             label: STRINGS.nav.myCoachees,     icon: '🧑‍🎓',  roles: ['coach'] },
  { href: '/coach/analyze',     label: STRINGS.nav.runAnalysis,    icon: '✨',  roles: ['coach'] },
  { href: '/admin',             label: STRINGS.nav.users,           icon: '👥',  roles: ['admin'] },
];

const roleColors: Record<string, { dot: string; label: string }> = {
  coachee: { dot: 'bg-emerald-500', label: 'text-emerald-700' },
  coach:   { dot: 'bg-blue-500',   label: 'text-blue-700' },
  admin:   { dot: 'bg-amber-500',  label: 'text-amber-700' },
};

export function Sidebar() {
  const { user } = useAuth();
  const pathname = usePathname();
  const router = useRouter();

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

      {/* Bottom */}
      <div className="px-4 py-5 space-y-3">
        {user?.role === 'coachee' && (
          <button
            onClick={() => {
              resetOnboarding();
              router.push('/client/welcome');
            }}
            className="flex items-center gap-1.5 text-xs text-stone-400 hover:text-emerald-600 transition-colors"
          >
            <svg className="w-3.5 h-3.5" viewBox="0 0 20 20" fill="currentColor">
              <path fillRule="evenodd" d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zM8.94 6.94a.75.75 0 11-1.061-1.061 3 3 0 112.871 5.026v.345a.75.75 0 01-1.5 0v-.916c0-.414.336-.75.75-.75a1.5 1.5 0 10-1.06-2.56zM10 15a1 1 0 100-2 1 1 0 000 2z" clipRule="evenodd" />
            </svg>
            {STRINGS.onboarding.replayOnboarding}
          </button>
        )}
        <p className="text-xs text-stone-400 leading-relaxed">
          {STRINGS.brand.sidebarHint}
        </p>
      </div>
    </aside>
  );
}

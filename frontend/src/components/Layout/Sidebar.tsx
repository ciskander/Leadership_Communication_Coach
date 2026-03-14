'use client';

import Link from 'next/link';
import { usePathname, useRouter } from 'next/navigation';
import { useAuth } from '@/hooks/useAuth';
import { STRINGS } from '@/config/strings';
import { resetOnboarding } from '@/lib/onboarding';

// ─── Icon helper ─────────────────────────────────────────────────────────────
// All icons use a 24×24 stroke viewport. One or two path strings per icon.
// This keeps the NavItem type simple (icon: string | string[]) while producing
// clean, weight-consistent SVG output.

function NavIcon({ paths, className = '' }: { paths: string | string[]; className?: string }) {
  const pathArr = typeof paths === 'string' ? [paths] : paths;
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.7}
      strokeLinecap="round"
      strokeLinejoin="round"
      className={`w-[15px] h-[15px] shrink-0 ${className}`}
      aria-hidden="true"
    >
      {pathArr.map((d, i) => (
        <path key={i} d={d} />
      ))}
    </svg>
  );
}

// ─── Icon path library ────────────────────────────────────────────────────────

const ICONS = {
  home:       'M3 9.5L12 3L21 9.5V19.4C21 19.73 20.73 20 20.4 20H15V15H9V20H3.6C3.27 20 3 19.73 3 19.4V9.5Z',
  book:       [
    'M12 2L3 7L12 12L21 7L12 2Z',
    'M3 12L12 17L21 12',
    'M3 17L12 22L21 17',
  ],
  sparkles:   [
    'M9 3L10.5 7.5L15 9L10.5 10.5L9 15L7.5 10.5L3 9L7.5 7.5L9 3Z',
    'M19 13L19.75 15.25L22 16L19.75 16.75L19 19L18.25 16.75L16 16L18.25 15.25L19 13Z',
  ],
  beaker:     [
    'M9 3H15',
    'M9 3V9L4 18H20L15 9V3',
    'M7.5 14H16.5',
  ],
  trendingUp: [
    'M3 17L9 11L13 15L21 7',
    'M15 7H21V13',
  ],
  users:      [
    'M17 20C17 18 14.76 16 12 16C9.24 16 7 18 7 20',
    'M12 13C13.66 13 15 11.66 15 10C15 8.34 13.66 7 12 7C10.34 7 9 8.34 9 10C9 11.66 10.34 13 12 13Z',
    'M21 20C21 18.5 19.5 17.25 17.5 16.75',
    'M17.5 10C17.5 11.38 16.72 12.58 15.57 13.19',
  ],
  admin:      [
    'M12 2L3 7L12 12L21 7L12 2Z',
    'M3 17L12 22L21 17',
    'M3 12L12 17L21 12',
  ],
} satisfies Record<string, string | string[]>;

// ─── Nav items ────────────────────────────────────────────────────────────────

interface NavItem {
  href: string;
  label: string;
  iconKey: keyof typeof ICONS;
  roles: string[];
}

const navItems: NavItem[] = [
  { href: '/client',            label: STRINGS.nav.home,            iconKey: 'home',       roles: ['coachee'] },
  { href: '/client/baseline',   label: STRINGS.nav.baselinePack,    iconKey: 'book',       roles: ['coachee'] },
  { href: '/client/analyze',    label: STRINGS.nav.analyzeMeeting,  iconKey: 'sparkles',   roles: ['coachee'] },
  { href: '/client/experiment', label: STRINGS.nav.myExperiment,    iconKey: 'beaker',     roles: ['coachee'] },
  { href: '/client/progress',   label: STRINGS.nav.progress,        iconKey: 'trendingUp', roles: ['coachee'] },
  { href: '/coach',             label: STRINGS.nav.myCoachees,      iconKey: 'users',      roles: ['coach']   },
  { href: '/coach/analyze',     label: STRINGS.nav.runAnalysis,     iconKey: 'sparkles',   roles: ['coach']   },
  { href: '/admin',             label: STRINGS.nav.users,           iconKey: 'admin',      roles: ['admin']   },
];

// ─── Role badge colour ramp ───────────────────────────────────────────────────
// Uses cv-* tokens from tailwind.tokens.ts
const roleColors: Record<string, { dot: string; label: string }> = {
  coachee: { dot: 'bg-cv-teal-500',   label: 'text-cv-teal-700'  },
  coach:   { dot: 'bg-blue-500',      label: 'text-[#1E3A5F]'    },
  admin:   { dot: 'bg-cv-amber-500',  label: 'text-cv-amber-700' },
};

// ─── Component ────────────────────────────────────────────────────────────────

export function Sidebar() {
  const { user }   = useAuth();
  const pathname   = usePathname();
  const router     = useRouter();

  const items  = navItems.filter((item) => (user ? item.roles.includes(user.role) : false));
  const colors = roleColors[user?.role ?? 'coachee'];

  return (
    <aside className="w-52 min-h-screen bg-cv-warm-50 border-r border-cv-warm-200 flex flex-col">

      {/* ── Role badge ── */}
      <div className="px-5 pt-5 pb-4">
        <div className="flex items-center gap-2">
          <span className={`w-1.5 h-1.5 rounded-full ${colors.dot}`} />
          <span className={`text-2xs font-semibold uppercase tracking-[0.18em] ${colors.label}`}>
            {user?.role ?? ''}
          </span>
        </div>
      </div>

      {/* ── Nav items ── */}
      <nav className="flex-1 px-3 space-y-0.5">
        {items.map((item) => {
          const active =
            pathname === item.href ||
            (item.href !== '/client' &&
              item.href !== '/coach' &&
              item.href !== '/admin' &&
              pathname.startsWith(item.href));

          return (
            <Link
              key={item.href}
              href={item.href}
              className={[
                'flex items-center gap-2.5 px-3 py-2.5 rounded-lg text-sm transition-all duration-150',
                active
                  ? 'bg-cv-teal-600 text-white shadow-sm'
                  : 'text-cv-stone-500 hover:bg-cv-warm-100 hover:text-cv-stone-800',
              ].join(' ')}
            >
              <NavIcon
                paths={ICONS[item.iconKey]}
                className={active ? 'opacity-90' : 'opacity-60'}
              />
              <span className="font-medium leading-none">{item.label}</span>
            </Link>
          );
        })}
      </nav>

      {/* ── Bottom: replay onboarding + hint ── */}
      <div className="px-5 py-5 space-y-3 border-t border-cv-warm-200">
        {user?.role === 'coachee' && (
          <button
            onClick={() => {
              resetOnboarding();
              router.push('/client/welcome');
            }}
            className="flex items-center gap-1.5 text-2xs text-cv-stone-400 hover:text-cv-teal-600 transition-colors"
          >
            {/* Question-circle icon */}
            <svg
              viewBox="0 0 20 20"
              fill="currentColor"
              className="w-3.5 h-3.5 shrink-0"
              aria-hidden="true"
            >
              <path
                fillRule="evenodd"
                d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zM8.94 6.94a.75.75 0 11-1.061-1.061 3 3 0 112.871 5.026v.345a.75.75 0 01-1.5 0v-.916c0-.414.336-.75.75-.75a1.5 1.5 0 10-1.06-2.56zM10 15a1 1 0 100-2 1 1 0 000 2z"
                clipRule="evenodd"
              />
            </svg>
            {STRINGS.onboarding.replayOnboarding}
          </button>
        )}

        <p className="text-2xs text-cv-stone-400 leading-relaxed">
          {STRINGS.brand.sidebarHint}
        </p>
      </div>
    </aside>
  );
}

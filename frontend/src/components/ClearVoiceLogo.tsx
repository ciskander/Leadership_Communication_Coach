import { STRINGS } from '@/config/strings';

interface ClearVoiceLogoProps {
  /** Tailwind className forwarded to the <svg> element */
  className?: string;
  /**
   * 'full'  → mark + wordmark + subtitle  (default; used in Navbar)
   * 'mark'  → icon-only square mark       (reserved for future compact use)
   */
  variant?: 'full' | 'mark';
}

/**
 * ClearVoiceLogo — redesigned for the "calm meets McKinsey" design system.
 *
 * Mark:      Flat teal (#0F6E56) speech bubble · white person silhouette ·
 *            amber (#D97706) upward-trend arrow extending past the bubble edge
 * Wordmark:  DM Serif Display (via CSS var --font-serif) · "Clear" charcoal · "Voice" teal
 * Subtitle:  DM Sans small-caps · stone-400
 *
 * The component relies on --font-serif and --font-sans CSS variables
 * injected by Next.js next/font in layout.tsx.
 */
export function ClearVoiceLogo({ className = '', variant = 'full' }: ClearVoiceLogoProps) {
  // ─── Shared mark geometry ────────────────────────────────────────────────
  // Lives in a 65×60 local coordinate space and is translated/scaled by the
  // parent <svg> viewBox.
  const mark = (
    <g>
      {/* ── Speech bubble body (flat teal) ── */}
      <path
        d="M11,2 H45 Q55,2 55,12 V37 Q55,47 45,47 H32 L24,58 L26,47 H11 Q1,47 1,37 V12 Q1,2 11,2 Z"
        fill="#0F6E56"
      />

      {/* ── Person: head ── */}
      <circle cx="28" cy="20" r="6.5" fill="white" fillOpacity="0.9" />

      {/* ── Person: shoulders (clips naturally at bubble bottom) ── */}
      <path
        d="M13,46 Q13,34 28,34 Q43,34 43,46"
        fill="white"
        fillOpacity="0.82"
      />

      {/* ── Upward-trend arrow in amber ── */}
      {/* Shaft — rises from lower-right body area, exits bubble boundary */}
      <line
        x1="40" y1="34"
        x2="58" y2="8"
        stroke="#D97706"
        strokeWidth="2.4"
        strokeLinecap="round"
      />
      {/* Arrowhead — tip at (58,3), intentionally extends beyond bubble */}
      <polygon points="58,3 65,14 51,14" fill="#D97706" />
    </g>
  );

  // ─── Mark-only variant ────────────────────────────────────────────────────
  if (variant === 'mark') {
    return (
      <svg
        viewBox="0 0 65 60"
        fill="none"
        xmlns="http://www.w3.org/2000/svg"
        className={className}
        aria-label={STRINGS.brand.logoAriaLabel}
      >
        {mark}
      </svg>
    );
  }

  // ─── Full logo (mark + wordmark + subtitle) ───────────────────────────────
  return (
    <svg
      viewBox="0 0 294 60"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      className={className}
      aria-label={STRINGS.brand.logoAriaLabel}
    >
      {mark}

      {/* ── Wordmark: "Clear" (charcoal) + "Voice" (teal) ── */}
      <text
        x="76"
        y="37"
        fontFamily="var(--font-serif), 'DM Serif Display', Georgia, serif"
        fontWeight="400"
        fontSize="30"
        letterSpacing="-0.4"
      >
        <tspan fill="#1C1917">{STRINGS.brand.wordmarkLeft}</tspan>
        <tspan fill="#0F6E56">{STRINGS.brand.wordmarkRight}</tspan>
      </text>

      {/* ── Subtitle: small tracked caps ── */}
      <text
        x="78"
        y="52"
        fontFamily="var(--font-sans), 'DM Sans', system-ui, sans-serif"
        fontWeight="500"
        fontSize="7.5"
        fill="#A8A29E"
        letterSpacing="1.7"
        textLength="208"
        lengthAdjust="spacingAndGlyphs"
      >
        {STRINGS.brand.subtitle}
      </text>
    </svg>
  );
}

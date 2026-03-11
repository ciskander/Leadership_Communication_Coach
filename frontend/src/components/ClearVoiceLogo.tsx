import { STRINGS } from '@/config/strings';

export function ClearVoiceLogo({ className = '' }: { className?: string }) {
  return (
    <svg
      viewBox="0 0 280 64"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      className={className}
      aria-label={STRINGS.brand.logoAriaLabel}
    >
      <defs>
        {/* Bubble gradient: teal left → blue right */}
        <linearGradient id="bubbleGrad" x1="0%" y1="0%" x2="100%" y2="100%">
          <stop offset="0%" stopColor="#2abfbf" />
          <stop offset="100%" stopColor="#1a6fc4" />
        </linearGradient>
        {/* Arrow gradient: teal → green */}
        <linearGradient id="arrowGrad" x1="0%" y1="100%" x2="100%" y2="0%">
          <stop offset="0%" stopColor="#2abfbf" />
          <stop offset="100%" stopColor="#4ab53e" />
        </linearGradient>
      </defs>

      {/* ── Speech bubble body ── */}
      <path
        d="M4 8 Q4 2 10 2 H46 Q52 2 52 8 V36 Q52 42 46 42 H28 L18 54 L20 42 H10 Q4 42 4 36 Z"
        fill="url(#bubbleGrad)"
      />

      {/* ── Person icon (head + shoulders) ── */}
      {/* Head */}
      <circle cx="28" cy="16" r="6" fill="white" fillOpacity="0.9" />
      {/* Shoulders */}
      <path
        d="M14 38 Q14 28 28 28 Q42 28 42 38"
        fill="white"
        fillOpacity="0.9"
      />

      {/* ── Upward arrow (overlaid, top-right of bubble) ── */}
      <g transform="translate(30, 4)">
        {/* Arrow shaft */}
        <line x1="10" y1="22" x2="18" y2="6" stroke="url(#arrowGrad)" strokeWidth="3" strokeLinecap="round" />
        {/* Arrow head */}
        <polygon points="18,2 24,12 12,12" fill="#4ab53e" />
      </g>

      {/* ── Wordmark: "Clear" in blue ── */}
      <text
        x="60"
        y="34"
        fontFamily="'Arial Black', 'Arial Bold', Arial, sans-serif"
        fontWeight="900"
        fontSize="26"
        fill="#1a6fc4"
        letterSpacing="-0.5"
      >
        {STRINGS.brand.wordmarkLeft}
      </text>

      {/* ── Wordmark: "Voice" in green ── */}
      <text
        x="122"
        y="34"
        fontFamily="'Arial Black', 'Arial Bold', Arial, sans-serif"
        fontWeight="900"
        fontSize="26"
        fill="#4ab53e"
        letterSpacing="-0.5"
      >
        {STRINGS.brand.wordmarkRight}
      </text>

      {/* ── Subtitle ── */}
      <text
        x="61"
        y="48"
        fontFamily="Arial, sans-serif"
        fontWeight="400"
        fontSize="8.5"
        fill="#888888"
        letterSpacing="1.8"
      >
        {STRINGS.brand.subtitle}
      </text>
    </svg>
  );
}

/**
 * ClearVoice Design Tokens
 *
 * This file is the single source of truth for the cv.* color ramps.
 * The values here must stay in sync with tailwind.config.ts.
 *
 * Usage in tailwind.config.ts:
 *   import { cvTokens } from './tailwind.tokens'
 *   export default { content: [...], theme: { extend: cvTokens } }
 *
 * For reference in non-Tailwind contexts (e.g. Recharts axis ticks,
 * Chart.js datasets) import individual ramps directly:
 *
 *   import { teal, warm, stone, amber, red } from './tailwind.tokens'
 *   stroke={teal[600]}
 */

// ── Individual ramps (importable for non-Tailwind use) ────────────────────────

export const teal = {
  50:  '#E1F5EE',
  100: '#9FE1CB',
  200: '#5DCAA5',
  300: '#2DB88A',
  400: '#1D9E75',
  500: '#158064',
  600: '#0F6E56',  // primary brand / CTA
  700: '#0C5848',
  800: '#085041',
  900: '#04342C',
} as const;

export const warm = {
  50:  '#FDFCF9',  // near-white body tint
  100: '#F7F5F0',  // main page background
  200: '#EFEDE7',  // card surfaces, borders
  300: '#E4E1D8',  // stronger borders, hover states
} as const;

export const stone = {
  50:  '#F1EFE8',
  100: '#D3D1C7',
  200: '#C0BDB2',
  300: '#A8A59A',
  400: '#888780',  // axis ticks, secondary labels
  500: '#726F68',  // muted body text
  600: '#5F5E5A',
  700: '#4D4C49',
  800: '#444441',
  900: '#2C2C2A',  // primary body text
} as const;

export const amber = {
  50:  '#FEF8EC',
  100: '#FAC775',
  200: '#F7B04C',
  400: '#EF9F27',
  500: '#D48820',
  600: '#BA7517',
  700: '#8F5910',
  800: '#6A4010',
} as const;

export const red = {
  50:  '#FDF2F2',
  100: '#F7C1C1',
  200: '#F09898',
  300: '#E87070',
  400: '#E24B4A',
  500: '#CC3635',
  600: '#A32D2D',
  700: '#7A2020',
} as const;

// ── Tailwind extend block ─────────────────────────────────────────────────────

export const cvTokens = {
  colors: {
    cv: {
      teal,
      warm: {
        ...warm,
        // Legacy named keys — prefer numeric steps in new code
        DEFAULT: warm[100],
        surface: warm[200],
        border:  'rgba(0,0,0,0.07)',
      },
      stone,
      amber,
      red,
    },
  },
  fontFamily: {
    // In Next.js use CSS variables (see tailwind.config.ts).
    // These hardcoded fallbacks are for non-Next.js usage.
    serif: ['DM Serif Display', 'Georgia', 'serif'],
    sans:  ['DM Sans', 'system-ui', 'sans-serif'],
  },
  fontSize: {
    '2xs': ['10px', { lineHeight: '1.4', letterSpacing: '0.08em' }],
    'xs':  ['11px', { lineHeight: '1.5' }],
    'sm':  ['13px', { lineHeight: '1.6' }],
    'base':['15px', { lineHeight: '1.65' }],
    'lg':  ['18px', { lineHeight: '1.4' }],
    'xl':  ['22px', { lineHeight: '1.3' }],
    '2xl': ['28px', { lineHeight: '1.2' }],
    '3xl': ['38px', { lineHeight: '1.15' }],
  },
  borderRadius: {
    'sm': '4px',
    'md': '6px',
    'lg': '10px',
    'xl': '14px',
  },
} as const;

import type { Config } from 'tailwindcss';

const config: Config = {
  content: [
    './src/pages/**/*.{js,ts,jsx,tsx,mdx}',
    './src/components/**/*.{js,ts,jsx,tsx,mdx}',
    './src/app/**/*.{js,ts,jsx,tsx,mdx}',
  ],
  theme: {
    extend: {
      colors: {
        cv: {

          // ── Teal — primary brand ramp ────────────────────────────────────
          teal: {
            50:  '#E1F5EE',
            100: '#9FE1CB',
            200: '#5DCAA5',
            300: '#2DB88A',  // ← added
            400: '#1D9E75',
            500: '#158064',  // ← added
            600: '#0F6E56',  // primary CTA
            700: '#0C5848',  // ← added
            800: '#085041',
            900: '#04342C',
          },

          // ── Warm — parchment backgrounds and surfaces ────────────────────
          // NOTE: The legacy named keys (DEFAULT / surface / border) are kept
          // for backwards compatibility but all components should use numeric steps.
          warm: {
            DEFAULT: '#F7F5F0',
            surface: '#EFEDE7',
            border:  'rgba(0,0,0,0.07)',
            50:  '#FDFCF9',  // near-white body tint      ← added
            100: '#F7F5F0',  // == DEFAULT; main bg
            200: '#EFEDE7',  // == surface; card/border
            300: '#E4E1D8',  // stronger border / hover   ← added
          },

          // ── Stone — warm neutral text and UI chrome ──────────────────────
          stone: {
            50:  '#F1EFE8',
            100: '#D3D1C7',
            200: '#C0BDB2',  // ← added
            300: '#A8A59A',  // ← added
            400: '#888780',
            500: '#726F68',  // ← added
            600: '#5F5E5A',
            700: '#4D4C49',  // ← added
            800: '#444441',
            900: '#2C2C2A',
          },

          // ── Amber — warnings, building states ───────────────────────────
          amber: {
            50:  '#FEF8EC',  // ← added
            100: '#FAC775',
            200: '#F7B04C',  // ← added
            400: '#EF9F27',
            500: '#D48820',  // ← added
            600: '#BA7517',
            700: '#8F5910',  // ← added
            800: '#6A4010',  // ← added
          },

          // ── Navy — primary action buttons (formerly hardcoded #1E3A5F) ──
          navy: {
            600: '#1E3A5F',  // primary CTA
            700: '#162D4A',  // hover
          },

          // ── Blue — informational accents, evidence quotes ─────────────
          blue: {
            50:  '#EFF6FF',  // light info background
            100: '#DBEAFE',  // info border
            600: '#2563EB',  // chart accent
            700: '#1D4ED8',  // section header bg
          },

          // ── Rose — experiment section accents ────────────────────────────
          rose: {
            50:  '#FFF5F5',  // light text on dark header
            700: '#9B2C2C',  // section header bg
          },

          // ── Red — errors, destructive actions ────────────────────────────
          red: {
            50:  '#FDF2F2',  // ← added
            100: '#F7C1C1',
            200: '#F09898',  // ← added
            300: '#E87070',  // ← added
            400: '#E24B4A',
            500: '#CC3635',  // ← added
            600: '#A32D2D',
            700: '#7A2020',  // ← added
          },

        },
      },

      fontFamily: {
        // CSS variables are injected by next/font in app/layout.tsx
        serif: ['var(--font-serif)', 'Georgia', 'serif'],
        sans:  ['var(--font-sans)',  'system-ui', 'sans-serif'],
      },

      fontSize: {
        '2xs': ['10px', { lineHeight: '1.4', letterSpacing: '0.08em' }],
        'xs':  ['12px', { lineHeight: '1.5' }],
        'sm':  ['14px', { lineHeight: '1.6' }],
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
    },
  },
  plugins: [],
};

export default config;

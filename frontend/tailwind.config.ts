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
          teal: {
            50:  '#E1F5EE',
            100: '#9FE1CB',
            200: '#5DCAA5',
            400: '#1D9E75',
            600: '#0F6E56',
            800: '#085041',
            900: '#04342C',
          },
          warm: {
            DEFAULT: '#F7F5F0',
            surface: '#EFEDE7',
            border:  'rgba(0, 0, 0, 0.07)',
          },
          stone: {
            50:  '#F1EFE8',
            100: '#D3D1C7',
            400: '#888780',
            600: '#5F5E5A',
            800: '#444441',
            900: '#2C2C2A',
          },
          amber: {
            100: '#FAC775',
            400: '#EF9F27',
            600: '#BA7517',
          },
          red: {
            100: '#F7C1C1',
            400: '#E24B4A',
            600: '#A32D2D',
          },
        },
      },
      fontFamily: {
        serif: ['var(--font-serif)', 'Georgia', 'serif'],
        sans:  ['var(--font-sans)',  'system-ui', 'sans-serif'],
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
    },
  },
  plugins: [],
};

export default config;

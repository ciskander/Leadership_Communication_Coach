import type { Metadata } from 'next';
import { Inter, DM_Sans, DM_Serif_Display } from 'next/font/google';
import './globals.css';
import { STRINGS } from '@/config/strings';

// Kept for any legacy components still using it directly
const inter = Inter({
  subsets: ['latin'],
  variable: '--font-inter',
});

const dmSans = DM_Sans({
  subsets: ['latin'],
  weight: ['300', '400', '500'],
  style: ['normal', 'italic'],
  variable: '--font-sans',
  display: 'swap',
});

const dmSerif = DM_Serif_Display({
  subsets: ['latin'],
  weight: ['400'],
  style: ['normal', 'italic'],
  variable: '--font-serif',
  display: 'swap',
});

export const metadata: Metadata = {
  title: STRINGS.app.title,
  description: STRINGS.app.description,
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" className={`${dmSans.variable} ${dmSerif.variable} ${inter.variable}`}>
      <body className={dmSans.className}>{children}</body>
    </html>
  );
}

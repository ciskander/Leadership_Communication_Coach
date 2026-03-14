import type { Metadata } from 'next';
import { Montserrat, Lora } from 'next/font/google';
import './globals.css';
import { STRINGS } from '@/config/strings';

const montserrat = Montserrat({
  subsets: ['latin'],
  weight: ['300', '400', '500', '600', '700'],
  style: ['normal', 'italic'],
  variable: '--font-sans',
  display: 'swap',
});

const lora = Lora({
  subsets: ['latin'],
  weight: ['400', '500', '600', '700'],
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
    <html lang="en" className={`${montserrat.variable} ${lora.variable}`}>
      <body className={montserrat.className}>{children}</body>
    </html>
  );
}

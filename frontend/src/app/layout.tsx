import type { Metadata } from 'next';
import { Inter } from 'next/font/google';
import './globals.css';
import { STRINGS } from '@/config/strings';

const inter = Inter({ subsets: ['latin'] });

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
    <html lang="en">
      <body className={inter.className}>{children}</body>
    </html>
  );
}

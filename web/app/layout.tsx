import type { Metadata } from 'next';
import './globals.css';

export const metadata: Metadata = {
  title: 'Blim — Buy on Vinted before everyone else',
  description: 'Real-time Vinted feed and one-click buying.',
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}

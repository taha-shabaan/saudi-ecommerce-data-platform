import type { Metadata } from 'next';
import './globals.css';

export const metadata: Metadata = {
  title: 'Synthetic Data Generation Engine',
  description: 'Production-ready platform for relational mock data generation, topological DAG resolution, and multi-format exports.',
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body className="bg-slate-950 text-slate-100 min-h-screen antialiased">
        {children}
      </body>
    </html>
  );
}

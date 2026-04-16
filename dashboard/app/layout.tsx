import type { Metadata } from 'next'
import './globals.css'

export const metadata: Metadata = {
  title: 'GBC Orders Dashboard',
  description: 'Analytics dashboard for GBC / Tomyris orders',
}

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="ru">
      <body className="antialiased">{children}</body>
    </html>
  )
}

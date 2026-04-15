import type { Metadata } from 'next'
import './globals.css'
import AppChrome from '@/components/AppChrome'

export const metadata: Metadata = {
  title: 'AgentShrink',
  description: 'Trace, analyze, and route AI agent calls to cheaper safer models.',
}

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <head>
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="anonymous" />
      </head>
      <body>
        <AppChrome>{children}</AppChrome>
      </body>
    </html>
  )
}

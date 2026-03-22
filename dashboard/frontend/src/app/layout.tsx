import type { Metadata } from 'next'
import './globals.css'
import Sidebar from '@/components/Sidebar'

export const metadata: Metadata = {
  title: 'AgentShrink Dashboard',
  description: 'Automatically convert LLM agents to use cheaper local SLMs',
}

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        <div style={{ display: 'flex', height: '100vh', overflow: 'hidden' }}>
          <Sidebar />
          <main style={{
            flex: 1,
            overflow: 'auto',
            padding: '24px',
            background: 'var(--bg-tertiary)',
          }}>
            {children}
          </main>
        </div>
      </body>
    </html>
  )
}

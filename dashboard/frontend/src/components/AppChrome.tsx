'use client'

import { usePathname } from 'next/navigation'
import Sidebar from '@/components/Sidebar'

export default function AppChrome({ children }: { children: React.ReactNode }) {
  const pathname = usePathname()
  const isPublicSite = pathname.startsWith('/site')

  if (isPublicSite) {
    return (
      <main style={{
        minHeight: '100vh',
        background: 'var(--bg-tertiary)',
      }}>
        {children}
      </main>
    )
  }

  return (
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
  )
}

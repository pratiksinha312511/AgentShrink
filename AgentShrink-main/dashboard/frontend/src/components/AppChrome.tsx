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
        background: '#E0E5EC',
      }}>
        {children}
      </main>
    )
  }

  return (
    <div style={{ display: 'flex', height: '100vh', overflow: 'hidden', background: '#E0E5EC' }}>
      <Sidebar />
      <main style={{
        flex: 1,
        overflow: 'auto',
        padding: '28px 32px',
        background: '#E0E5EC',
      }}>
        {children}
      </main>
    </div>
  )
}

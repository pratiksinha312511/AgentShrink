'use client'
import Link from 'next/link'
import { usePathname } from 'next/navigation'

const NAV = [
  { href: '/projects',   label: 'Projects',    dot: '#2E8B57' },
  { href: '/welcome',    label: 'Get Started', dot: '#2E8B57' },
  { href: '/',          label: 'Overview',    dot: '#7F77DD' },
  { href: '/clusters',  label: 'Cluster Map', dot: '#1D9E75' },
  { href: '/report',    label: 'Report',      dot: '#EF9F27' },
  { href: '/routing',   label: 'Live Routing',dot: '#185FA5' },
  { href: '/finetune',  label: 'Fine-tune',   dot: '#D85A30' },
  { href: '/models',    label: 'Models',      dot: '#9F3F7A' },
  { href: '/settings',  label: 'Settings',    dot: '#888780' },
]

export default function Sidebar() {
  const path = usePathname()

  return (
    <aside style={{
      width: 200,
      background: 'var(--bg-secondary)',
      borderRight: '0.5px solid var(--border)',
      display: 'flex',
      flexDirection: 'column',
      flexShrink: 0,
      height: '100vh',
    }}>
      {/* Logo */}
      <div style={{
        padding: '18px 16px 14px',
        borderBottom: '0.5px solid var(--border)',
        marginBottom: 8,
      }}>
        <div style={{ fontSize: 15, fontWeight: 600, color: 'var(--text-primary)' }}>
          AgentShrink
        </div>
        <div style={{ fontSize: 11, color: 'var(--text-tertiary)', marginTop: 2 }}>
          v0.1.0
        </div>
      </div>

      {/* Nav items */}
      <nav style={{ flex: 1 }}>
        {NAV.map(item => {
          const active = path === item.href
          return (
            <Link key={item.href} href={item.href} style={{ textDecoration: 'none' }}>
              <div className={`nav-item ${active ? 'active' : ''}`}>
                <span style={{
                  width: 7, height: 7,
                  borderRadius: '50%',
                  background: item.dot,
                  flexShrink: 0,
                  display: 'inline-block',
                }} />
                {item.label}
              </div>
            </Link>
          )
        })}
      </nav>

      {/* Footer */}
      <div style={{
        padding: '12px 16px',
        borderTop: '0.5px solid var(--border)',
        fontSize: 10,
        color: 'var(--text-tertiary)',
        lineHeight: 1.6,
      }}>
        Based on<br />
        NVIDIA arXiv:2506.02153
      </div>
    </aside>
  )
}

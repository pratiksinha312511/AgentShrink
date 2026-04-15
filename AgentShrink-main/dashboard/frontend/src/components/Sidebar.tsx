'use client'
import Link from 'next/link'
import { usePathname } from 'next/navigation'
import {
  LayoutDashboard,
  Rocket,
  ScatterChart,
  FileBarChart,
  Radio,
  BrainCircuit,
  Box,
  Settings,
  FolderKanban,
  Users,
  CreditCard,
  UserCircle,
} from 'lucide-react'

const NAV_GROUPS = [
  {
    label: 'Project',
    items: [
      { href: '/projects',  label: 'Projects',     icon: FolderKanban },
      { href: '/welcome',   label: 'Get Started',  icon: Rocket },
    ],
  },
  {
    label: 'Pipeline',
    items: [
      { href: '/',          label: 'Overview',      icon: LayoutDashboard },
      { href: '/clusters',  label: 'Cluster Map',   icon: ScatterChart },
      { href: '/report',    label: 'Report',        icon: FileBarChart },
      { href: '/routing',   label: 'Live Routing',  icon: Radio },
      { href: '/finetune',  label: 'Fine-tune',     icon: BrainCircuit },
    ],
  },
  {
    label: 'System',
    items: [
      { href: '/models',    label: 'Models',        icon: Box },
      { href: '/settings',  label: 'Settings',      icon: Settings },
    ],
  },
  {
    label: 'Account',
    items: [
      { href: '/account',   label: 'Account',       icon: UserCircle },
      { href: '/teams',     label: 'Teams',          icon: Users },
      { href: '/billing',   label: 'Billing',        icon: CreditCard },
    ],
  },
]

export default function Sidebar() {
  const path = usePathname()

  return (
    <aside style={{
      width: 240,
      background: '#E0E5EC',
      display: 'flex',
      flexDirection: 'column',
      flexShrink: 0,
      height: '100vh',
      overflow: 'hidden',
      boxShadow: '6px 0 16px rgb(163,177,198,0.3)',
    }}>
      {/* Logo */}
      <div style={{
        padding: '24px 20px 20px',
        display: 'flex',
        alignItems: 'center',
        gap: 12,
      }}>
        <div style={{
          width: 40,
          height: 40,
          borderRadius: 16,
          background: '#E0E5EC',
          boxShadow: '5px 5px 10px rgb(163,177,198,0.6), -5px -5px 10px rgba(255,255,255,0.5)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
        }}>
          <BrainCircuit size={20} style={{ color: '#6C63FF' }} />
        </div>
        <div>
          <div className="font-display" style={{
            fontSize: 15,
            fontWeight: 800,
            color: '#3D4852',
            letterSpacing: '-0.02em',
          }}>
            AgentShrink
          </div>
          <div style={{ fontSize: 11, color: '#9CA3AF', fontWeight: 500 }}>v0.6</div>
        </div>
      </div>

      {/* Nav groups */}
      <nav style={{ flex: 1, overflow: 'auto', paddingTop: 4, paddingBottom: 8 }}>
        {NAV_GROUPS.map((group) => (
          <div key={group.label}>
            <div className="nav-group-label">{group.label}</div>
            {group.items.map((item) => {
              const active = path === item.href
              const Icon = item.icon
              return (
                <Link key={item.href} href={item.href} style={{ textDecoration: 'none' }}>
                  <div className={`nav-item ${active ? 'active' : ''}`}>
                    <div style={{
                      width: 28,
                      height: 28,
                      borderRadius: 10,
                      background: '#E0E5EC',
                      boxShadow: active
                        ? 'inset 3px 3px 6px rgb(163,177,198,0.6), inset -3px -3px 6px rgba(255,255,255,0.5)'
                        : '3px 3px 6px rgb(163,177,198,0.4), -3px -3px 6px rgba(255,255,255,0.4)',
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                      flexShrink: 0,
                      transition: 'box-shadow 300ms ease-out',
                    }}>
                      <Icon size={14} strokeWidth={active ? 2 : 1.5} style={{ color: active ? '#6C63FF' : '#9CA3AF' }} />
                    </div>
                    <span>{item.label}</span>
                  </div>
                </Link>
              )
            })}
          </div>
        ))}
      </nav>

      {/* Footer */}
      <div style={{
        padding: '14px 20px',
        fontSize: 11,
        color: '#9CA3AF',
        lineHeight: 1.5,
        fontWeight: 500,
      }}>
        <div>arXiv:2506.02153</div>
        <div style={{ color: '#BFC5CC' }}>NVIDIA Research 2025</div>
      </div>
    </aside>
  )
}

'use client'

import type { CSSProperties, ReactNode } from 'react'
import { useState } from 'react'

/* ═══════════════════════════════════════════════════════════════
   AGENTSHRINK — NEUMORPHIC COMPONENT LIBRARY
   Soft UI · Dual Shadows · Hyper-Rounded · Tactile Depth
   ═══════════════════════════════════════════════════════════════ */

// ── Layout ──────────────────────────────────────────────────────

export function PageShell({
  children,
  maxWidth = 1280,
}: {
  children: ReactNode
  maxWidth?: number
}) {
  return (
    <div style={{ maxWidth, width: '100%', display: 'flex', flexDirection: 'column', gap: 20 }}>
      {children}
    </div>
  )
}

export function PageHeader({
  tag,
  title,
  description,
  right,
}: {
  tag?: string
  title: string
  description?: string
  right?: ReactNode
}) {
  return (
    <div className="card" style={{ padding: 28 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 16, flexWrap: 'wrap' }}>
        <div>
          {tag && (
            <span style={{
              display: 'inline-block',
              fontSize: 11,
              fontWeight: 600,
              color: '#6C63FF',
              background: 'rgba(108, 99, 255, 0.1)',
              padding: '3px 12px',
              borderRadius: 9999,
              marginBottom: 10,
              letterSpacing: '0.04em',
              textTransform: 'uppercase',
              boxShadow: '3px 3px 6px rgb(163,177,198,0.4), -3px -3px 6px rgba(255,255,255,0.4)',
            }}>
              {tag}
            </span>
          )}
          <h1 className="font-display" style={{
            fontSize: 24,
            fontWeight: 800,
            margin: 0,
            color: '#3D4852',
            letterSpacing: '-0.02em',
          }}>
            {title}
          </h1>
          {description && (
            <p style={{
              margin: '10px 0 0',
              color: '#6B7280',
              fontSize: 14,
              lineHeight: 1.7,
              maxWidth: 560,
            }}>
              {description}
            </p>
          )}
        </div>
        {right && <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>{right}</div>}
      </div>
    </div>
  )
}

// ── Card ────────────────────────────────────────────────────────

export function TerminalCard({
  title,
  children,
  style,
  headerRight,
  noPadding,
}: {
  title?: string
  children: ReactNode
  style?: CSSProperties
  headerRight?: ReactNode
  noPadding?: boolean
}) {
  return (
    <div className="card" style={style}>
      {title && (
        <div className="card-header" style={{ justifyContent: 'space-between' }}>
          <span>{title}</span>
          {headerRight}
        </div>
      )}
      <div style={noPadding ? undefined : { padding: 20 }}>{children}</div>
    </div>
  )
}

// ── Metrics ─────────────────────────────────────────────────────

export function MetricRow({ children }: { children: ReactNode }) {
  return (
    <div style={{
      display: 'grid',
      gridTemplateColumns: 'repeat(auto-fit, minmax(150px, 1fr))',
      gap: 16,
    }}>
      {children}
    </div>
  )
}

export function Metric({
  label,
  value,
  color = '#6C63FF',
}: {
  label: string
  value: string | number
  color?: string
}) {
  return (
    <div className="metric-card">
      <div className="metric-num" style={{ color }}>{value}</div>
      <div className="metric-label">{label}</div>
    </div>
  )
}

// ── Stat (inline key:value) ─────────────────────────────────────

export function StatRow({ label, value }: { label: string; value: ReactNode }) {
  return (
    <div style={{
      display: 'flex',
      justifyContent: 'space-between',
      alignItems: 'center',
      padding: '10px 0',
      fontSize: 13,
    }}>
      <span style={{ color: '#6B7280', fontWeight: 500, fontSize: 12, textTransform: 'uppercase', letterSpacing: '0.04em' }}>{label}</span>
      <span style={{ color: '#3D4852', fontWeight: 600 }}>{value}</span>
    </div>
  )
}

// ── Badge ───────────────────────────────────────────────────────

type BadgeVariant = 'green' | 'amber' | 'red' | 'blue' | 'purple' | 'default'

const BADGE_STYLES: Record<BadgeVariant, CSSProperties> = {
  green:   { background: 'rgba(56, 178, 172, 0.12)', color: '#2C9A94' },
  amber:   { background: 'rgba(214, 158, 46, 0.12)', color: '#B7791F' },
  red:     { background: 'rgba(229, 62, 62, 0.12)',  color: '#C53030' },
  blue:    { background: 'rgba(49, 130, 206, 0.12)', color: '#2B6CB0' },
  purple:  { background: 'rgba(108, 99, 255, 0.12)', color: '#5A52D5' },
  default: { background: 'rgba(107, 114, 128, 0.08)', color: '#6B7280' },
}

export function Badge({ children, variant = 'default' }: { children: ReactNode; variant?: BadgeVariant }) {
  return (
    <span style={{
      display: 'inline-flex',
      alignItems: 'center',
      gap: 4,
      padding: '4px 12px',
      fontSize: 11,
      fontWeight: 600,
      textTransform: 'uppercase',
      letterSpacing: '0.04em',
      borderRadius: 9999,
      boxShadow: '3px 3px 6px rgb(163,177,198,0.4), -3px -3px 6px rgba(255,255,255,0.4)',
      ...BADGE_STYLES[variant],
    }}>
      {children}
    </span>
  )
}

// ── StatusDot ───────────────────────────────────────────────────

export function StatusDot({ ok, pulse }: { ok: boolean; pulse?: boolean }) {
  const color = ok ? '#38B2AC' : '#E53E3E'
  return (
    <span
      className={pulse ? 'live-dot' : undefined}
      style={{
        display: 'inline-block',
        width: 10,
        height: 10,
        borderRadius: 9999,
        background: color,
        boxShadow: `0 0 6px ${color}60, inset 1px 1px 2px rgba(255,255,255,0.3)`,
      }}
    />
  )
}

// ── Buttons ─────────────────────────────────────────────────────

export function PrimaryButton({
  children,
  onClick,
  disabled,
  style,
  type,
}: {
  children: ReactNode
  onClick?: () => void
  disabled?: boolean
  style?: CSSProperties
  type?: 'button' | 'submit' | 'reset'
}) {
  return (
    <button className="btn btn-primary" onClick={onClick} disabled={disabled} style={style} type={type}>
      {children}
    </button>
  )
}

export function SecondaryButton({
  children,
  onClick,
  disabled,
  style,
  type,
}: {
  children: ReactNode
  onClick?: () => void
  disabled?: boolean
  style?: CSSProperties
  type?: 'button' | 'submit' | 'reset'
}) {
  return (
    <button className="btn btn-secondary" onClick={onClick} disabled={disabled} style={style} type={type}>
      {children}
    </button>
  )
}

export function DangerButton({
  children,
  onClick,
  disabled,
  style,
}: {
  children: ReactNode
  onClick?: () => void
  disabled?: boolean
  style?: CSSProperties
}) {
  return (
    <button className="btn btn-danger" onClick={onClick} disabled={disabled} style={style}>
      {children}
    </button>
  )
}

// ── Inputs ──────────────────────────────────────────────────────

export function TerminalInput({
  value,
  onChange,
  placeholder,
  type = 'text',
  style,
  ...rest
}: {
  value: string | number
  onChange: (e: React.ChangeEvent<HTMLInputElement>) => void
  placeholder?: string
  type?: string
  style?: CSSProperties
} & Omit<React.InputHTMLAttributes<HTMLInputElement>, 'onChange'>) {
  return (
    <input
      className="terminal-input"
      type={type}
      value={value}
      onChange={onChange}
      placeholder={placeholder}
      style={style}
      {...rest}
    />
  )
}

export function TerminalSelect({
  value,
  onChange,
  children,
  style,
}: {
  value: string
  onChange: (e: React.ChangeEvent<HTMLSelectElement>) => void
  children: ReactNode
  style?: CSSProperties
}) {
  return (
    <select className="terminal-select" value={value} onChange={onChange} style={style}>
      {children}
    </select>
  )
}

export function FieldLabel({
  label,
  children,
}: {
  label: string
  children: ReactNode
}) {
  return (
    <label style={{ display: 'grid', gap: 8 }}>
      <span style={{
        fontSize: 12,
        fontWeight: 600,
        color: '#6B7280',
        letterSpacing: '0.02em',
      }}>{label}</span>
      {children}
    </label>
  )
}

// ── Progress ────────────────────────────────────────────────────

export function ProgressBar({
  value,
  max = 100,
  label,
  color = '#6C63FF',
}: {
  value: number
  max?: number
  label?: string
  color?: string
}) {
  const pct = Math.max(0, Math.min(100, (value / max) * 100))
  return (
    <div className="progress-bar">
      {label && (
        <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 6 }}>
          <span style={{ fontSize: 12, color: '#6B7280', fontWeight: 500 }}>{label}</span>
          <span style={{ fontSize: 12, color, fontWeight: 600 }}>{Math.round(pct)}%</span>
        </div>
      )}
      <div className="progress-track">
        <div className="progress-fill" style={{ width: `${pct}%`, background: `linear-gradient(135deg, ${color}, ${color}cc)` }} />
      </div>
    </div>
  )
}

// ── Code Block ──────────────────────────────────────────────────

export function CodeBlock({ text, copyable }: { text: string; copyable?: boolean }) {
  const handleCopy = () => {
    navigator.clipboard?.writeText(text)
  }
  return (
    <div style={{ position: 'relative' }}>
      <pre className="code-block">{text}</pre>
      {copyable && (
        <button
          onClick={handleCopy}
          className="btn btn-secondary"
          style={{
            position: 'absolute',
            top: 12,
            right: 12,
            padding: '4px 10px',
            fontSize: 11,
          }}
        >
          Copy
        </button>
      )}
    </div>
  )
}

// ── Collapsible ─────────────────────────────────────────────────

export function Collapsible({
  title,
  children,
  defaultOpen = false,
}: {
  title: string
  children: ReactNode
  defaultOpen?: boolean
}) {
  const [open, setOpen] = useState(defaultOpen)
  return (
    <div>
      <button
        onClick={() => setOpen(!open)}
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 10,
          background: 'none',
          border: 'none',
          color: '#3D4852',
          cursor: 'pointer',
          padding: '10px 0',
          fontSize: 13,
          fontWeight: 500,
          width: '100%',
          textAlign: 'left',
        }}
      >
        <span style={{
          display: 'inline-flex',
          alignItems: 'center',
          justifyContent: 'center',
          width: 24,
          height: 24,
          borderRadius: 8,
          background: '#E0E5EC',
          boxShadow: open
            ? 'inset 3px 3px 6px rgb(163,177,198,0.6), inset -3px -3px 6px rgba(255,255,255,0.5)'
            : '3px 3px 6px rgb(163,177,198,0.6), -3px -3px 6px rgba(255,255,255,0.5)',
          fontSize: 12,
          color: '#6C63FF',
          transition: 'all 300ms ease-out',
        }}>
          {open ? '−' : '+'}
        </span>
        {title}
      </button>
      {open && <div style={{ paddingLeft: 34, paddingTop: 4 }}>{children}</div>}
    </div>
  )
}

// ── Loading state ───────────────────────────────────────────────

export function LoadingTerminal({ message = 'Loading' }: { message?: string }) {
  return (
    <div style={{
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center',
      padding: 48,
      color: '#6B7280',
      fontSize: 14,
      fontWeight: 500,
    }}>
      <span>{message}</span>
      <span className="cursor-blink" style={{ marginLeft: 4 }} />
    </div>
  )
}

// ── Error display ───────────────────────────────────────────────

export function ErrorBlock({ message }: { message: string }) {
  return (
    <div className="card" style={{
      padding: 18,
      background: 'rgba(229, 62, 62, 0.06)',
      color: '#C53030',
      fontSize: 13,
      fontWeight: 500,
      borderRadius: 16,
    }}>
      <span style={{ fontWeight: 700, marginRight: 6 }}>Error:</span>{message}
    </div>
  )
}

export function SuccessBlock({ message }: { message: string }) {
  return (
    <div className="card" style={{
      padding: 18,
      background: 'rgba(56, 178, 172, 0.06)',
      color: '#2C9A94',
      fontSize: 13,
      fontWeight: 500,
      borderRadius: 16,
    }}>
      <span style={{ fontWeight: 700, marginRight: 6 }}>Done:</span>{message}
    </div>
  )
}

// ── Empty state ─────────────────────────────────────────────────

export function EmptyState({ message, hint }: { message: string; hint?: string }) {
  return (
    <div style={{
      padding: '40px 20px',
      textAlign: 'center',
      color: '#6B7280',
      fontSize: 14,
    }}>
      <div style={{
        width: 56,
        height: 56,
        borderRadius: 9999,
        background: '#E0E5EC',
        boxShadow: 'inset 6px 6px 10px rgb(163,177,198,0.6), inset -6px -6px 10px rgba(255,255,255,0.5)',
        margin: '0 auto 16px',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        fontSize: 20,
      }}>
        ∅
      </div>
      <div style={{ fontWeight: 500, marginBottom: hint ? 6 : 0 }}>{message}</div>
      {hint && <div style={{ color: '#9CA3AF', fontSize: 13 }}>{hint}</div>}
    </div>
  )
}

// ── Animated Action Button ──────────────────────────────────────

export function AnimatedActionButton({
  onClick,
  label,
  icon = 'play',
  disabled = false,
  active = false,
}: {
  onClick: () => void
  label: string
  icon?: 'play' | 'check' | 'spinner' | 'rocket'
  disabled?: boolean
  active?: boolean
}) {
  const icons: Record<string, ReactNode> = {
    play: (
      <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor">
        <polygon points="5,3 19,12 5,21" />
      </svg>
    ),
    check: (
      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round">
        <polyline points="20 6 9 17 4 12" />
      </svg>
    ),
    spinner: (
      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" style={{ animation: 'spin 1s linear infinite' }}>
        <path d="M21 12a9 9 0 1 1-6.219-8.56" />
      </svg>
    ),
    rocket: (
      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <path d="M4.5 16.5c-1.5 1.26-2 5-2 5s3.74-.5 5-2c.71-.84.7-2.13-.09-2.91a2.18 2.18 0 0 0-2.91-.09z" />
        <path d="m12 15-3-3a22 22 0 0 1 2-3.95A12.88 12.88 0 0 1 22 2c0 2.72-.78 7.5-6 11a22.35 22.35 0 0 1-4 2z" />
        <path d="M9 12H4s.55-3.03 2-4c1.62-1.08 5 0 5 0" />
        <path d="M12 15v5s3.03-.55 4-2c1.08-1.62 0-5 0-5" />
      </svg>
    ),
  }

  return (
    <button
      className="btn btn-primary"
      onClick={onClick}
      disabled={disabled}
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: 8,
        animation: active ? 'analysing-pulse 2s ease-in-out infinite' : undefined,
      }}
    >
      {icons[icon]}
      {label}
    </button>
  )
}

// ── NeuToggle (enhanced) ────────────────────────────────────────

export function NeuToggle({
  checked,
  onClick,
  disabled = false,
  label,
  variant = 'default',
}: {
  checked: boolean
  onClick: () => void
  disabled?: boolean
  label: string
  variant?: 'default' | 'judge'
}) {
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      aria-label={label}
      title={label}
      className="terminal-toggle"
      style={{ opacity: disabled ? 0.4 : 1 }}
    >
      <div className={`terminal-toggle-track${checked ? (variant === 'judge' ? ' judge' : ' active') : ''}`}>
        <div className="terminal-toggle-thumb" />
      </div>
    </button>
  )
}

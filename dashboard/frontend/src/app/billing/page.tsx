'use client'

import { useEffect, useState } from 'react'
import { createPublicBillingCheckout, fetchHostedConfig, fetchPublicBilling } from '@/lib/api'

export default function BillingPage() {
  const [billing, setBilling] = useState<any>(null)
  const [hosted, setHosted] = useState<any>(null)
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')

  useEffect(() => {
    Promise.all([fetchPublicBilling(), fetchHostedConfig()])
      .then(([billingData, hostedData]) => {
        setBilling(billingData)
        setHosted(hostedData)
      })
      .catch((e: any) => setError(e.message || 'Failed to load billing'))
  }, [])

  if (error) {
    return <div className="card" style={{ padding: 24 }}>{error}</div>
  }

  const startCheckout = async () => {
    try {
      setError('')
      const data = await createPublicBillingCheckout({ return_url: window.location.origin })
      if (data?.checkout_url) {
        window.location.href = data.checkout_url
        return
      }
      setMessage('Billing provider responded, but no checkout URL was returned.')
    } catch (e: any) {
      setError(e.message || 'Failed to start billing checkout')
    }
  }

  return (
    <div style={{ maxWidth: 920 }}>
      <div className="card" style={{ padding: 24, marginBottom: 16 }}>
        <div style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-secondary)', marginBottom: 8 }}>Hosted billing shell</div>
        <h1 style={{ fontSize: 24, margin: '0 0 8px', color: 'var(--text-primary)' }}>Billing</h1>
        <p style={{ margin: 0, color: 'var(--text-secondary)', lineHeight: 1.7 }}>
          This page separates hosted billing and tenancy metadata from the purely local runtime. It is the first step
          toward a real public product contract, while still staying transparent that billing is not yet production-grade.
        </p>
        {(message || error) && (
          <div style={{ marginTop: 10, fontSize: 12, color: error ? '#A32D2D' : '#27500A' }}>
            {error || message}
          </div>
        )}
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr 1fr', gap: 16, marginBottom: 16 }}>
        <Metric label="Plan" value={billing?.billing?.plan || hosted?.billing?.plan || 'beta'} />
        <Metric label="Currency" value={billing?.billing?.currency || hosted?.billing?.currency || 'USD'} />
        <Metric label="Projects" value={String(billing?.metrics?.projects || 0)} />
        <Metric label="Members" value={String(billing?.metrics?.members || 0)} />
      </div>

      <div className="card" style={{ padding: 24, marginBottom: 16 }}>
        <div style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-secondary)', marginBottom: 12 }}>Usage summary</div>
        <div style={{ display: 'grid', gap: 10 }}>
          <InfoRow label="Total calls" value={String(billing?.metrics?.total_calls || 0)} />
          <InfoRow label="Total runs" value={String(billing?.metrics?.total_runs || 0)} />
          <InfoRow label="Seat count" value={String(billing?.billing?.seat_count || 0)} />
          <InfoRow label="Included projects" value={String(billing?.billing?.included_projects || 0)} />
          <InfoRow label="Ledger entries" value={String((billing?.ledger?.entries || []).length)} />
        </div>
      </div>

      <div className="card" style={{ padding: 24 }}>
        <div style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-secondary)', marginBottom: 12 }}>Hosted config split</div>
        <div style={{ display: 'grid', gap: 10 }}>
          <InfoRow label="Deployment mode" value={hosted?.deployment?.mode || 'local-hosted'} />
          <InfoRow label="Public app URL" value={hosted?.deployment?.public_app_url || '-'} mono />
          <InfoRow label="Public API URL" value={hosted?.deployment?.public_api_url || '-'} mono />
          <InfoRow label="Gateway URL" value={hosted?.deployment?.gateway_url || '-'} mono />
          <InfoRow label="Auth provider" value={hosted?.auth?.provider || 'local-session'} />
          <InfoRow label="Billing provider" value={hosted?.billing?.provider || 'manual'} />
          <InfoRow label="Isolation mode" value={hosted?.tenancy?.isolation_mode || 'team-scoped'} />
        </div>
        <div style={{ display: 'flex', gap: 8, marginTop: 14, flexWrap: 'wrap' }}>
          {hosted?.billing?.provider === 'stripe' && (
            <button onClick={startCheckout} style={buttonStyle}>Open Stripe checkout</button>
          )}
        </div>
      </div>
    </div>
  )
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="metric-card" style={{ alignItems: 'flex-start' }}>
      <div className="metric-num" style={{ color: 'var(--text-primary)' }}>{value}</div>
      <div className="metric-label">{label}</div>
    </div>
  )
}

function InfoRow({ label, value, mono = false }: { label: string; value: string; mono?: boolean }) {
  return (
    <div style={{ background: 'var(--bg-secondary)', borderRadius: 10, padding: '12px 14px' }}>
      <div style={{ fontSize: 11, textTransform: 'uppercase', color: 'var(--text-tertiary)', marginBottom: 4 }}>{label}</div>
      <div style={{ fontSize: 13, color: 'var(--text-primary)', fontFamily: mono ? 'monospace' : undefined, wordBreak: 'break-word' }}>{value}</div>
    </div>
  )
}

const buttonStyle = {
  border: '0.5px solid var(--border)',
  borderRadius: 8,
  background: 'var(--bg-primary)',
  color: 'var(--text-primary)',
  fontSize: 12,
  fontWeight: 600,
  padding: '8px 10px',
  cursor: 'pointer',
} as const

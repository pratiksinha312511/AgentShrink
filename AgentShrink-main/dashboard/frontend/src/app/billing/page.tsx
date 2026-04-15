'use client'

import { useEffect, useState } from 'react'
import { createPublicBillingCheckout, fetchHostedConfig, fetchPublicBilling } from '@/lib/api'
import { PageShell, PageHeader, TerminalCard, MetricRow, Metric, PrimaryButton, ErrorBlock, SuccessBlock } from '@/components/Terminal'

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

  if (error && !billing) {
    return (
      <PageShell maxWidth={920}>
        <PageHeader title="BILLING" tag="hosted" />
        <ErrorBlock message={error} />
      </PageShell>
    )
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
    <PageShell maxWidth={920}>
      <PageHeader
        title="BILLING"
        tag="hosted"
        description="Separates hosted billing and tenancy metadata from the purely local runtime. First step toward a real public product contract."
      />

      {error && <ErrorBlock message={error} />}
      {message && !error && <SuccessBlock message={message} />}

      <MetricRow>
        <Metric label="plan" value={billing?.billing?.plan || hosted?.billing?.plan || 'beta'} color="#6C63FF" />
        <Metric label="currency" value={billing?.billing?.currency || hosted?.billing?.currency || 'USD'} />
        <Metric label="projects" value={String(billing?.metrics?.projects || 0)} />
        <Metric label="members" value={String(billing?.metrics?.members || 0)} />
      </MetricRow>

      <TerminalCard title="USAGE SUMMARY">
        <table className="terminal-table">
          <tbody>
            <Row label="total_calls" value={String(billing?.metrics?.total_calls || 0)} />
            <Row label="total_runs" value={String(billing?.metrics?.total_runs || 0)} />
            <Row label="seat_count" value={String(billing?.billing?.seat_count || 0)} />
            <Row label="included_projects" value={String(billing?.billing?.included_projects || 0)} />
            <Row label="ledger_entries" value={String((billing?.ledger?.entries || []).length)} />
          </tbody>
        </table>
      </TerminalCard>

      <TerminalCard title="HOSTED CONFIG" headerRight={
        hosted?.billing?.provider === 'stripe' ? (
          <PrimaryButton onClick={startCheckout}>OPEN STRIPE CHECKOUT</PrimaryButton>
        ) : undefined
      }>
        <table className="terminal-table">
          <tbody>
            <Row label="deployment_mode" value={hosted?.deployment?.mode || 'local-hosted'} />
            <Row label="public_app_url" value={hosted?.deployment?.public_app_url || '-'} mono />
            <Row label="public_api_url" value={hosted?.deployment?.public_api_url || '-'} mono />
            <Row label="gateway_url" value={hosted?.deployment?.gateway_url || '-'} mono />
            <Row label="auth_provider" value={hosted?.auth?.provider || 'local-session'} />
            <Row label="billing_provider" value={hosted?.billing?.provider || 'manual'} />
            <Row label="isolation_mode" value={hosted?.tenancy?.isolation_mode || 'team-scoped'} />
          </tbody>
        </table>
      </TerminalCard>
    </PageShell>
  )
}

function Row({ label, value, mono = false }: { label: string; value: string; mono?: boolean }) {
  return (
    <tr>
      <td style={{ color: 'var(--text-tertiary)', whiteSpace: 'nowrap' }}>{label}</td>
      <td style={{ color: mono ? '#6C63FF' : '#3D4852', wordBreak: 'break-word' }}>{value}</td>
    </tr>
  )
}

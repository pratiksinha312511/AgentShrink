'use client'

import { useEffect, useState } from 'react'
import Link from 'next/link'
import { acceptPublicInvite, fetchHostedConfig, fetchPublicBilling, fetchPublicIdentity, fetchPublicInvites, fetchPublicProjects, fetchPublicSession, fetchPublicTeams, loginPublicSession, logoutPublicSession } from '@/lib/api'
import {
  PageShell, PageHeader, TerminalCard, TerminalInput, Badge,
  SecondaryButton, ErrorBlock, SuccessBlock,
} from '@/components/Terminal'

type Identity = {
  account?: { id?: string; name?: string; slug?: string }
  project?: { id?: string; name?: string; slug?: string; environment?: string }
  project_name?: string
  project_token_preview?: string
  gateway_url?: string
  docs_url?: string
  dashboard_url?: string
  environment?: string
}

type ProjectsPayload = {
  projects?: Array<{ id: string }>
}

export default function AccountPage() {
  const [identity, setIdentity] = useState<Identity | null>(null)
  const [projectCount, setProjectCount] = useState(0)
  const [teamCount, setTeamCount] = useState(0)
  const [memberCount, setMemberCount] = useState(0)
  const [session, setSession] = useState<any>(null)
  const [pendingInvites, setPendingInvites] = useState<any[]>([])
  const [hostedConfig, setHostedConfig] = useState<any>(null)
  const [billing, setBilling] = useState<any>(null)
  const [userName, setUserName] = useState('Local Owner')
  const [userEmail, setUserEmail] = useState('local-owner@agentshrink.local')
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')

  useEffect(() => {
    Promise.all([fetchPublicIdentity(), fetchPublicProjects(), fetchPublicTeams(), fetchPublicSession(), fetchPublicInvites(), fetchHostedConfig(), fetchPublicBilling()])
      .then(([id, projects, teams, sessionData, invites, hosted, billingData]) => {
        setIdentity(id)
        setProjectCount((projects?.projects || []).length)
        setTeamCount((teams?.teams || []).length)
        setMemberCount((teams?.memberships || []).length)
        setSession(sessionData)
        setPendingInvites(invites?.invites || [])
        setHostedConfig(hosted)
        setBilling(billingData)
        setUserName(sessionData?.user?.name || 'Local Owner')
        setUserEmail(sessionData?.user?.email || 'local-owner@agentshrink.local')
      })
      .catch((e: any) => setError(e.message || 'Failed to load account'))
  }, [])

  const signIn = async () => {
    try {
      setError('')
      const sessionData = await loginPublicSession({ user_name: userName, user_email: userEmail })
      setSession(sessionData)
      setMessage('Local hosted-style session updated.')
    } catch (e: any) {
      setError(e.message || 'Failed to create session')
    }
  }

  const signOut = async () => {
    try {
      setError('')
      const sessionData = await logoutPublicSession()
      setSession(sessionData)
      setMessage('Session cleared.')
    } catch (e: any) {
      setError(e.message || 'Failed to clear session')
    }
  }

  const acceptInvite = async (token: string) => {
    try {
      setError('')
      const result = await acceptPublicInvite(token, { user_name: userName, user_email: userEmail })
      setSession(result?.session || session)
      const invites = await fetchPublicInvites()
      setPendingInvites(invites?.invites || [])
      setMessage('Invite accepted. Your memberships have been updated.')
    } catch (e: any) {
      setError(e.message || 'Failed to accept invite')
    }
  }

  return (
    <PageShell maxWidth={920}>
      <PageHeader
        tag="account"
        title="ACCOUNT"
        description="Account owns projects, projects own tokens and gateway settings."
      />

      {error && <ErrorBlock message={error} />}
      {message && <SuccessBlock message={message} />}

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
        <TerminalCard title="IDENTITY">
          <InfoRow label="account" value={identity?.account?.name || 'Local AgentShrink Workspace'} />
          <InfoRow label="slug" value={identity?.account?.slug || 'local-workspace'} />
          <InfoRow label="teams" value={String(teamCount)} />
          <InfoRow label="members" value={String(memberCount)} />
          <InfoRow label="projects" value={String(projectCount)} />
        </TerminalCard>
        <TerminalCard title="ACTIVE PROJECT">
          <InfoRow label="project" value={identity?.project?.name || identity?.project_name || 'AgentShrink Project'} />
          <InfoRow label="env" value={identity?.project?.environment || identity?.environment || 'local'} />
          <InfoRow label="token" value={identity?.project_token_preview || '-'} />
          <InfoRow label="gateway" value={identity?.gateway_url || '-'} />
        </TerminalCard>
      </div>

      <TerminalCard title="SESSION">
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
          <div>
            <div style={{ fontSize: 10, color: 'var(--text-tertiary)', marginBottom: 4 }}>user name</div>
            <TerminalInput value={userName} onChange={(e) => setUserName(e.target.value)} />
          </div>
          <div>
            <div style={{ fontSize: 10, color: 'var(--text-tertiary)', marginBottom: 4 }}>user email</div>
            <TerminalInput value={userEmail} onChange={(e) => setUserEmail(e.target.value)} />
          </div>
        </div>
        <div style={{ fontSize: 10, color: 'var(--text-secondary)', marginTop: 8 }}>
          state: <code style={{ color: session?.authenticated ? '#38B2AC' : '#9CA3AF' }}>{session?.authenticated ? 'authenticated' : 'signed-out'}</code>
        </div>
        <div style={{ display: 'flex', gap: 8, marginTop: 10 }}>
          <SecondaryButton onClick={signIn}>UPDATE</SecondaryButton>
          <SecondaryButton onClick={signOut}>SIGN OUT</SecondaryButton>
        </div>
      </TerminalCard>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
        <TerminalCard title="PENDING INVITES">
          {(pendingInvites || []).length === 0 ? (
            <div style={{ fontSize: 11, color: 'var(--text-tertiary)' }}>No pending invites.</div>
          ) : (
            <div style={{ display: 'grid', gap: 8 }}>
              {(pendingInvites || []).map((invite) => (
            <div key={invite.id || invite.token} style={{ borderLeft: '3px solid #6C63FF', borderRadius: '0 12px 12px 0', padding: '8px 12px', background: 'rgba(108,99,255,0.04)' }}>
              <div style={{ fontSize: 12, fontWeight: 700, color: '#3D4852' }}>{invite.user_name}</div>
                  <div style={{ fontSize: 10, color: 'var(--text-secondary)' }}>role: <code>{invite.role}</code></div>
                  <div style={{ fontSize: 9, color: 'var(--text-tertiary)', marginTop: 4, wordBreak: 'break-all' }}>token: {invite.token}</div>
                  <SecondaryButton onClick={() => acceptInvite(invite.token)} style={{ marginTop: 6, padding: '3px 8px', fontSize: 9 }}>ACCEPT</SecondaryButton>
                </div>
              ))}
            </div>
          )}
        </TerminalCard>
        <TerminalCard title="HOSTED CONFIG">
          <InfoRow label="mode" value={hostedConfig?.deployment?.mode || 'local-hosted'} />
          <InfoRow label="app url" value={hostedConfig?.deployment?.public_app_url || '-'} />
          <InfoRow label="api url" value={hostedConfig?.deployment?.public_api_url || '-'} />
          <InfoRow label="auth" value={hostedConfig?.auth?.mode || 'session'} />
          <InfoRow label="isolation" value={hostedConfig?.tenancy?.isolation_mode || 'team-scoped'} />
        </TerminalCard>
      </div>

      <TerminalCard title="BILLING SUMMARY">
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr 1fr', gap: 10 }}>
          <InfoRow label="plan" value={billing?.billing?.plan || billing?.hosted?.plan || 'beta'} />
          <InfoRow label="projects" value={String(billing?.metrics?.projects || 0)} />
          <InfoRow label="members" value={String(billing?.metrics?.members || 0)} />
          <InfoRow label="calls" value={String(billing?.metrics?.total_calls || 0)} />
        </div>
        <Link href="/billing" style={{ color: '#6C63FF', fontWeight: 700, fontSize: 12, marginTop: 8, display: 'inline-block' }}>→ billing</Link>
      </TerminalCard>

      <TerminalCard title="NEXT STEPS">
        <div style={{ display: 'grid', gap: 6, fontSize: 11, color: 'var(--text-secondary)' }}>
<div>1. <Link href="/teams" style={{ color: '#6C63FF', fontWeight: 700 }}>Teams</Link> — inspect team separation</div>
            <div>2. <Link href="/projects" style={{ color: '#6C63FF', fontWeight: 700 }}>Projects</Link> — create and activate local projects</div>
            <div>3. <Link href="/settings" style={{ color: '#6C63FF', fontWeight: 700 }}>Settings</Link> — edit project details and rotate token</div>
            <div>4. <Link href="/site/docs" style={{ color: '#6C63FF', fontWeight: 700 }}>Docs</Link> — public integration contract</div>
        </div>
      </TerminalCard>
    </PageShell>
  )
}

function InfoRow({ label, value }: { label: string; value: string }) {
  return (
    <div style={{ display: 'flex', gap: 8, fontSize: 11, marginBottom: 6 }}>
      <span style={{ color: 'var(--text-tertiary)', minWidth: 70 }}>{label}:</span>
      <code style={{ color: 'var(--text-secondary)', wordBreak: 'break-word' }}>{value}</code>
    </div>
  )
}

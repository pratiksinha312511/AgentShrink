'use client'

import { useEffect, useState } from 'react'
import Link from 'next/link'
import { acceptPublicInvite, fetchHostedConfig, fetchPublicBilling, fetchPublicIdentity, fetchPublicInvites, fetchPublicProjects, fetchPublicSession, fetchPublicTeams, loginPublicSession, logoutPublicSession } from '@/lib/api'

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
    <div style={{ maxWidth: 920 }}>
      <div className="card" style={{ padding: 24, marginBottom: 16 }}>
        <div style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-secondary)', marginBottom: 8 }}>Hosted-style workspace identity</div>
        <h1 style={{ fontSize: 24, margin: '0 0 8px', color: 'var(--text-primary)' }}>Account</h1>
        <p style={{ margin: 0, color: 'var(--text-secondary)', lineHeight: 1.7 }}>
          This local repo now exposes the same core contract the hosted product will use: an account owns projects,
          projects own tokens and gateway settings, and apps connect through a project-scoped gateway credential.
        </p>
      </div>

      {(error || message) && (
        <div className="card" style={{ padding: 16, marginBottom: 16, color: error ? '#A32D2D' : '#27500A' }}>
          {error || message}
        </div>
      )}

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
        <div className="card" style={{ padding: 24 }}>
          <div style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-secondary)', marginBottom: 12 }}>Account identity</div>
          <InfoRow label="Account name" value={identity?.account?.name || 'Local AgentShrink Workspace'} />
          <InfoRow label="Account slug" value={identity?.account?.slug || 'local-workspace'} />
          <InfoRow label="Teams" value={String(teamCount)} />
          <InfoRow label="Memberships" value={String(memberCount)} />
          <InfoRow label="Projects" value={String(projectCount)} />
        </div>

        <div className="card" style={{ padding: 24 }}>
          <div style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-secondary)', marginBottom: 12 }}>Active project</div>
          <InfoRow label="Project" value={identity?.project?.name || identity?.project_name || 'AgentShrink Project'} />
          <InfoRow label="Environment" value={identity?.project?.environment || identity?.environment || 'local'} />
          <InfoRow label="Token preview" value={identity?.project_token_preview || '-'} mono />
          <InfoRow label="Gateway" value={identity?.gateway_url || '-'} mono />
        </div>
      </div>

      <div className="card" style={{ padding: 24, marginTop: 16 }}>
        <div style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-secondary)', marginBottom: 12 }}>Hosted-style session</div>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
          <label style={{ display: 'grid', gap: 6 }}>
            <span style={{ fontSize: 12, color: 'var(--text-secondary)' }}>User name</span>
            <input value={userName} onChange={(e) => setUserName(e.target.value)} style={inputStyle} />
          </label>
          <label style={{ display: 'grid', gap: 6 }}>
            <span style={{ fontSize: 12, color: 'var(--text-secondary)' }}>User email</span>
            <input value={userEmail} onChange={(e) => setUserEmail(e.target.value)} style={inputStyle} />
          </label>
        </div>
        <div style={{ fontSize: 12, color: 'var(--text-secondary)', marginTop: 10 }}>
          Session state: <code>{session?.authenticated ? 'authenticated' : 'signed-out'}</code>
        </div>
        <div style={{ display: 'flex', gap: 8, marginTop: 12, flexWrap: 'wrap' }}>
          <button onClick={signIn} style={buttonStyle}>Update session</button>
          <button onClick={signOut} style={buttonStyle}>Sign out</button>
        </div>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16, marginTop: 16 }}>
        <div className="card" style={{ padding: 24 }}>
          <div style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-secondary)', marginBottom: 12 }}>Pending invites</div>
          {(pendingInvites || []).length === 0 && (
            <div style={{ fontSize: 12, color: 'var(--text-secondary)' }}>No pending invites for the signed-in email.</div>
          )}
          <div style={{ display: 'grid', gap: 10 }}>
            {(pendingInvites || []).map((invite) => (
              <div key={invite.id || invite.token} style={{ background: 'var(--bg-secondary)', borderRadius: 10, padding: '12px 14px' }}>
                <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--text-primary)' }}>{invite.user_name}</div>
                <div style={{ fontSize: 12, color: 'var(--text-secondary)', marginTop: 4 }}>
                  Team invite for <code>{invite.role}</code>
                </div>
                <div style={{ fontSize: 11, color: 'var(--text-tertiary)', marginTop: 6, wordBreak: 'break-all' }}>
                  token: <code>{invite.token}</code>
                </div>
                <div style={{ marginTop: 10 }}>
                  <button onClick={() => acceptInvite(invite.token)} style={buttonStyle}>Accept invite</button>
                </div>
              </div>
            ))}
          </div>
        </div>

        <div className="card" style={{ padding: 24 }}>
          <div style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-secondary)', marginBottom: 12 }}>Hosted deployment split</div>
          <InfoRow label="Deployment mode" value={hostedConfig?.deployment?.mode || 'local-hosted'} />
          <InfoRow label="Public app URL" value={hostedConfig?.deployment?.public_app_url || '-'} mono />
          <InfoRow label="Public API URL" value={hostedConfig?.deployment?.public_api_url || '-'} mono />
          <InfoRow label="Auth mode" value={hostedConfig?.auth?.mode || 'session'} />
          <InfoRow label="Tenant isolation" value={hostedConfig?.tenancy?.isolation_mode || 'team-scoped'} />
        </div>
      </div>

      <div className="card" style={{ padding: 24, marginTop: 16 }}>
        <div style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-secondary)', marginBottom: 12 }}>Billing and tenant summary</div>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr 1fr', gap: 12 }}>
          <InfoRow label="Plan" value={billing?.billing?.plan || billing?.hosted?.plan || 'beta'} />
          <InfoRow label="Projects" value={String(billing?.metrics?.projects || 0)} />
          <InfoRow label="Members" value={String(billing?.metrics?.members || 0)} />
          <InfoRow label="Total calls" value={String(billing?.metrics?.total_calls || 0)} />
        </div>
        <div style={{ fontSize: 12, color: 'var(--text-secondary)', marginTop: 10 }}>
          This is the first hosted-style billing shell. It tracks tenant/account metadata and usage summary, but it is not a production billing engine yet.
        </div>
        <div style={{ marginTop: 10 }}>
          <Link href="/billing" style={linkStyle}>Open billing view</Link>
        </div>
      </div>

      <div className="card" style={{ padding: 24, marginTop: 16 }}>
        <div style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-secondary)', marginBottom: 12 }}>Next hosted-product steps</div>
        <div style={{ display: 'grid', gap: 10, fontSize: 13, color: 'var(--text-secondary)' }}>
          <div>1. Use <Link href="/teams" style={linkStyle}>Teams</Link> to inspect team separation and workspace membership.</div>
          <div>2. Use <Link href="/projects" style={linkStyle}>Projects</Link> to create and activate local projects with hosted-style identity.</div>
          <div>3. Use <Link href="/settings" style={linkStyle}>Settings</Link> to edit active project details and rotate its token.</div>
          <div>4. Open <Link href="/site/docs" style={linkStyle}>public docs</Link> to see the outward-facing integration contract.</div>
        </div>
      </div>
    </div>
  )
}

function InfoRow({ label, value, mono = false }: { label: string; value: string; mono?: boolean }) {
  return (
    <div style={{ background: 'var(--bg-secondary)', borderRadius: 10, padding: '12px 14px', marginBottom: 10 }}>
      <div style={{ fontSize: 11, textTransform: 'uppercase', color: 'var(--text-tertiary)', marginBottom: 4 }}>{label}</div>
      <div style={{ fontSize: 13, color: 'var(--text-primary)', fontFamily: mono ? 'monospace' : undefined, wordBreak: 'break-word' }}>{value}</div>
    </div>
  )
}

const linkStyle = {
  color: '#185FA5',
  textDecoration: 'none',
  fontWeight: 600,
} as const

const inputStyle = {
  width: '100%',
  borderRadius: 10,
  border: '0.5px solid var(--border)',
  background: 'var(--bg-primary)',
  color: 'var(--text-primary)',
  padding: '10px 12px',
  fontSize: 13,
} as const

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

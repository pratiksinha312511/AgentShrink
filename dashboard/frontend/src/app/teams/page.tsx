'use client'

import { useEffect, useState } from 'react'
import { createPublicTeam, fetchPublicTeams, invitePublicTeamMember, updatePublicTeamMemberRole } from '@/lib/api'

type TeamPayload = {
  account?: { name?: string }
  teams?: Array<{ id: string; name: string; slug: string; role?: string }>
  memberships?: Array<{ team_id: string; user_name: string; user_email: string; role: string }>
  projects?: Array<{ id: string; name: string; team_id: string; environment?: string }>
  invites?: Array<{ id: string; team_id: string; user_name: string; user_email: string; role: string; token: string; status: string }>
}

export default function TeamsPage() {
  const [data, setData] = useState<TeamPayload | null>(null)
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')
  const [teamName, setTeamName] = useState('')
  const [creating, setCreating] = useState(false)
  const [inviteState, setInviteState] = useState<Record<string, { user_name: string; user_email: string; role: string }>>({})

  const load = () => {
    fetchPublicTeams().then(setData).catch((e: any) => setError(e.message || 'Failed to load teams'))
  }

  useEffect(() => {
    load()
  }, [])

  const createTeam = async () => {
    if (!teamName.trim()) {
      setError('Team name is required')
      return
    }
    setCreating(true)
    setError('')
    setMessage('')
    try {
      await createPublicTeam({ name: teamName.trim() })
      setTeamName('')
      setMessage('Team created.')
      load()
    } catch (e: any) {
      setError(e.message || 'Failed to create team')
    } finally {
      setCreating(false)
    }
  }

  const invite = async (teamId: string) => {
    const state = inviteState[teamId]
    if (!state?.user_name?.trim() || !state?.user_email?.trim()) {
      setError('Invitee name and email are required')
      return
    }
    setError('')
    setMessage('')
    try {
      const result = await invitePublicTeamMember(teamId, state)
      const inviteToken = result?.invite?.token ? ` Invite token: ${result.invite.token}` : ''
      setMessage(`Team invite created.${inviteToken}`)
      setInviteState((current) => ({ ...current, [teamId]: { user_name: '', user_email: '', role: 'member' } }))
      load()
    } catch (e: any) {
      setError(e.message || 'Failed to invite team member')
    }
  }

  const updateRole = async (teamId: string, userEmail: string, role: string) => {
    setError('')
    setMessage('')
    try {
      await updatePublicTeamMemberRole(teamId, userEmail, { role })
      setMessage('Role updated.')
      load()
    } catch (e: any) {
      setError(e.message || 'Failed to update team role')
    }
  }

  return (
    <div style={{ maxWidth: 980 }}>
      <div className="card" style={{ padding: 24, marginBottom: 16 }}>
        <div style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-secondary)', marginBottom: 8 }}>Hosted-style team separation</div>
        <h1 style={{ fontSize: 24, margin: '0 0 8px', color: 'var(--text-primary)' }}>Teams</h1>
        <p style={{ margin: 0, color: 'var(--text-secondary)', lineHeight: 1.7 }}>
          Projects can now belong to a team, and the local product keeps team membership visible so the future hosted
          separation model is already reflected in the workspace structure.
        </p>
      </div>

      {(message || error) && (
        <div className="card" style={{ padding: 16, marginBottom: 16, color: error ? '#A32D2D' : '#27500A' }}>
          {error || message}
        </div>
      )}

      <div className="card" style={{ padding: 24, marginBottom: 16 }}>
        <div style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-secondary)', marginBottom: 10 }}>Create team</div>
        <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
          <input value={teamName} onChange={(e) => setTeamName(e.target.value)} placeholder="Growth Team" style={inputStyle} />
          <button onClick={createTeam} disabled={creating} style={{ ...buttonStyle, opacity: creating ? 0.7 : 1 }}>
            {creating ? 'Creating...' : 'Create team'}
          </button>
        </div>
      </div>

      <div style={{ display: 'grid', gap: 16 }}>
        {(data?.teams || []).map((team) => {
          const memberships = (data?.memberships || []).filter((membership) => membership.team_id === team.id)
          const projects = (data?.projects || []).filter((project) => project.team_id === team.id)
          const invites = (data?.invites || []).filter((invite) => invite.team_id === team.id && invite.status === 'pending')
          return (
            <div key={team.id} className="card" style={{ padding: 24 }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12, alignItems: 'center', flexWrap: 'wrap', marginBottom: 12 }}>
                <div>
                  <div style={{ fontSize: 16, fontWeight: 600, color: 'var(--text-primary)' }}>{team.name}</div>
                  <div style={{ fontSize: 12, color: 'var(--text-tertiary)', marginTop: 4 }}>
                    <code>{team.slug}</code>
                  </div>
                </div>
                <span className="badge" style={{ background: '#EEEDFE', color: '#3C3489' }}>
                  {projects.length} project{projects.length === 1 ? '' : 's'}
                </span>
              </div>

              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
                <div>
                  <div style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-secondary)', marginBottom: 8 }}>Membership</div>
                  <div style={{ display: 'grid', gap: 8 }}>
                    {memberships.map((membership, idx) => (
                      <div key={`${membership.user_email}-${idx}`} style={{ background: 'var(--bg-secondary)', borderRadius: 10, padding: '10px 12px' }}>
                        <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--text-primary)' }}>{membership.user_name}</div>
                        <div style={{ fontSize: 12, color: 'var(--text-secondary)' }}>{membership.user_email}</div>
                        <div style={{ display: 'flex', justifyContent: 'space-between', gap: 10, alignItems: 'center', marginTop: 6, flexWrap: 'wrap' }}>
                          <div style={{ fontSize: 11, color: 'var(--text-tertiary)' }}>role: <code>{membership.role}</code></div>
                          <select value={membership.role} onChange={(e) => updateRole(team.id, membership.user_email, e.target.value)} style={{ ...inputStyle, minWidth: 140, padding: '6px 8px', fontSize: 12 }}>
                            <option value="owner">owner</option>
                            <option value="admin">admin</option>
                            <option value="member">member</option>
                            <option value="viewer">viewer</option>
                          </select>
                        </div>
                      </div>
                    ))}
                  </div>
                  <div style={{ marginTop: 10, background: '#FBF8F1', borderRadius: 10, padding: '12px 14px' }}>
                    <div style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-secondary)', marginBottom: 8 }}>Invite teammate</div>
                    <div style={{ display: 'grid', gap: 8 }}>
                      <input
                        value={inviteState[team.id]?.user_name || ''}
                        onChange={(e) => setInviteState((current) => ({ ...current, [team.id]: { ...(current[team.id] || { role: 'member' }), user_name: e.target.value } }))}
                        placeholder="Teammate name"
                        style={inputStyle}
                      />
                      <input
                        value={inviteState[team.id]?.user_email || ''}
                        onChange={(e) => setInviteState((current) => ({ ...current, [team.id]: { ...(current[team.id] || { role: 'member' }), user_email: e.target.value } }))}
                        placeholder="teammate@example.com"
                        style={inputStyle}
                      />
                      <select
                        value={inviteState[team.id]?.role || 'member'}
                        onChange={(e) => setInviteState((current) => ({ ...current, [team.id]: { ...(current[team.id] || {}), role: e.target.value } as any }))}
                        style={inputStyle}
                      >
                        <option value="member">member</option>
                        <option value="viewer">viewer</option>
                        <option value="admin">admin</option>
                      </select>
                      <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
                        <button onClick={() => invite(team.id)} style={buttonStyle}>Invite member</button>
                      </div>
                    </div>
                  </div>
                </div>

                <div>
                  <div style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-secondary)', marginBottom: 8 }}>Projects in team</div>
                  <div style={{ display: 'grid', gap: 8 }}>
                    {projects.map((project) => (
                      <div key={project.id} style={{ background: 'var(--bg-secondary)', borderRadius: 10, padding: '10px 12px' }}>
                        <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--text-primary)' }}>{project.name}</div>
                        <div style={{ fontSize: 11, color: 'var(--text-tertiary)', marginTop: 4 }}>environment: <code>{project.environment || 'local'}</code></div>
                      </div>
                    ))}
                  </div>
                  <div style={{ marginTop: 12 }}>
                    <div style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-secondary)', marginBottom: 8 }}>Pending invites</div>
                    <div style={{ display: 'grid', gap: 8 }}>
                      {invites.length === 0 && (
                        <div style={{ fontSize: 12, color: 'var(--text-tertiary)' }}>No pending invites.</div>
                      )}
                      {invites.map((invite) => (
                        <div key={invite.id} style={{ background: 'var(--bg-secondary)', borderRadius: 10, padding: '10px 12px' }}>
                          <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--text-primary)' }}>{invite.user_name}</div>
                          <div style={{ fontSize: 12, color: 'var(--text-secondary)', marginTop: 4 }}>{invite.user_email} · <code>{invite.role}</code></div>
                          <div style={{ fontSize: 11, color: 'var(--text-tertiary)', marginTop: 6, wordBreak: 'break-all' }}>
                            token: <code>{invite.token}</code>
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                </div>
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}

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

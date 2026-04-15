'use client'

import { useEffect, useState } from 'react'
import { createPublicTeam, fetchPublicTeams, invitePublicTeamMember, updatePublicTeamMemberRole } from '@/lib/api'
import { PageShell, PageHeader, TerminalCard, TerminalInput, TerminalSelect, FieldLabel, PrimaryButton, SecondaryButton, Badge, ErrorBlock, SuccessBlock, EmptyState } from '@/components/Terminal'

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
    <PageShell maxWidth={980}>
      <PageHeader
        title="TEAMS"
        tag="org"
        description="Projects belong to a team. The local product keeps team membership visible so the future hosted separation model is already reflected."
      />

      {error && <ErrorBlock message={error} />}
      {message && !error && <SuccessBlock message={message} />}

      <TerminalCard title="CREATE TEAM">
        <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap', alignItems: 'flex-end' }}>
          <div style={{ flex: 1, minWidth: 200 }}>
          <FieldLabel label="team name">
            <TerminalInput value={teamName} onChange={(e) => setTeamName(e.target.value)} placeholder="Growth Team" />
          </FieldLabel>
          </div>
          <PrimaryButton onClick={createTeam} disabled={creating}>
            {creating ? 'CREATING...' : 'CREATE TEAM'}
          </PrimaryButton>
        </div>
      </TerminalCard>

      <div style={{ display: 'grid', gap: 16 }}>
        {(data?.teams || []).length === 0 && (
          <EmptyState message="No teams" hint="Create your first team above." />
        )}
        {(data?.teams || []).map((team) => {
          const memberships = (data?.memberships || []).filter((m) => m.team_id === team.id)
          const projects = (data?.projects || []).filter((p) => p.team_id === team.id)
          const invites = (data?.invites || []).filter((inv) => inv.team_id === team.id && inv.status === 'pending')
          return (
            <TerminalCard key={team.id} title={team.name.toUpperCase()} headerRight={
              <Badge variant="purple">{projects.length} project{projects.length === 1 ? '' : 's'}</Badge>
            }>
              <div style={{ fontSize: 12, color: 'var(--text-tertiary)', marginBottom: 16 }}>
                slug: <code style={{ color: '#6C63FF' }}>{team.slug}</code>
              </div>

              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
                {/* Left: Membership + Invite */}
                <div>
                  <div style={{ fontSize: 11, textTransform: 'uppercase', color: 'var(--text-tertiary)', marginBottom: 8 }}>Members</div>
                  <div style={{ display: 'grid', gap: 6 }}>
                    {memberships.map((m, idx) => (
                      <div key={`${m.user_email}-${idx}`} style={{ border: '1px solid var(--border)', padding: '10px 12px' }}>
                        <div style={{ fontSize: 13, color: 'var(--text-primary)' }}>{m.user_name}</div>
                        <div style={{ fontSize: 12, color: 'var(--text-secondary)' }}>{m.user_email}</div>
                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginTop: 6, gap: 10 }}>
                          <Badge variant={m.role === 'owner' ? 'green' : m.role === 'admin' ? 'amber' : 'default'}>{m.role}</Badge>
                          <TerminalSelect value={m.role} onChange={(e) => updateRole(team.id, m.user_email, e.target.value)} style={{ minWidth: 120 }}>
                            <option value="owner">owner</option>
                            <option value="admin">admin</option>
                            <option value="member">member</option>
                            <option value="viewer">viewer</option>
                          </TerminalSelect>
                        </div>
                      </div>
                    ))}
                  </div>

                  <div style={{ border: '1px solid var(--border)', padding: '12px 14px', marginTop: 10 }}>
                    <div style={{ fontSize: 11, textTransform: 'uppercase', color: 'var(--text-tertiary)', marginBottom: 8 }}>Invite Teammate</div>
                    <div style={{ display: 'grid', gap: 8 }}>
                      <TerminalInput
                        value={inviteState[team.id]?.user_name || ''}
                        onChange={(e) => setInviteState((cur) => ({ ...cur, [team.id]: { ...(cur[team.id] || { role: 'member' }), user_name: e.target.value } }))}
                        placeholder="Teammate name"
                      />
                      <TerminalInput
                        value={inviteState[team.id]?.user_email || ''}
                        onChange={(e) => setInviteState((cur) => ({ ...cur, [team.id]: { ...(cur[team.id] || { role: 'member' }), user_email: e.target.value } }))}
                        placeholder="teammate@example.com"
                      />
                      <TerminalSelect
                        value={inviteState[team.id]?.role || 'member'}
                        onChange={(e) => setInviteState((cur) => ({ ...cur, [team.id]: { ...(cur[team.id] || {}), role: e.target.value } as any }))}
                      >
                        <option value="member">member</option>
                        <option value="viewer">viewer</option>
                        <option value="admin">admin</option>
                      </TerminalSelect>
                      <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
                        <SecondaryButton onClick={() => invite(team.id)}>INVITE</SecondaryButton>
                      </div>
                    </div>
                  </div>
                </div>

                {/* Right: Projects + Pending invites */}
                <div>
                  <div style={{ fontSize: 11, textTransform: 'uppercase', color: 'var(--text-tertiary)', marginBottom: 8 }}>Projects</div>
                  <div style={{ display: 'grid', gap: 6 }}>
                    {projects.map((p) => (
                      <div key={p.id} style={{ border: '1px solid var(--border)', padding: '10px 12px' }}>
                        <div style={{ fontSize: 13, color: 'var(--text-primary)' }}>{p.name}</div>
                        <div style={{ fontSize: 11, color: 'var(--text-tertiary)', marginTop: 4 }}>
                          env: <code style={{ color: '#6C63FF' }}>{p.environment || 'local'}</code>
                        </div>
                      </div>
                    ))}
                    {projects.length === 0 && (
                      <div style={{ fontSize: 12, color: 'var(--text-tertiary)' }}>No projects in team.</div>
                    )}
                  </div>

                  <div style={{ marginTop: 12 }}>
                    <div style={{ fontSize: 11, textTransform: 'uppercase', color: 'var(--text-tertiary)', marginBottom: 8 }}>Pending Invites</div>
                    <div style={{ display: 'grid', gap: 6 }}>
                      {invites.length === 0 && (
                        <div style={{ fontSize: 12, color: 'var(--text-tertiary)' }}>No pending invites.</div>
                      )}
                      {invites.map((inv) => (
                        <div key={inv.id} style={{ border: '1px solid var(--border)', padding: '10px 12px' }}>
                          <div style={{ fontSize: 13, color: 'var(--text-primary)' }}>{inv.user_name}</div>
                          <div style={{ fontSize: 12, color: 'var(--text-secondary)', marginTop: 4 }}>
                            {inv.user_email} · <Badge variant="amber">{inv.role}</Badge>
                          </div>
                          <div style={{ fontSize: 11, color: 'var(--text-tertiary)', marginTop: 6, wordBreak: 'break-all' }}>
                            token: <code style={{ color: '#6C63FF' }}>{inv.token}</code>
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                </div>
              </div>
            </TerminalCard>
          )
        })}
      </div>
    </PageShell>
  )
}

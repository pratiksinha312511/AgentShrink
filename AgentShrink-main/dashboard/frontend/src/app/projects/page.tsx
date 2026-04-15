'use client'

import { useEffect, useState } from 'react'
import { activatePublicProject, createPublicProject, fetchProductProviders, fetchPublicProjects } from '@/lib/api'
import {
  PageShell, PageHeader, TerminalCard, FieldLabel, TerminalInput,
  TerminalSelect, PrimaryButton, SecondaryButton, Badge,
  LoadingTerminal, ErrorBlock, SuccessBlock,
} from '@/components/Terminal'

type ProjectRecord = {
  id: string
  name: string
  slug: string
  environment?: string
  config?: {
    gateway?: { upstream_provider?: string; port?: number }
    dashboard_frontend?: { port?: number }
    db_path?: string
  }
  usage?: {
    has_data?: boolean
    total_calls?: number
    total_runs?: number
    latest_timestamp?: string | null
    gateway_event_count?: number
  }
}

type RegistryPayload = {
  account?: { id?: string; name?: string; slug?: string }
  active_project_id?: string
  projects?: ProjectRecord[]
  active_config?: any
  teams?: Array<{ id: string; name: string }>
}

type ProviderConfig = {
  id: string
  name: string
  enabled?: boolean
}

export default function ProjectsPage() {
  const [data, setData] = useState<RegistryPayload | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [creating, setCreating] = useState(false)
  const [switchingId, setSwitchingId] = useState('')
  const [name, setName] = useState('')
  const [environment, setEnvironment] = useState('local')
  const [upstream, setUpstream] = useState('mock')
  const [message, setMessage] = useState('')
  const [providers, setProviders] = useState<ProviderConfig[]>([])

  const load = async () => {
    try {
      const next = await fetchPublicProjects()
      setData(next)
      setError('')
    } catch (e: any) {
      setError(e.message || 'Failed to load projects')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    load()
    fetchProductProviders().then(result => setProviders(result.providers || [])).catch(() => {})
  }, [])

  const createProject = async () => {
    if (!name.trim()) {
      setError('Project name is required')
      return
    }
    setCreating(true)
    setError('')
    setMessage('')
    try {
      const next = await createPublicProject({
        name: name.trim(),
        environment,
        upstream_provider: upstream,
      })
      setData(next)
      setName('')
      setMessage('Project created and activated. Restart the local stack so ports and runtime settings switch cleanly.')
    } catch (e: any) {
      setError(e.message || 'Failed to create project')
    } finally {
      setCreating(false)
    }
  }

  const activateProject = async (projectId: string) => {
    setSwitchingId(projectId)
    setError('')
    setMessage('')
    try {
      const next = await activatePublicProject(projectId)
      setData(next)
      setMessage('Project switched. Restart the local stack so the new project ports and DB take effect everywhere.')
    } catch (e: any) {
      setError(e.message || 'Failed to switch project')
    } finally {
      setSwitchingId('')
    }
  }

  const timeAgo = (ts: string | null | undefined) => {
    if (!ts) return 'never'
    const diff = Date.now() - Date.parse(ts)
    if (diff < 60000) return 'just now'
    if (diff < 3600000) return `${Math.floor(diff / 60000)}m ago`
    if (diff < 86400000) return `${Math.floor(diff / 3600000)}h ago`
    return `${Math.floor(diff / 86400000)}d ago`
  }

  if (loading) return <LoadingTerminal message="loading projects" />

  return (
    <PageShell maxWidth={960}>
      <PageHeader
        tag="workspace"
        title="PROJECTS"
        description="Each project has its own gateway token, ports, database, and upstream provider defaults."
      />

      {error && <ErrorBlock message={error} />}
      {message && <SuccessBlock message={message} />}

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1.2fr', gap: 16 }}>
        {/* ── Create form ── */}
        <TerminalCard title="NEW PROJECT">
          <div style={{ display: 'grid', gap: 12 }}>
            <FieldLabel label="project name">
              <TerminalInput value={name} onChange={(e) => setName(e.target.value)} placeholder="support-automation-beta" />
            </FieldLabel>
            <FieldLabel label="environment">
              <TerminalSelect value={environment} onChange={(e) => setEnvironment(e.target.value)}>
                <option value="local">local</option>
                <option value="staging">staging</option>
                <option value="production">production</option>
              </TerminalSelect>
            </FieldLabel>
            <FieldLabel label="upstream provider">
              <TerminalSelect value={upstream} onChange={(e) => setUpstream(e.target.value)}>
                {providers.filter(p => p.enabled !== false).map((p) => (
                  <option key={p.id} value={p.id}>{p.name} ({p.id})</option>
                ))}
              </TerminalSelect>
            </FieldLabel>
          </div>
          <div style={{ display: 'flex', justifyContent: 'flex-end', marginTop: 16 }}>
            <PrimaryButton onClick={createProject} disabled={creating}>
              {creating ? 'CREATING...' : 'CREATE'}
            </PrimaryButton>
          </div>
        </TerminalCard>

        {/* ── Project list ── */}
        <TerminalCard title={data?.account?.name?.toUpperCase() || 'WORKSPACE'} noPadding>
          {(data?.projects || []).map((project) => {
            const active = data?.active_project_id === project.id
            const calls = project.usage?.total_calls ?? 0
            const gwEvents = project.usage?.gateway_event_count ?? 0
            return (
              <div
                key={project.id}
                style={{
                  padding: '14px 16px',
                  borderBottom: '1px solid var(--border)',
                  background: active ? 'var(--terminal-green-bg)' : 'transparent',
                  borderLeft: active ? '3px solid #6C63FF' : '3px solid transparent',
                }}
              >
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 12 }}>
                  <div>
                    <div style={{
                      fontSize: 13,
                      fontWeight: active ? 700 : 500,
                      color: active ? '#6C63FF' : '#3D4852',
                    }}>
                      {project.name}
                    </div>
                    <div style={{ fontSize: 11, color: 'var(--text-secondary)', marginTop: 2 }}>
                      <code>{project.slug}</code> · <code>{project.environment || 'local'}</code>
                      {' · '}<span style={{ color: 'var(--text-tertiary)' }}>
                        {calls} calls · {gwEvents} gw · last: {timeAgo(project.usage?.latest_timestamp)}
                      </span>
                    </div>
                  </div>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                    {active ? (
                      <Badge variant="green">ACTIVE</Badge>
                    ) : (
                      <SecondaryButton
                        onClick={() => activateProject(project.id)}
                        disabled={switchingId === project.id}
                        style={{ padding: '4px 10px', fontSize: 10 }}
                      >
                        {switchingId === project.id ? 'SWITCHING...' : 'ACTIVATE'}
                      </SecondaryButton>
                    )}
                  </div>
                </div>
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 6, marginTop: 8, fontSize: 11, color: 'var(--text-tertiary)' }}>
                  <div>provider: <code style={{ color: 'var(--text-secondary)' }}>{project.config?.gateway?.upstream_provider || 'mock'}</code></div>
                  <div>gateway: <code style={{ color: 'var(--text-secondary)' }}>{project.config?.gateway?.port ?? '-'}</code></div>
                  <div>frontend: <code style={{ color: 'var(--text-secondary)' }}>{project.config?.dashboard_frontend?.port ?? '-'}</code></div>
                  <div style={{ wordBreak: 'break-all' }}>db: <code style={{ color: 'var(--text-secondary)' }}>{project.config?.db_path || '-'}</code></div>
                </div>
              </div>
            )
          })}
        </TerminalCard>
      </div>
    </PageShell>
  )
}

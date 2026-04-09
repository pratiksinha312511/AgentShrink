'use client'

import { useEffect, useState } from 'react'
import { activatePublicProject, createPublicProject, fetchProductProviders, fetchPublicProjectActivity, fetchPublicProjects } from '@/lib/api'

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

type ProjectActivityPayload = {
  project?: { id?: string; name?: string; slug?: string; environment?: string; team_id?: string }
  usage?: { total_calls?: number; total_runs?: number; latest_timestamp?: string | null; gateway_event_count?: number; has_data?: boolean }
  recent_calls?: Array<{ timestamp?: string; node_name?: string; model_name?: string; prompt_preview?: string; latency_ms?: number; gateway_mode?: string; provider?: string }>
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
  const [selectedProjectId, setSelectedProjectId] = useState('')
  const [activity, setActivity] = useState<ProjectActivityPayload | null>(null)
  const [activityLoading, setActivityLoading] = useState(false)
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

  useEffect(() => {
    const activeId = selectedProjectId || data?.active_project_id
    if (!activeId) return
    setActivityLoading(true)
    fetchPublicProjectActivity(activeId, 12)
      .then(setActivity)
      .catch(() => setActivity(null))
      .finally(() => setActivityLoading(false))
  }, [data, selectedProjectId])

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
      setSelectedProjectId(next.active_project_id || '')
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
      setSelectedProjectId(projectId)
      setMessage('Project switched. Restart the local stack so the new project ports and DB take effect everywhere.')
    } catch (e: any) {
      setError(e.message || 'Failed to switch project')
    } finally {
      setSwitchingId('')
    }
  }

  if (loading) return <div style={{ color: 'var(--text-tertiary)', padding: 40, textAlign: 'center' }}>Loading projects...</div>

  return (
    <div style={{ maxWidth: 980 }}>
      <div className="card" style={{ padding: 24, marginBottom: 16 }}>
        <div style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-secondary)', marginBottom: 8 }}>Local project flow</div>
        <h1 style={{ fontSize: 24, margin: '0 0 8px', color: 'var(--text-primary)' }}>Projects</h1>
        <p style={{ margin: 0, color: 'var(--text-secondary)', lineHeight: 1.7 }}>
          This local workspace can hold multiple projects, each with its own gateway token, ports, database, and upstream provider defaults.
        </p>
      </div>

      {(error || message) && (
        <div className="card" style={{ padding: 16, marginBottom: 16, color: error ? '#A32D2D' : '#27500A' }}>
          {error || message}
        </div>
      )}

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1.2fr', gap: 16 }}>
        <div className="card" style={{ padding: 24 }}>
          <div style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-secondary)', marginBottom: 12 }}>Create a new project</div>
          <div style={{ display: 'grid', gap: 10 }}>
            <Field label="Project name">
              <input value={name} onChange={(e) => setName(e.target.value)} style={inputStyle} placeholder="Support automation beta" />
            </Field>
            <Field label="Environment">
              <select value={environment} onChange={(e) => setEnvironment(e.target.value)} style={inputStyle}>
                <option value="local">local</option>
                <option value="staging">staging</option>
                <option value="production">production</option>
              </select>
            </Field>
            <Field label="Default upstream provider">
              <select value={upstream} onChange={(e) => setUpstream(e.target.value)} style={inputStyle}>
                {providers.filter(provider => provider.enabled !== false).map((option) => (
                  <option key={option.id} value={option.id}>{option.name} ({option.id})</option>
                ))}
              </select>
            </Field>
          </div>
          <div style={{ marginTop: 14, fontSize: 12, color: 'var(--text-tertiary)', lineHeight: 1.6 }}>
            Save creates the project immediately and activates it as the local default.
          </div>
          <div style={{ display: 'flex', justifyContent: 'flex-end', marginTop: 16 }}>
            <button onClick={createProject} disabled={creating} style={{ ...primaryButtonStyle, opacity: creating ? 0.7 : 1 }}>
              {creating ? 'Creating...' : 'Create project'}
            </button>
          </div>
        </div>

        <div className="card" style={{ padding: 24 }}>
          <div style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-secondary)', marginBottom: 12 }}>
            {data?.account?.name || 'Local AgentShrink Workspace'}
          </div>
          <div style={{ display: 'grid', gap: 12 }}>
            {(data?.projects || []).map((project) => {
              const active = data?.active_project_id === project.id
              return (
                <div key={project.id} onClick={() => setSelectedProjectId(project.id)} style={{ border: '0.5px solid var(--border)', borderRadius: 12, padding: 16, background: active ? '#F3FAF6' : 'var(--bg-secondary)', cursor: 'pointer' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12, alignItems: 'center', flexWrap: 'wrap' }}>
                    <div>
                      <div style={{ fontSize: 14, fontWeight: 600, color: 'var(--text-primary)' }}>{project.name}</div>
                      <div style={{ fontSize: 12, color: 'var(--text-tertiary)', marginTop: 4 }}>
                        <code>{project.slug}</code> · <code>{project.environment || 'local'}</code>
                      </div>
                    </div>
                    <span className="badge" style={{ background: active ? '#EAF3DE' : '#EEEDFE', color: active ? '#27500A' : '#3C3489' }}>
                      {active ? 'Active project' : 'Saved project'}
                    </span>
                  </div>
                  <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8, marginTop: 12, fontSize: 12, color: 'var(--text-secondary)' }}>
                    <div>Gateway provider: <code>{project.config?.gateway?.upstream_provider || 'mock'}</code></div>
                    <div>Gateway port: <code>{project.config?.gateway?.port ?? '-'}</code></div>
                    <div>Frontend port: <code>{project.config?.dashboard_frontend?.port ?? '-'}</code></div>
                    <div style={{ wordBreak: 'break-all' }}>DB: <code>{project.config?.db_path || '-'}</code></div>
                    <div>Total calls: <code>{project.usage?.total_calls ?? 0}</code></div>
                    <div>Gateway events: <code>{project.usage?.gateway_event_count ?? 0}</code></div>
                  </div>
                  {!active && (
                    <div style={{ display: 'flex', justifyContent: 'flex-end', marginTop: 12 }}>
                      <button onClick={() => activateProject(project.id)} disabled={switchingId === project.id} style={{ ...secondaryButtonStyle, opacity: switchingId === project.id ? 0.7 : 1 }}>
                        {switchingId === project.id ? 'Switching...' : 'Activate'}
                      </button>
                    </div>
                  )}
                </div>
              )
            })}
          </div>
        </div>
      </div>

      <div className="card" style={{ padding: 24, marginTop: 16 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12, alignItems: 'center', marginBottom: 12, flexWrap: 'wrap' }}>
          <div>
            <div style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-secondary)', marginBottom: 6 }}>Project-scoped usage and activity</div>
            <div style={{ fontSize: 13, color: 'var(--text-secondary)' }}>
              {activity?.project?.name || 'Select a project'} · project-scoped activity
            </div>
          </div>
          {activity?.usage && (
            <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
              <span className="badge" style={{ background: '#EAF3DE', color: '#27500A' }}>{activity.usage.total_calls ?? 0} calls</span>
              <span className="badge" style={{ background: '#EEEDFE', color: '#3C3489' }}>{activity.usage.total_runs ?? 0} runs</span>
              <span className="badge" style={{ background: '#E6F1FB', color: '#0C447C' }}>{activity.usage.gateway_event_count ?? 0} gateway events</span>
            </div>
          )}
        </div>
        {activityLoading ? (
          <div style={{ color: 'var(--text-tertiary)', fontSize: 13 }}>Loading activity...</div>
        ) : !(activity?.recent_calls || []).length ? (
          <div style={{ color: 'var(--text-tertiary)', fontSize: 13 }}>No activity captured yet for this project.</div>
        ) : (
          <div style={{ display: 'grid', gap: 10 }}>
            {(activity?.recent_calls || []).map((call, idx) => (
              <div key={`${call.timestamp}-${idx}`} style={{ background: 'var(--bg-secondary)', borderRadius: 10, padding: '12px 14px' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', gap: 10, flexWrap: 'wrap', marginBottom: 6 }}>
                  <div style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-primary)' }}>{call.node_name || 'unknown-node'}</div>
                  <div style={{ fontSize: 11, color: 'var(--text-tertiary)' }}>{call.timestamp || 'n/a'}</div>
                </div>
                <div style={{ fontSize: 12, color: 'var(--text-secondary)', lineHeight: 1.6, marginBottom: 6 }}>
                  {call.prompt_preview || ''}
                </div>
                <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', fontSize: 11, color: 'var(--text-tertiary)' }}>
                  <span>model: <code>{call.model_name || 'unknown'}</code></span>
                  <span>provider: <code>{call.provider || 'n/a'}</code></span>
                  <span>mode: <code>{call.gateway_mode || 'n/a'}</code></span>
                  <span>latency: <code>{call.latency_ms ?? 0} ms</code></span>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label style={{ display: 'grid', gap: 6 }}>
      <span style={{ fontSize: 12, fontWeight: 500, color: 'var(--text-secondary)' }}>{label}</span>
      {children}
    </label>
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

const primaryButtonStyle = {
  border: 'none',
  borderRadius: 10,
  background: 'var(--accent-primary)',
  color: 'white',
  fontSize: 13,
  fontWeight: 600,
  padding: '10px 14px',
  cursor: 'pointer',
} as const

const secondaryButtonStyle = {
  border: '0.5px solid var(--border)',
  borderRadius: 8,
  background: 'var(--bg-primary)',
  color: 'var(--text-primary)',
  fontSize: 12,
  fontWeight: 600,
  padding: '8px 10px',
  cursor: 'pointer',
} as const

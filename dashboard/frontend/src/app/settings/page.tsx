'use client'
import { useEffect, useState } from 'react'
import { fetchConfig, fetchProductConfig, fetchProductDoctor, fetchProductLogs, fetchProductStack, rotateProductToken, saveProductConfig } from '@/lib/api'

type ProductConfig = {
  project_name: string
  db_path: string
  output_dir: string
  gateway: { host: string; port: number; upstream_provider: string }
  dashboard_backend: { host: string; port: number }
  dashboard_frontend: { port: number }
  defaults: { gateway_model: string; gateway_api_key: string; confidence_threshold: number }
}

type DoctorCheck = {
  name: string
  ok: boolean
  detail: string
  remedy?: string
  category?: string
  severity?: string
  commands?: string[]
}
type StackAction = { id: string; label: string; command: string; kind: string; risk: string; reason: string }
type StackStatus = { recommended_actions?: StackAction[] }

const inputStyle = {
  width: '100%',
  borderRadius: 10,
  border: '0.5px solid var(--border)',
  background: 'var(--bg-primary)',
  color: 'var(--text-primary)',
  padding: '10px 12px',
  fontSize: 13,
} as const

export default function SettingsPage() {
  const [runtimeConfig, setRuntimeConfig] = useState<any>(null)
  const [productConfig, setProductConfig] = useState<ProductConfig | null>(null)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  const [saveMessage, setSaveMessage] = useState('')
  const [checks, setChecks] = useState<DoctorCheck[]>([])
  const [stack, setStack] = useState<StackStatus | null>(null)
  const [copiedKey, setCopiedKey] = useState('')
  const [selectedService, setSelectedService] = useState<'gateway' | 'backend' | 'frontend'>('gateway')
  const [selectedStream, setSelectedStream] = useState<'stdout' | 'stderr'>('stdout')
  const [logLines, setLogLines] = useState<string[]>([])
  const [logPath, setLogPath] = useState('')
  const [logError, setLogError] = useState('')
  const [logLoading, setLogLoading] = useState(false)
  const [rotatingToken, setRotatingToken] = useState(false)

  useEffect(() => {
    Promise.all([fetchConfig(), fetchProductConfig(), fetchProductDoctor(), fetchProductStack()])
      .then(([runtime, product, doctor, stackState]) => {
        setRuntimeConfig(runtime)
        setProductConfig(product)
        setChecks(doctor.checks || [])
        setStack(stackState)
      })
      .catch(e => setError(e.message))
      .finally(() => setLoading(false))
  }, [])

  useEffect(() => {
    const loadLogs = async () => {
      setLogLoading(true)
      setLogError('')
      try {
        const result = await fetchProductLogs(selectedService, selectedStream, 80)
        setLogLines(result.lines || [])
        setLogPath(result.path || '')
      } catch (e: any) {
        setLogLines([])
        setLogPath('')
        setLogError(e.message || 'Failed to load logs')
      } finally {
        setLogLoading(false)
      }
    }
    loadLogs()
  }, [selectedService, selectedStream])

  const updateField = (path: string[], value: string | number) => {
    setProductConfig(current => {
      if (!current) return current
      const next: any = JSON.parse(JSON.stringify(current))
      let cursor = next
      for (let i = 0; i < path.length - 1; i += 1) cursor = cursor[path[i]]
      cursor[path[path.length - 1]] = value
      return next
    })
  }

  const save = async () => {
    if (!productConfig) return
    setSaving(true)
    setError('')
    setSaveMessage('')
    try {
      const payload = {
        ...productConfig,
        gateway: {
          ...productConfig.gateway,
          port: Number(productConfig.gateway.port),
        },
        dashboard_backend: {
          ...productConfig.dashboard_backend,
          port: Number(productConfig.dashboard_backend.port),
        },
        dashboard_frontend: {
          ...productConfig.dashboard_frontend,
          port: Number(productConfig.dashboard_frontend.port),
        },
        defaults: {
          ...productConfig.defaults,
          confidence_threshold: Number(productConfig.defaults.confidence_threshold),
        },
      }
      const saved = await saveProductConfig(payload)
      setProductConfig(saved)
      setSaveMessage('Saved. Restart the local stack so port and runtime changes take effect everywhere.')
    } catch (e: any) {
      setError(e.message || 'Failed to save settings')
    } finally {
      setSaving(false)
    }
  }

  const copyText = async (key: string, text: string) => {
    try {
      await navigator.clipboard.writeText(text)
      setCopiedKey(key)
      window.setTimeout(() => {
        setCopiedKey(current => (current === key ? '' : current))
      }, 1800)
    } catch {}
  }

  const refreshLogs = async () => {
    setLogLoading(true)
    setLogError('')
    try {
      const result = await fetchProductLogs(selectedService, selectedStream, 80)
      setLogLines(result.lines || [])
      setLogPath(result.path || '')
    } catch (e: any) {
      setLogLines([])
      setLogPath('')
      setLogError(e.message || 'Failed to load logs')
    } finally {
      setLogLoading(false)
    }
  }

  const rotateToken = async () => {
    setRotatingToken(true)
    setError('')
    setSaveMessage('')
    try {
      const result = await rotateProductToken()
      setProductConfig(result.config)
      setSaveMessage('Project token rotated. Restart the stack or gateway so new clients use the updated token.')
    } catch (e: any) {
      setError(e.message || 'Failed to rotate project token')
    } finally {
      setRotatingToken(false)
    }
  }

  if (loading) return <div style={{ color: 'var(--text-tertiary)', padding: 40, textAlign: 'center' }}>Loading settings...</div>
  if (error && !productConfig) return <div className="card" style={{ padding: 24, maxWidth: 900 }}>{error}</div>

  const items = runtimeConfig ? [
    ['Target provider', runtimeConfig.target_agent_provider],
    ['Local model', runtimeConfig.target_agent_ollama_model],
    ['Fallback API model', runtimeConfig.target_agent_openai_model],
    ['Ollama host', runtimeConfig.ollama_host],
    ['Eval samples / cluster', runtimeConfig.eval_samples_per_cluster],
    ['Remote min interval (s)', runtimeConfig.remote_min_interval_s],
    ['Judge min interval (s)', runtimeConfig.judge_min_interval_s],
    ['Confidence threshold', runtimeConfig.confidence_threshold],
    ['Quality threshold', runtimeConfig.quality_threshold],
    ['Configured models', runtimeConfig.model_count],
    ['Database', runtimeConfig.db_path],
    ['Output dir', runtimeConfig.output_dir],
  ] : []
  const failingProviderChecks = checks.filter(check => !check.ok && check.category === 'provider')

  return (
    <div style={{ maxWidth: 980 }}>
      <div className="card" style={{ padding: 24, marginBottom: 16 }}>
        <h1 style={{ fontSize: 22, fontWeight: 500, marginBottom: 8 }}>Settings</h1>
        <p style={{ color: 'var(--text-secondary)', lineHeight: 1.7, marginBottom: 16 }}>
          Edit your local AgentShrink project configuration here. Saving updates the project manifest.
          Restart the stack afterward if you change ports, paths, or gateway defaults.
        </p>
        {error && <div style={{ marginBottom: 12, color: '#A32D2D', fontSize: 13 }}>{error}</div>}
        {saveMessage && <div style={{ marginBottom: 12, color: '#27500A', fontSize: 13 }}>{saveMessage}</div>}
        {productConfig && (
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
            <Field label="Project name">
              <input value={productConfig.project_name} onChange={e => updateField(['project_name'], e.target.value)} style={inputStyle} />
            </Field>
            <Field label="Gateway upstream provider">
              <select value={productConfig.gateway.upstream_provider} onChange={e => updateField(['gateway', 'upstream_provider'], e.target.value)} style={inputStyle}>
                {['mock', 'openai', 'nvidia', 'ollama', 'huggingface'].map(option => (
                  <option key={option} value={option}>{option}</option>
                ))}
              </select>
            </Field>
            <Field label="Database path">
              <input value={productConfig.db_path} onChange={e => updateField(['db_path'], e.target.value)} style={inputStyle} />
            </Field>
            <Field label="Output directory">
              <input value={productConfig.output_dir} onChange={e => updateField(['output_dir'], e.target.value)} style={inputStyle} />
            </Field>
            <Field label="Gateway host">
              <input value={productConfig.gateway.host} onChange={e => updateField(['gateway', 'host'], e.target.value)} style={inputStyle} />
            </Field>
            <Field label="Gateway port">
              <input type="number" value={productConfig.gateway.port} onChange={e => updateField(['gateway', 'port'], Number(e.target.value))} style={inputStyle} />
            </Field>
            <Field label="Backend host">
              <input value={productConfig.dashboard_backend.host} onChange={e => updateField(['dashboard_backend', 'host'], e.target.value)} style={inputStyle} />
            </Field>
            <Field label="Backend port">
              <input type="number" value={productConfig.dashboard_backend.port} onChange={e => updateField(['dashboard_backend', 'port'], Number(e.target.value))} style={inputStyle} />
            </Field>
            <Field label="Frontend port">
              <input type="number" value={productConfig.dashboard_frontend.port} onChange={e => updateField(['dashboard_frontend', 'port'], Number(e.target.value))} style={inputStyle} />
            </Field>
            <Field label="Default gateway model">
              <input value={productConfig.defaults.gateway_model} onChange={e => updateField(['defaults', 'gateway_model'], e.target.value)} style={inputStyle} />
            </Field>
            <div style={{ display: 'grid', gap: 6 }}>
              <span style={{ fontSize: 12, fontWeight: 500, color: 'var(--text-secondary)' }}>Project token</span>
              <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
                <input value={productConfig.defaults.gateway_api_key} onChange={e => updateField(['defaults', 'gateway_api_key'], e.target.value)} style={inputStyle} />
                <button
                  onClick={rotateToken}
                  disabled={rotatingToken}
                  style={{ ...secondaryButtonStyle, whiteSpace: 'nowrap', height: 40, opacity: rotatingToken ? 0.7 : 1 }}
                >
                  {rotatingToken ? 'Rotating...' : 'Rotate'}
                </button>
              </div>
              <div style={{ fontSize: 11, color: 'var(--text-tertiary)' }}>
                This token is used as the Bearer credential for clients talking to the AgentShrink gateway.
              </div>
            </div>
            <Field label="Confidence threshold">
              <input type="number" step="0.01" value={productConfig.defaults.confidence_threshold} onChange={e => updateField(['defaults', 'confidence_threshold'], Number(e.target.value))} style={inputStyle} />
            </Field>
          </div>
        )}
        <div style={{ display: 'flex', justifyContent: 'flex-end', marginTop: 16 }}>
          <button
            onClick={save}
            disabled={saving || !productConfig}
            style={{
              border: 'none',
              borderRadius: 10,
              background: 'var(--accent-primary)',
              color: 'white',
              fontSize: 13,
              fontWeight: 600,
              padding: '10px 14px',
              cursor: 'pointer',
              opacity: saving ? 0.7 : 1,
            }}
          >
            {saving ? 'Saving...' : 'Save Project Settings'}
          </button>
        </div>
      </div>

      <div className="card" style={{ padding: 24, marginBottom: 16 }}>
        <div style={{ fontSize: 12, fontWeight: 500, color: 'var(--text-secondary)', marginBottom: 12 }}>Provider setup guidance</div>
        {productConfig && (
          <div style={{ fontSize: 13, color: 'var(--text-secondary)', lineHeight: 1.8, marginBottom: 12 }}>
            Selected upstream provider: <code>{productConfig.gateway.upstream_provider}</code>
          </div>
        )}
        {failingProviderChecks.length === 0 ? (
          <div style={{ fontSize: 13, color: '#1D9E75' }}>No provider setup blockers are currently reported.</div>
        ) : (
          <div style={{ display: 'grid', gap: 10 }}>
            {failingProviderChecks.map((check) => (
              <div key={check.name} style={{ background: '#FFF2EE', borderRadius: 10, padding: '12px 14px' }}>
                <div style={{ fontSize: 12, fontWeight: 600, color: '#A32D2D', marginBottom: 4 }}>{check.name}</div>
                <div style={{ fontSize: 12, color: 'var(--text-secondary)', marginBottom: check.remedy ? 6 : 0 }}>{check.detail}</div>
                {check.remedy && <div style={{ fontSize: 12, color: '#7A4428' }}>Next step: {check.remedy}</div>}
                {!!check.commands?.length && (
                  <>
                    <pre style={{
                      margin: '10px 0 0',
                      padding: '10px 12px',
                      borderRadius: 8,
                      background: '#171714',
                      color: '#F7F4ED',
                      fontSize: 12,
                      lineHeight: 1.55,
                      whiteSpace: 'pre-wrap',
                    }}>
                      {check.commands.join('\n')}
                    </pre>
                    <div style={{ display: 'flex', justifyContent: 'flex-end', marginTop: 8 }}>
                      <button onClick={() => copyText(`provider-${check.name}`, check.commands!.join('\n'))} style={secondaryButtonStyle}>
                        {copiedKey === `provider-${check.name}` ? 'Copied recovery commands' : 'Copy recovery commands'}
                      </button>
                    </div>
                  </>
                )}
              </div>
            ))}
          </div>
        )}
      </div>

      <div className="card" style={{ padding: 24, marginBottom: 16 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 12, marginBottom: 12, flexWrap: 'wrap' }}>
          <div>
            <div style={{ fontSize: 12, fontWeight: 500, color: 'var(--text-secondary)', marginBottom: 6 }}>Stack controls</div>
            <div style={{ fontSize: 13, color: 'var(--text-secondary)', lineHeight: 1.7 }}>
              AgentShrink uses a reliable foreground supervisor on Windows. Use these commands from a terminal when you want to start or stop the full stack.
            </div>
          </div>
          <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
            <button onClick={() => copyText('up', 'agentshrink stack up')} style={secondaryButtonStyle}>
              {copiedKey === 'up' ? 'Copied stack up' : 'Copy stack up'}
            </button>
            <button onClick={() => copyText('down', 'agentshrink stack down')} style={secondaryButtonStyle}>
              {copiedKey === 'down' ? 'Copied stack down' : 'Copy stack down'}
            </button>
            <button onClick={() => copyText('status', 'agentshrink stack status')} style={secondaryButtonStyle}>
              {copiedKey === 'status' ? 'Copied stack status' : 'Copy stack status'}
            </button>
          </div>
        </div>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 10 }}>
          <CommandBlock label="Start" command="agentshrink stack up" />
          <CommandBlock label="Status" command="agentshrink stack status" />
          <CommandBlock label="Stop" command="agentshrink stack down" />
        </div>
        {!!stack?.recommended_actions?.length && (
          <div style={{ display: 'grid', gap: 10, marginTop: 14 }}>
            {stack.recommended_actions.map((action) => (
              <div key={action.id} style={{ background: 'var(--bg-secondary)', borderRadius: 10, padding: '12px 14px' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', gap: 10, alignItems: 'center', marginBottom: 6, flexWrap: 'wrap' }}>
                  <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--text-primary)' }}>{action.label}</div>
                  <span className="badge" style={{
                    background: action.risk === 'caution' ? '#FAEEDA' : '#EAF3DE',
                    color: action.risk === 'caution' ? '#633806' : '#27500A',
                  }}>
                    {action.risk === 'caution' ? 'Caution' : 'Safe'}
                  </span>
                </div>
                <div style={{ fontSize: 12, color: 'var(--text-secondary)', lineHeight: 1.6, marginBottom: 8 }}>
                  {action.reason}
                </div>
                <CommandBlock label="Recommended command" command={action.command} />
                <div style={{ display: 'flex', justifyContent: 'flex-end', marginTop: 8 }}>
                  <button onClick={() => copyText(`action-${action.id}`, action.command)} style={secondaryButtonStyle}>
                    {copiedKey === `action-${action.id}` ? 'Copied action' : 'Copy action'}
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      <div className="card" style={{ padding: 24, marginBottom: 16 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 12, marginBottom: 12, flexWrap: 'wrap' }}>
          <div>
            <div style={{ fontSize: 12, fontWeight: 500, color: 'var(--text-secondary)', marginBottom: 6 }}>Recent service logs</div>
            <div style={{ fontSize: 13, color: 'var(--text-secondary)' }}>
              Inspect the latest gateway, backend, or frontend logs without leaving the app.
            </div>
          </div>
          <button onClick={refreshLogs} disabled={logLoading} style={secondaryButtonStyle}>
            {logLoading ? 'Refreshing...' : 'Refresh logs'}
          </button>
        </div>
        <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap', marginBottom: 12 }}>
          <select value={selectedService} onChange={e => setSelectedService(e.target.value as any)} style={{ ...inputStyle, maxWidth: 180 }}>
            <option value="gateway">gateway</option>
            <option value="backend">backend</option>
            <option value="frontend">frontend</option>
          </select>
          <select value={selectedStream} onChange={e => setSelectedStream(e.target.value as any)} style={{ ...inputStyle, maxWidth: 180 }}>
            <option value="stdout">stdout</option>
            <option value="stderr">stderr</option>
          </select>
        </div>
        {logPath && (
          <div style={{ fontSize: 12, color: 'var(--text-tertiary)', marginBottom: 10, wordBreak: 'break-all' }}>
            {logPath}
          </div>
        )}
        {logError ? (
          <div style={{ color: '#A32D2D', fontSize: 13 }}>{logError}</div>
        ) : (
          <pre style={{
            margin: 0,
            padding: '14px 16px',
            borderRadius: 10,
            background: '#171714',
            color: '#F7F4ED',
            fontSize: 12,
            lineHeight: 1.55,
            whiteSpace: 'pre-wrap',
            minHeight: 220,
            maxHeight: 360,
            overflowY: 'auto',
          }}>
            {logLines.length ? logLines.join('\n') : (logLoading ? 'Loading logs...' : 'No log lines available yet.')}
          </pre>
        )}
      </div>

      <div className="card" style={{ padding: 24, marginBottom: 16 }}>
        <div style={{ fontSize: 12, fontWeight: 500, color: 'var(--text-secondary)', marginBottom: 12 }}>Current runtime view</div>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
          {items.map(([label, value]) => (
            <div key={String(label)} style={{ background: 'var(--bg-secondary)', borderRadius: 8, padding: '12px 14px' }}>
              <div style={{ fontSize: 11, color: 'var(--text-tertiary)', textTransform: 'uppercase', marginBottom: 4 }}>{label}</div>
              <div style={{ fontSize: 13, color: 'var(--text-primary)', wordBreak: 'break-word' }}>{value}</div>
            </div>
          ))}
        </div>
      </div>

      {runtimeConfig && (
        <div className="card" style={{ padding: 24 }}>
          <div style={{ fontSize: 12, fontWeight: 500, color: 'var(--text-secondary)', marginBottom: 12 }}>Current readiness</div>
          <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
            <span className="badge" style={{ background: runtimeConfig.analysis_exists ? '#EAF3DE' : '#FCEBEB', color: runtimeConfig.analysis_exists ? '#27500A' : '#A32D2D' }}>
              Analysis {runtimeConfig.analysis_exists ? 'available' : 'missing'}
            </span>
            <span className="badge" style={{ background: runtimeConfig.heuristic_report ? '#FAEEDA' : '#EEEDFE', color: runtimeConfig.heuristic_report ? '#633806' : '#3C3489' }}>
              {runtimeConfig.heuristic_report ? 'Heuristic report active' : 'Saved report available'}
            </span>
            <span className="badge" style={{ background: '#EEEDFE', color: '#3C3489' }}>
              {runtimeConfig.cluster_count} clusters loaded
            </span>
          </div>
        </div>
      )}
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

function CommandBlock({ label, command }: { label: string; command: string }) {
  return (
    <div style={{ background: 'var(--bg-secondary)', borderRadius: 10, padding: '12px 14px' }}>
      <div style={{ fontSize: 11, color: 'var(--text-tertiary)', textTransform: 'uppercase', marginBottom: 6 }}>{label}</div>
      <code style={{ fontSize: 12, color: 'var(--text-primary)', wordBreak: 'break-word' }}>{command}</code>
    </div>
  )
}

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

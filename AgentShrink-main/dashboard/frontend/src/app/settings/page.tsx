'use client'
import { useEffect, useState } from 'react'
import { deleteProductProvider, fetchConfig, fetchHostedConfig, fetchProductConfig, fetchProductDoctor, fetchProductLogs, fetchProductProviderModels, fetchProductProviderPresets, fetchProductProviders, fetchProductStack, rotateProductToken, saveHostedConfig, saveProductConfig, saveProductProvider, testProductProvider } from '@/lib/api'

type ProductConfig = {
  account?: { id?: string; name?: string; slug?: string }
  project?: { id?: string; name?: string; slug?: string; environment?: string }
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
type HostedConfig = {
  deployment?: { mode?: string; public_app_url?: string; public_api_url?: string; gateway_url?: string }
  auth?: { mode?: string; provider?: string; allow_self_signup?: boolean; auth0?: { domain?: string; client_id?: string; client_secret?: string; audience?: string; redirect_path?: string } }
  billing?: { provider?: string; plan?: string; currency?: string; seat_price_usd?: number; usage_price_per_1k_calls_usd?: number; stripe?: { secret_key?: string; price_id?: string; success_path?: string; cancel_path?: string } }
  tenancy?: { isolation_mode?: string; project_token_scope?: string }
}

type ProviderConfig = {
  id: string
  name: string
  adapter: string
  builtin?: boolean
  enabled?: boolean
  description?: string
  default_model?: string
  base_url?: string
  api_key?: string
  api_key_env?: string
  base_url_env?: string
  extra_headers?: Record<string, string>
}

type ProviderPreset = ProviderConfig

const inputStyle = {
  width: '100%',
  borderRadius: 12,
  border: 'none',
  background: '#E0E5EC',
  color: '#3D4852',
  padding: '10px 14px',
  fontSize: 13,
  boxShadow: 'inset 3px 3px 6px rgb(163,177,198,0.6), inset -3px -3px 6px rgba(255,255,255,0.5)',
} as const

export default function SettingsPage() {
  const [runtimeConfig, setRuntimeConfig] = useState<any>(null)
  const [productConfig, setProductConfig] = useState<ProductConfig | null>(null)
  const [hostedConfig, setHostedConfig] = useState<HostedConfig | null>(null)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [savingHosted, setSavingHosted] = useState(false)
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
  const [providers, setProviders] = useState<ProviderConfig[]>([])
  const [providerPresets, setProviderPresets] = useState<ProviderPreset[]>([])
  const [savingProvider, setSavingProvider] = useState(false)
  const [deletingProviderId, setDeletingProviderId] = useState('')
  const [testingProviderId, setTestingProviderId] = useState('')
  const [discoveringProviderId, setDiscoveringProviderId] = useState('')
  const [providerTestResults, setProviderTestResults] = useState<Record<string, { ok: boolean; message: string; checked_via?: string }>>({})
  const [providerModelResults, setProviderModelResults] = useState<Record<string, { models: string[]; detail?: string; source?: string }>>({})
  const [providerExtraHeadersText, setProviderExtraHeadersText] = useState('{}')
  const [showBuiltInProviders, setShowBuiltInProviders] = useState(false)
  const [showProviderDraft, setShowProviderDraft] = useState(false)
  const [showProviderAdvanced, setShowProviderAdvanced] = useState(false)
  const [showHostedConfig, setShowHostedConfig] = useState(false)
  const [providerDraft, setProviderDraft] = useState<ProviderConfig>({
    id: '',
    name: '',
    adapter: 'openai_compatible',
    description: '',
    default_model: '',
    base_url: '',
    api_key: '',
    api_key_env: '',
    base_url_env: '',
    enabled: true,
    extra_headers: {},
  })

  useEffect(() => {
    Promise.all([fetchConfig(), fetchProductConfig(), fetchHostedConfig(), fetchProductDoctor(), fetchProductStack(), fetchProductProviders(), fetchProductProviderPresets()])
      .then(([runtime, product, hosted, doctor, stackState, providerRegistry, presetRegistry]) => {
        setRuntimeConfig(runtime)
        setProductConfig(product)
        setHostedConfig(hosted)
        setChecks(doctor.checks || [])
        setStack(stackState)
        setProviders(providerRegistry.providers || [])
        setProviderPresets(presetRegistry.presets || providerRegistry.presets || [])
        // Auto-test the active upstream provider on page load
        const upstream = product?.gateway?.upstream_provider
        if (upstream) {
          testProductProvider(upstream)
            .then(result => setProviderTestResults(current => ({ ...current, [upstream]: result })))
            .catch(e => setProviderTestResults(current => ({ ...current, [upstream]: { ok: false, message: e.message || 'Failed to test provider connection' } })))
        }
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

  const updateHostedField = (path: string[], value: string | number | boolean) => {
    setHostedConfig(current => {
      if (!current) return current
      const next: any = JSON.parse(JSON.stringify(current))
      let cursor = next
      for (let i = 0; i < path.length - 1; i += 1) {
        cursor[path[i]] = cursor[path[i]] || {}
        cursor = cursor[path[i]]
      }
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

  const saveHosted = async () => {
    if (!hostedConfig) return
    setSavingHosted(true)
    setError('')
    setSaveMessage('')
    try {
      const saved = await saveHostedConfig(hostedConfig)
      setHostedConfig(saved)
      setSaveMessage('Hosted/public config saved. Auth and billing provider changes may require restarting the stack and setting matching env vars where needed.')
    } catch (e: any) {
      setError(e.message || 'Failed to save hosted config')
    } finally {
      setSavingHosted(false)
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

  const saveProvider = async () => {
    if (!providerDraft.id.trim()) {
      setError('Provider id is required')
      return
    }
    if (!providerDraft.name.trim()) {
      setError('Provider name is required')
      return
    }
    setSavingProvider(true)
    setError('')
    setSaveMessage('')
    try {
      let extraHeaders: Record<string, string> = {}
      try {
        const parsed = JSON.parse(providerExtraHeadersText || '{}')
        extraHeaders = Object.fromEntries(
          Object.entries(parsed || {}).map(([key, value]) => [String(key), String(value)])
        )
      } catch {
        throw new Error('Advanced adapter config must be valid JSON.')
      }
      const result = await saveProductProvider({
        ...providerDraft,
        id: providerDraft.id.trim().toLowerCase(),
        name: providerDraft.name.trim(),
        description: providerDraft.description?.trim() || '',
        default_model: providerDraft.default_model?.trim() || '',
        base_url: providerDraft.base_url?.trim() || '',
        api_key: providerDraft.api_key?.trim() || '',
        api_key_env: providerDraft.api_key_env?.trim() || '',
        base_url_env: providerDraft.base_url_env?.trim() || '',
        extra_headers: extraHeaders,
      })
      setProviders(result.providers || [])
      setProviderPresets(result.presets || providerPresets)
      setProviderDraft({
        id: '',
        name: '',
        adapter: 'openai_compatible',
        description: '',
        default_model: '',
        base_url: '',
        api_key: '',
        api_key_env: '',
        base_url_env: '',
        enabled: true,
        extra_headers: {},
      })
      setProviderExtraHeadersText('{}')
      setSaveMessage('Provider registry updated. You can now select this provider as the gateway upstream.')
    } catch (e: any) {
      setError(e.message || 'Failed to save provider config')
    } finally {
      setSavingProvider(false)
    }
  }

  const removeProvider = async (providerId: string) => {
    setDeletingProviderId(providerId)
    setError('')
    setSaveMessage('')
    try {
      const result = await deleteProductProvider(providerId)
      setProviders(result.providers || [])
      if (productConfig?.gateway.upstream_provider === providerId) {
        setSaveMessage('Provider deleted. Pick a new gateway upstream before saving project settings.')
      } else {
        setSaveMessage('Provider deleted from the registry.')
      }
    } catch (e: any) {
      setError(e.message || 'Failed to delete provider config')
    } finally {
      setDeletingProviderId('')
    }
  }

  const applyPreset = (preset: ProviderPreset) => {
    setProviderDraft({
      id: preset.id,
      name: preset.name,
      adapter: preset.adapter,
      description: preset.description || '',
      default_model: preset.default_model || '',
      base_url: preset.base_url || '',
      api_key: '',
      api_key_env: preset.api_key_env || '',
      base_url_env: preset.base_url_env || '',
      enabled: true,
      extra_headers: preset.extra_headers || {},
    })
    setProviderExtraHeadersText(JSON.stringify(preset.extra_headers || {}, null, 2))
    setSaveMessage(`Loaded the ${preset.name} preset into the provider draft. Add your BYOK secret and save if you want an editable copy.`)
  }

  const runProviderTest = async (providerId: string) => {
    setTestingProviderId(providerId)
    setError('')
    try {
      const result = await testProductProvider(providerId)
      setProviderTestResults(current => ({ ...current, [providerId]: result }))
    } catch (e: any) {
      setProviderTestResults(current => ({ ...current, [providerId]: { ok: false, message: e.message || 'Failed to test provider connection' } }))
    } finally {
      setTestingProviderId('')
    }
  }

  const loadProviderModels = async (providerId: string) => {
    setDiscoveringProviderId(providerId)
    setError('')
    try {
      const result = await fetchProductProviderModels(providerId)
      setProviderModelResults(current => ({ ...current, [providerId]: result }))
    } catch (e: any) {
      setProviderModelResults(current => ({ ...current, [providerId]: { models: [], detail: e.message || 'Failed to discover provider models' } }))
    } finally {
      setDiscoveringProviderId('')
    }
  }

  const editProvider = (provider: ProviderConfig) => {
    setProviderDraft({
      id: provider.id,
      name: provider.name,
      adapter: provider.adapter,
      description: provider.description || '',
      default_model: provider.default_model || '',
      base_url: provider.base_url || '',
      api_key: provider.api_key || '',
      api_key_env: provider.api_key_env || '',
      base_url_env: provider.base_url_env || '',
      enabled: provider.enabled !== false,
      extra_headers: provider.extra_headers || {},
    })
    setProviderExtraHeadersText(JSON.stringify(provider.extra_headers || {}, null, 2))
    setShowProviderDraft(true)
    setShowProviderAdvanced(Boolean(provider.extra_headers && Object.keys(provider.extra_headers).length))
    setSaveMessage(`Loaded ${provider.name} into the edit form.`)
  }

  if (loading) return <div style={{ color: 'var(--text-tertiary)', padding: 40, textAlign: 'center' }}>Loading settings...</div>
  if (error && !productConfig) return <div className="card" style={{ padding: 24, maxWidth: 900 }}>{error}</div>

  const items = runtimeConfig ? [
    ['Active provider', runtimeConfig.target_agent_provider_name || runtimeConfig.target_agent_provider],
    ['Active gateway model', runtimeConfig.active_gateway_model || runtimeConfig.target_agent_openai_model],
    ['Local model', runtimeConfig.target_agent_ollama_model],
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
  const enabledProviders = providers.filter(provider => provider.enabled !== false)
  const customProviders = providers.filter(provider => !provider.builtin)
  const builtinProviders = providers.filter(provider => provider.builtin)
  const activeProvider = providers.find(provider => provider.id === productConfig?.gateway.upstream_provider) || null
  const activeProviderTest = activeProvider ? providerTestResults[activeProvider.id] : undefined
  const activeProviderFailing = activeProviderTest && !activeProviderTest.ok
  const activeProviderMissingCred = activeProvider && !activeProvider.builtin && !activeProvider.api_key && !activeProvider.api_key_env

  return (
    <div style={{ maxWidth: 980 }}>
      {(activeProviderFailing || activeProviderMissingCred || failingProviderChecks.length > 0) && (
        <div style={{
          background: '#FFF2EE',
          border: '1px solid #F5C6B8',
          borderRadius: 12,
          padding: '14px 18px',
          marginBottom: 16,
          display: 'flex',
          alignItems: 'flex-start',
          gap: 12,
        }}>
          <span style={{ fontSize: 18, lineHeight: 1 }}>&#9888;</span>
          <div>
            <div style={{ fontSize: 13, fontWeight: 600, color: '#A32D2D', marginBottom: 4 }}>
              Provider setup needs attention
            </div>
            {activeProviderFailing && (
              <div style={{ fontSize: 12, color: '#7A4428', marginBottom: 4 }}>
                Active provider <code>{activeProvider!.name}</code> failed connection test: {activeProviderTest!.message}
              </div>
            )}
            {activeProviderMissingCred && !activeProviderFailing && (
              <div style={{ fontSize: 12, color: '#7A4428', marginBottom: 4 }}>
                Active provider <code>{activeProvider!.name}</code> has no API key or env var configured. Add credentials in the Provider Registry below, then click Test.
              </div>
            )}
            {failingProviderChecks.length > 0 && (
              <div style={{ fontSize: 12, color: '#7A4428' }}>
                {failingProviderChecks.length} provider check{failingProviderChecks.length > 1 ? 's' : ''} failing. See Provider Setup Guidance below.
              </div>
            )}
          </div>
        </div>
      )}
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
            <Field label="Account name">
              <input value={productConfig.account?.name || ''} onChange={e => updateField(['account', 'name'], e.target.value)} style={inputStyle} />
            </Field>
            <Field label="Account slug">
              <input value={productConfig.account?.slug || ''} onChange={e => updateField(['account', 'slug'], e.target.value)} style={inputStyle} />
            </Field>
            <Field label="Project name">
              <input value={productConfig.project_name} onChange={e => updateField(['project_name'], e.target.value)} style={inputStyle} />
            </Field>
            <Field label="Project slug">
              <input value={productConfig.project?.slug || ''} onChange={e => updateField(['project', 'slug'], e.target.value)} style={inputStyle} />
            </Field>
            <Field label="Project environment">
              <input value={productConfig.project?.environment || 'local'} onChange={e => updateField(['project', 'environment'], e.target.value)} style={inputStyle} />
            </Field>
            <Field label="Gateway upstream provider">
              <select value={productConfig.gateway.upstream_provider} onChange={e => updateField(['gateway', 'upstream_provider'], e.target.value)} style={inputStyle}>
                {enabledProviders.map(option => (
                  <option key={option.id} value={option.id}>{option.name} ({option.id})</option>
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
        <div style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          gap: 12,
          marginTop: 16,
          paddingTop: 12,
          borderTop: 'none',
          flexWrap: 'wrap',
        }}>
          <div style={{ fontSize: 12, color: '#6B7280' }}>
            Save these changes to update the active local project.
          </div>
          <button
            onClick={save}
            disabled={saving || !productConfig}
            style={{
              border: 'none',
              borderRadius: 12,
              background: '#6C63FF',
              color: 'white',
              fontSize: 13,
              fontWeight: 600,
              padding: '12px 16px',
              cursor: 'pointer',
              opacity: saving ? 0.7 : 1,
              boxShadow: '5px 5px 10px rgb(163,177,198,0.6), -5px -5px 10px rgba(255,255,255,0.5)',
            }}
          >
            {saving ? 'Saving...' : 'Save Project Settings'}
          </button>
        </div>
      </div>

      <div className="card" style={{ padding: 24, marginBottom: 16 }}>
        <h2 style={{ fontSize: 18, fontWeight: 500, marginBottom: 8 }}>Provider Registry and BYOK</h2>
        <p style={{ color: 'var(--text-secondary)', lineHeight: 1.7, marginBottom: 16 }}>
          This is the provider-agnostic gateway layer. Built-in adapters stay available, and you can add your own
          adapters, presets, and BYOK credentials here. Test the saved connection and discover models before switching your gateway upstream.
        </p>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: 10, marginBottom: 16 }}>
          <CompactStat label="Active upstream" value={activeProvider?.name || productConfig?.gateway.upstream_provider || '-'} />
          <CompactStat label="Custom providers" value={String(customProviders.length)} />
          <CompactStat label="Built-ins" value={String(builtinProviders.length)} />
        </div>
        {!!providerPresets.length && (
          <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginBottom: 14 }}>
            {providerPresets.map((preset) => (
              <button key={preset.id} onClick={() => applyPreset(preset)} style={secondaryButtonStyle}>
                Use preset: {preset.name}
              </button>
            ))}
          </div>
        )}
        <div style={{ display: 'grid', gap: 12, marginBottom: 18 }}>
          {(showBuiltInProviders ? providers : [...customProviders, ...(activeProvider?.builtin ? [activeProvider] : [])]
            .filter((provider, index, list) => list.findIndex(item => item.id === provider.id) === index)
          ).map((provider) => (
            <div key={provider.id} style={{ background: 'var(--bg-secondary)', borderRadius: 12, padding: 16 }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12, alignItems: 'center', flexWrap: 'wrap', marginBottom: 8 }}>
                <div>
                  <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--text-primary)' }}>{provider.name}</div>
                  <div style={{ fontSize: 12, color: 'var(--text-tertiary)' }}>
                    <code>{provider.id}</code> · <code>{provider.adapter}</code> · {provider.builtin ? 'built-in' : 'custom'}
                  </div>
                </div>
                <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
                  {!provider.builtin && (
                    <button onClick={() => editProvider(provider)} style={secondaryButtonStyle}>
                      Edit
                    </button>
                  )}
                  <button onClick={() => runProviderTest(provider.id)} disabled={testingProviderId === provider.id} style={secondaryButtonStyle}>
                    {testingProviderId === provider.id ? 'Testing...' : 'Test'}
                  </button>
                  <button onClick={() => loadProviderModels(provider.id)} disabled={discoveringProviderId === provider.id} style={secondaryButtonStyle}>
                    {discoveringProviderId === provider.id ? 'Loading...' : 'Models'}
                  </button>
                  {!provider.builtin && (
                    <button
                      onClick={() => removeProvider(provider.id)}
                      disabled={deletingProviderId === provider.id}
                      style={{ ...secondaryButtonStyle, opacity: deletingProviderId === provider.id ? 0.7 : 1 }}
                    >
                      {deletingProviderId === provider.id ? 'Deleting...' : 'Delete'}
                    </button>
                  )}
                </div>
              </div>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8, fontSize: 12, color: 'var(--text-secondary)' }}>
                <div>Default model: <code>{provider.default_model || '-'}</code></div>
                <div>{provider.enabled === false ? 'Disabled' : 'Enabled'}{provider.id === productConfig?.gateway.upstream_provider ? ' · active' : ''}</div>
                <div style={{ wordBreak: 'break-all' }}>Base URL: <code>{provider.base_url || provider.base_url_env || '-'}</code></div>
                <div>Credential: <code>{provider.api_key ? 'saved in config' : (provider.api_key_env || '-')}</code></div>
              </div>
              {!!provider.description && (
                <div style={{ marginTop: 8, fontSize: 12, color: 'var(--text-tertiary)', lineHeight: 1.6 }}>
                  {provider.description}
                </div>
              )}
              {!!providerTestResults[provider.id] && (
                <div style={{ marginTop: 10, fontSize: 12, color: providerTestResults[provider.id].ok ? '#27500A' : '#A32D2D' }}>
                  {providerTestResults[provider.id].ok ? 'Connection OK' : 'Connection failed'}: {providerTestResults[provider.id].message}
                  {providerTestResults[provider.id].checked_via ? ` (${providerTestResults[provider.id].checked_via})` : ''}
                </div>
              )}
              {!!providerModelResults[provider.id] && (
                <div style={{ marginTop: 10, display: 'grid', gap: 6 }}>
                  <div style={{ fontSize: 12, color: 'var(--text-secondary)' }}>
                    {providerModelResults[provider.id].detail || 'Model discovery completed.'}
                  </div>
                  <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
                    {(providerModelResults[provider.id].models || []).map((modelName) => (
                      <span key={modelName} className="badge" style={{ background: '#EEEDFE', color: '#3C3489' }}>{modelName}</span>
                    ))}
                  </div>
                </div>
              )}
            </div>
          ))}
        </div>
        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginBottom: 14 }}>
          <button onClick={() => setShowBuiltInProviders(current => !current)} style={secondaryButtonStyle}>
            {showBuiltInProviders ? `Hide built-ins (${builtinProviders.length})` : `Show built-ins (${builtinProviders.length})`}
          </button>
          <button onClick={() => setShowProviderDraft(current => !current)} style={secondaryButtonStyle}>
            {showProviderDraft ? 'Hide add-provider form' : 'Add provider'}
          </button>
        </div>
        {showProviderDraft && (
          <>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
          <Field label="Provider id">
            <input value={providerDraft.id} onChange={e => setProviderDraft(current => ({ ...current, id: e.target.value }))} style={inputStyle} placeholder="sarvam-openai" />
          </Field>
          <Field label="Display name">
            <input value={providerDraft.name} onChange={e => setProviderDraft(current => ({ ...current, name: e.target.value }))} style={inputStyle} placeholder="Sarvam AI" />
          </Field>
            <Field label="Adapter">
              <select value={providerDraft.adapter} onChange={e => setProviderDraft(current => ({ ...current, adapter: e.target.value }))} style={inputStyle}>
                <option value="openai_compatible">openai_compatible</option>
                <option value="anthropic_native">anthropic_native</option>
                <option value="azure_openai">azure_openai</option>
                <option value="custom_http">custom_http</option>
                <option value="gemini_native">gemini_native</option>
                <option value="huggingface_chat">huggingface_chat</option>
                <option value="mock">mock</option>
              </select>
            </Field>
          <Field label="Default model">
            <input value={providerDraft.default_model} onChange={e => setProviderDraft(current => ({ ...current, default_model: e.target.value }))} style={inputStyle} placeholder="model-name" />
          </Field>
          <Field label="Base URL">
            <input value={providerDraft.base_url} onChange={e => setProviderDraft(current => ({ ...current, base_url: e.target.value }))} style={inputStyle} placeholder="https://provider.example/v1" />
          </Field>
          <Field label="API key">
            <input value={providerDraft.api_key} onChange={e => setProviderDraft(current => ({ ...current, api_key: e.target.value }))} style={inputStyle} placeholder="paste the real provider key here" />
          </Field>
          <Field label="API key env var name">
            <input value={providerDraft.api_key_env} onChange={e => setProviderDraft(current => ({ ...current, api_key_env: e.target.value }))} style={inputStyle} placeholder="SARVAM_API_KEY" />
          </Field>
          <Field label="Base URL env var name">
            <input value={providerDraft.base_url_env} onChange={e => setProviderDraft(current => ({ ...current, base_url_env: e.target.value }))} style={inputStyle} placeholder="SARVAM_BASE_URL" />
          </Field>
          <div style={{ gridColumn: '1 / -1' }}>
            <Field label="Description">
              <input value={providerDraft.description} onChange={e => setProviderDraft(current => ({ ...current, description: e.target.value }))} style={inputStyle} placeholder="What this provider is for" />
            </Field>
          </div>
        </div>
        <div style={{ marginTop: 12, fontSize: 12, color: 'var(--text-tertiary)', lineHeight: 1.7 }}>
          Put the real secret in <code>API key</code>. Use the env-var fields only for names like <code>SARVAM_API_KEY</code>, not the secret value itself.
        </div>
        <div style={{ marginTop: 8 }}>
          <button onClick={() => setShowProviderAdvanced(current => !current)} style={secondaryButtonStyle}>
            {showProviderAdvanced ? 'Hide advanced adapter config' : 'Show advanced adapter config'}
          </button>
        </div>
        {showProviderAdvanced && (
          <>
            <div style={{ marginTop: 12 }}>
              <Field label="Advanced adapter config / headers (JSON)">
                <textarea
                  value={providerExtraHeadersText}
                  onChange={e => setProviderExtraHeadersText(e.target.value)}
                  style={{ ...inputStyle, minHeight: 120, fontFamily: 'monospace' }}
                  placeholder='{"api_version":"2024-10-21"}'
                />
              </Field>
            </div>
            <div style={{ marginTop: 8, fontSize: 12, color: 'var(--text-tertiary)', lineHeight: 1.7 }}>
              Use the advanced JSON field for adapter-specific settings like <code>{'{"api_version":"2024-10-21"}'}</code> for Azure or <code>{'{"request_mode":"prompt_only","response_text_path":"result.text"}'}</code> for <code>custom_http</code>.
            </div>
          </>
        )}
        <div style={{ display: 'flex', justifyContent: 'flex-end', marginTop: 16 }}>
          <button
            onClick={saveProvider}
            disabled={savingProvider}
            style={{ ...secondaryButtonStyle, background: '#6C63FF', color: 'white', border: 'none', opacity: savingProvider ? 0.7 : 1, boxShadow: '5px 5px 10px rgb(163,177,198,0.6), -5px -5px 10px rgba(255,255,255,0.5)' }}
          >
            {savingProvider ? 'Saving provider...' : 'Save provider'}
          </button>
        </div>
          </>
        )}
      </div>

      <div className="card" style={{ padding: 24, marginBottom: 16 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 12, marginBottom: 8, flexWrap: 'wrap' }}>
          <h2 style={{ fontSize: 18, fontWeight: 500, margin: 0 }}>Hosted/Public Config</h2>
          <button onClick={() => setShowHostedConfig(current => !current)} style={secondaryButtonStyle}>
            {showHostedConfig ? 'Hide hosted config' : 'Show hosted config'}
          </button>
        </div>
        <p style={{ color: 'var(--text-secondary)', lineHeight: 1.7, marginBottom: 16 }}>
          This section is optional for future hosted deployment work. You can ignore it for the normal single-user local product.
        </p>
        {showHostedConfig && hostedConfig && (
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
            <Field label="Deployment mode">
              <select value={hostedConfig.deployment?.mode || 'local-hosted'} onChange={e => updateHostedField(['deployment', 'mode'], e.target.value)} style={inputStyle}>
                {['local-hosted', 'hosted', 'staging'].map(option => <option key={option} value={option}>{option}</option>)}
              </select>
            </Field>
            <Field label="Public app URL">
              <input value={hostedConfig.deployment?.public_app_url || ''} onChange={e => updateHostedField(['deployment', 'public_app_url'], e.target.value)} style={inputStyle} />
            </Field>
            <Field label="Public API URL">
              <input value={hostedConfig.deployment?.public_api_url || ''} onChange={e => updateHostedField(['deployment', 'public_api_url'], e.target.value)} style={inputStyle} />
            </Field>
            <Field label="Public gateway URL">
              <input value={hostedConfig.deployment?.gateway_url || ''} onChange={e => updateHostedField(['deployment', 'gateway_url'], e.target.value)} style={inputStyle} />
            </Field>
            <Field label="Auth mode">
              <select value={hostedConfig.auth?.mode || 'session'} onChange={e => updateHostedField(['auth', 'mode'], e.target.value)} style={inputStyle}>
                {['session', 'external'].map(option => <option key={option} value={option}>{option}</option>)}
              </select>
            </Field>
            <Field label="Auth provider">
              <select value={hostedConfig.auth?.provider || 'local-session'} onChange={e => updateHostedField(['auth', 'provider'], e.target.value)} style={inputStyle}>
                {['local-session', 'auth0'].map(option => <option key={option} value={option}>{option}</option>)}
              </select>
            </Field>
            <Field label="Auth0 domain">
              <input value={hostedConfig.auth?.auth0?.domain || ''} onChange={e => updateHostedField(['auth', 'auth0', 'domain'], e.target.value)} style={inputStyle} />
            </Field>
            <Field label="Auth0 client id">
              <input value={hostedConfig.auth?.auth0?.client_id || ''} onChange={e => updateHostedField(['auth', 'auth0', 'client_id'], e.target.value)} style={inputStyle} />
            </Field>
            <Field label="Auth0 client secret">
              <input value={hostedConfig.auth?.auth0?.client_secret || ''} onChange={e => updateHostedField(['auth', 'auth0', 'client_secret'], e.target.value)} style={inputStyle} />
            </Field>
            <Field label="Auth0 audience">
              <input value={hostedConfig.auth?.auth0?.audience || ''} onChange={e => updateHostedField(['auth', 'auth0', 'audience'], e.target.value)} style={inputStyle} />
            </Field>
            <Field label="Billing provider">
              <select value={hostedConfig.billing?.provider || 'manual'} onChange={e => updateHostedField(['billing', 'provider'], e.target.value)} style={inputStyle}>
                {['manual', 'stripe'].map(option => <option key={option} value={option}>{option}</option>)}
              </select>
            </Field>
            <Field label="Billing plan">
              <input value={hostedConfig.billing?.plan || ''} onChange={e => updateHostedField(['billing', 'plan'], e.target.value)} style={inputStyle} />
            </Field>
            <Field label="Stripe secret key">
              <input value={hostedConfig.billing?.stripe?.secret_key || ''} onChange={e => updateHostedField(['billing', 'stripe', 'secret_key'], e.target.value)} style={inputStyle} />
            </Field>
            <Field label="Stripe price id">
              <input value={hostedConfig.billing?.stripe?.price_id || ''} onChange={e => updateHostedField(['billing', 'stripe', 'price_id'], e.target.value)} style={inputStyle} />
            </Field>
            <Field label="Isolation mode">
              <select value={hostedConfig.tenancy?.isolation_mode || 'team-scoped'} onChange={e => updateHostedField(['tenancy', 'isolation_mode'], e.target.value)} style={inputStyle}>
                {['team-scoped', 'tenant-scoped', 'project-scoped'].map(option => <option key={option} value={option}>{option}</option>)}
              </select>
            </Field>
            <Field label="Project token scope">
              <select value={hostedConfig.tenancy?.project_token_scope || 'project'} onChange={e => updateHostedField(['tenancy', 'project_token_scope'], e.target.value)} style={inputStyle}>
                {['project', 'team', 'tenant'].map(option => <option key={option} value={option}>{option}</option>)}
              </select>
            </Field>
          </div>
        )}
        {showHostedConfig && (
        <div style={{ display: 'flex', justifyContent: 'flex-end', marginTop: 16 }}>
          <button
            onClick={saveHosted}
            disabled={savingHosted || !hostedConfig}
            style={{
              border: 'none',
              borderRadius: 12,
              background: '#6C63FF',
              color: 'white',
              fontSize: 13,
              fontWeight: 600,
              padding: '10px 14px',
              cursor: 'pointer',
              opacity: savingHosted ? 0.7 : 1,
              boxShadow: '5px 5px 10px rgb(163,177,198,0.6), -5px -5px 10px rgba(255,255,255,0.5)',
            }}
          >
            {savingHosted ? 'Saving hosted config...' : 'Save Hosted/Public Config'}
          </button>
        </div>
        )}
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
                      padding: '12px 14px',
                      borderRadius: 12,
                      background: '#E0E5EC',
                      color: '#3D4852',
                      fontSize: 12,
                      lineHeight: 1.55,
                      whiteSpace: 'pre-wrap',
                      boxShadow: 'inset 4px 4px 8px rgb(163,177,198,0.6), inset -4px -4px 8px rgba(255,255,255,0.5)',
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
            padding: '16px 18px',
            borderRadius: 16,
            background: '#E0E5EC',
            color: '#3D4852',
            fontSize: 12,
            lineHeight: 1.55,
            whiteSpace: 'pre-wrap',
            minHeight: 220,
            maxHeight: 360,
            overflowY: 'auto',
            boxShadow: 'inset 6px 6px 12px rgb(163,177,198,0.6), inset -6px -6px 12px rgba(255,255,255,0.5)',
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

function CompactStat({ label, value }: { label: string; value: string }) {
  return (
    <div style={{ background: 'var(--bg-secondary)', borderRadius: 10, padding: '12px 14px' }}>
      <div style={{ fontSize: 11, color: 'var(--text-tertiary)', textTransform: 'uppercase', marginBottom: 4 }}>{label}</div>
      <div style={{ fontSize: 13, color: 'var(--text-primary)', fontWeight: 500 }}>{value}</div>
    </div>
  )
}

const secondaryButtonStyle = {
  border: 'none',
  borderRadius: 12,
  background: '#E0E5EC',
  color: '#3D4852',
  fontSize: 12,
  fontWeight: 600,
  padding: '8px 14px',
  cursor: 'pointer',
  boxShadow: '5px 5px 10px rgb(163,177,198,0.6), -5px -5px 10px rgba(255,255,255,0.5)',
} as const

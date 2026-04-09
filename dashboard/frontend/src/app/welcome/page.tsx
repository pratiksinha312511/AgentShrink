'use client'
import { useEffect, useState } from 'react'
import Link from 'next/link'
import { fetchProductConfig, fetchProductDoctor, fetchProductStack, testProductGateway } from '@/lib/api'

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
type StackService = { configured_url: string; process_recorded: boolean; healthy: boolean }
type StackAction = { id: string; label: string; command: string; kind: string; risk: string; reason: string }
type StackStatus = {
  gateway: StackService
  backend: StackService
  frontend: StackService
  all_healthy: boolean
  any_running: boolean
  recommended_actions?: StackAction[]
}
type GatewayTestResult = {
  status: string
  gateway_url: string
  model: string
  message: string
}

function CodeBlock({ text }: { text: string }) {
  return (
    <pre style={{
      margin: 0,
      padding: '14px 16px',
      borderRadius: 10,
      background: '#171714',
      color: '#F7F4ED',
      fontSize: 12,
      overflowX: 'auto',
      lineHeight: 1.55,
      whiteSpace: 'pre-wrap',
    }}>
      {text}
    </pre>
  )
}

export default function WelcomePage() {
  const [config, setConfig] = useState<ProductConfig | null>(null)
  const [checks, setChecks] = useState<DoctorCheck[]>([])
  const [stack, setStack] = useState<StackStatus | null>(null)
  const [copiedKey, setCopiedKey] = useState('')
  const [testingGateway, setTestingGateway] = useState(false)
  const [gatewayTest, setGatewayTest] = useState<GatewayTestResult | null>(null)
  const [gatewayError, setGatewayError] = useState('')

  useEffect(() => {
    fetchProductConfig().then(setConfig).catch(() => {})
    fetchProductDoctor().then((data) => setChecks(data.checks || [])).catch(() => {})
    fetchProductStack().then(setStack).catch(() => {})

    const timer = setInterval(() => {
      fetchProductStack().then(setStack).catch(() => {})
    }, 5000)

    return () => clearInterval(timer)
  }, [])

  const gatewayUrl = config ? `http://${config.gateway.host}:${config.gateway.port}/v1` : 'http://127.0.0.1:8100/v1'
  const sdkSnippet = `from openai import OpenAI\n\nclient = OpenAI(\n    base_url="${gatewayUrl}",\n    api_key="${config?.defaults.gateway_api_key || 'agentshrink-local'}",  # project token\n)`
  const rawSnippet = `import requests\n\nresponse = requests.post(\n    "${gatewayUrl}/chat/completions",\n    headers={"Authorization": "Bearer ${config?.defaults.gateway_api_key || 'agentshrink-local'}"},  # project token\n    json={\n        "model": "${config?.defaults.gateway_model || 'mock-model'}",\n        "messages": [{"role": "user", "content": "hello"}],\n    },\n)`
  const langchainLoggerSnippet = `from agentshrink import AgentShrinkLogger\nfrom langchain_openai import ChatOpenAI\n\nllm = ChatOpenAI(\n    base_url="${gatewayUrl}",\n    api_key="${config?.defaults.gateway_api_key || 'agentshrink-local'}",\n    model="${config?.defaults.gateway_model || 'mock-model'}",\n    callbacks=[AgentShrinkLogger()],\n)`
  const langchainRoutedSnippet = `from agentshrink import ShrinkLLM\n\nllm = ShrinkLLM(\n    output_dir="${config?.output_dir || '.agentshrink_output'}",\n    fallback_provider="openai",\n    fallback_model="gpt-4o-mini",\n    confidence_threshold=${config?.defaults.confidence_threshold ?? 0.75},\n)`
  const stackReady = !!stack?.all_healthy
  const failingChecks = checks.filter(check => !check.ok)
  const providerChecks = checks.filter(check => check.category === 'provider')
  const providerHelp: Record<string, { title: string; lines: string[] }> = {
    mock: {
      title: 'Mock mode guidance',
      lines: [
        'Use mock mode for free local testing before connecting any real provider.',
        'The gateway will echo safe mock responses and still populate routing, cluster, and report flows.',
      ],
    },
    openai: {
      title: 'OpenAI setup guidance',
      lines: [
        'Set OPENAI_API_KEY in your environment before starting the stack.',
        'If you use a custom OpenAI-compatible endpoint, also set OPENAI_BASE_URL.',
      ],
    },
    nvidia: {
      title: 'NVIDIA setup guidance',
      lines: [
        'Set NVIDIA_API_KEY in your environment before starting the stack.',
        'AgentShrink will send OpenAI-compatible requests to the NVIDIA integration endpoint.',
      ],
    },
    huggingface: {
      title: 'Hugging Face setup guidance',
      lines: [
        'Set HF_TOKEN in your environment before starting the stack.',
        'If you select gated models later, your token also needs access approval for those repos.',
      ],
    },
    ollama: {
      title: 'Ollama setup guidance',
      lines: [
        'Start Ollama locally before switching the gateway upstream to ollama.',
        'The default health probe checks the Ollama tags endpoint to confirm local reachability.',
      ],
    },
  }
  const activeProviderHelp = providerHelp[config?.gateway.upstream_provider || 'mock']
  const readinessLabel = stackReady
    ? 'Your local AgentShrink stack is live.'
    : stack?.any_running
      ? 'Some services are up, but the full stack is not healthy yet.'
      : 'Start the stack to begin capturing and routing traffic.'

  const ServiceDot = ({ ok }: { ok: boolean }) => (
    <span style={{
      width: 8,
      height: 8,
      borderRadius: '50%',
      background: ok ? '#1D9E75' : '#D85A30',
      display: 'inline-block',
      flexShrink: 0,
    }} />
  )

  const copyText = async (key: string, text: string) => {
    try {
      await navigator.clipboard.writeText(text)
      setCopiedKey(key)
      window.setTimeout(() => {
        setCopiedKey((current) => (current === key ? '' : current))
      }, 1800)
    } catch {}
  }

  const runGatewayTest = async () => {
    setTestingGateway(true)
    setGatewayError('')
    try {
      const result = await testProductGateway()
      setGatewayTest(result)
    } catch (err: any) {
      setGatewayTest(null)
      setGatewayError(err?.message || 'Gateway test failed')
    } finally {
      setTestingGateway(false)
    }
  }

  const smallButton = {
    border: '0.5px solid var(--border)',
    borderRadius: 8,
    background: 'var(--bg-primary)',
    color: 'var(--text-primary)',
    fontSize: 12,
    fontWeight: 600,
    padding: '8px 10px',
    cursor: 'pointer',
  } as const

  return (
    <div style={{ maxWidth: 980 }}>
      <div className="card" style={{ padding: 28, marginBottom: 20, background: 'linear-gradient(135deg, #F4EFE2 0%, #FBF8F1 100%)' }}>
        <div style={{ fontSize: 11, textTransform: 'uppercase', letterSpacing: '0.08em', color: '#6C675A', marginBottom: 10 }}>
          AgentShrink Onboarding
        </div>
        <h1 style={{ fontSize: 30, lineHeight: 1.1, margin: 0, color: 'var(--text-primary)' }}>
          Connect any AI agent, observe its calls, then shrink the easy steps to cheaper local models.
        </h1>
        <p style={{ marginTop: 14, fontSize: 14, color: 'var(--text-secondary)', lineHeight: 1.7, maxWidth: 760 }}>
          The smoothest path is to point an OpenAI-compatible client or raw HTTP app at the AgentShrink gateway.
          You can test the full flow for free in mock mode before using any real provider.
        </p>
        <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap', marginTop: 16 }}>
          <span className="badge" style={{ background: '#EAF3DE', color: '#27500A' }}>Local-first</span>
          <span className="badge" style={{ background: '#EEEDFE', color: '#3C3489' }}>OpenAI-compatible gateway</span>
          <span className="badge" style={{ background: '#E6F1FB', color: '#0C447C' }}>Free mock mode</span>
        </div>
        <div className="card" style={{ marginTop: 18, padding: 16, background: stackReady ? '#F3FAF6' : '#FBF6EF' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 6 }}>
            <ServiceDot ok={stackReady} />
            <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--text-primary)' }}>
              {readinessLabel}
            </div>
          </div>
          <div style={{ fontSize: 12, color: 'var(--text-secondary)' }}>
            {stackReady
              ? 'You can move straight into Live Routing, then Cluster Map and Report.'
              : 'Run the local stack once, then refresh this page or wait a few seconds for service status to update.'}
          </div>
          <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap', marginTop: 12 }}>
            <Link href="/routing" style={{ textDecoration: 'none' }}>
              <span className="badge" style={{ background: '#E6F1FB', color: '#0C447C', cursor: 'pointer' }}>Open Live Routing</span>
            </Link>
            <Link href="/clusters" style={{ textDecoration: 'none' }}>
              <span className="badge" style={{ background: '#EAF3DE', color: '#27500A', cursor: 'pointer' }}>Open Cluster Map</span>
            </Link>
            <Link href="/report" style={{ textDecoration: 'none' }}>
              <span className="badge" style={{ background: '#FBF2E6', color: '#9A5C00', cursor: 'pointer' }}>Open Report</span>
            </Link>
            <button
              onClick={runGatewayTest}
              disabled={testingGateway || !stack?.gateway.healthy}
              style={{ ...smallButton, opacity: testingGateway || !stack?.gateway.healthy ? 0.6 : 1 }}
            >
              {testingGateway ? 'Testing...' : 'Test My Gateway'}
            </button>
          </div>
          {(gatewayTest || gatewayError) && (
            <div style={{ marginTop: 12, padding: 12, borderRadius: 10, background: gatewayError ? '#FFF2EE' : '#EEF8F3' }}>
              <div style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-primary)', marginBottom: 4 }}>
                {gatewayError ? 'Gateway test failed' : 'Gateway test passed'}
              </div>
              <div style={{ fontSize: 12, color: 'var(--text-secondary)', lineHeight: 1.6 }}>
                {gatewayError || gatewayTest?.message}
              </div>
            </div>
          )}
        </div>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1.3fr 1fr', gap: 16, marginBottom: 20 }}>
        <div className="card" style={{ padding: 20 }}>
          <div style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-secondary)', marginBottom: 12 }}>Your local project</div>
          <div style={{ display: 'grid', gap: 10, fontSize: 13 }}>
            <div><strong>Account:</strong> {config?.account?.name || 'Local AgentShrink Workspace'}</div>
            <div><strong>Project:</strong> {config?.project?.name || config?.project_name || 'Loading...'}</div>
            <div><strong>Project slug:</strong> <code>{config?.project?.slug || 'agentshrink-project'}</code></div>
            <div><strong>Environment:</strong> <code>{config?.project?.environment || 'local'}</code></div>
            <div><strong>Gateway URL:</strong> <code>{gatewayUrl}</code></div>
            <div><strong>DB Path:</strong> <code>{config?.db_path || 'Loading...'}</code></div>
            <div><strong>Upstream:</strong> <code>{config?.gateway.upstream_provider || 'mock'}</code></div>
            <div><strong>Default model:</strong> <code>{config?.defaults.gateway_model || 'mock-model'}</code></div>
            <div><strong>Project token:</strong> <code>{config?.defaults.gateway_api_key || 'Loading...'}</code></div>
          </div>
        </div>
        <div className="card" style={{ padding: 20 }}>
          <div style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-secondary)', marginBottom: 12 }}>Local readiness</div>
          <div style={{ display: 'grid', gap: 8 }}>
            {checks.map((check) => (
              <div key={check.name} style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 12 }}>
                <span style={{
                  width: 8, height: 8, borderRadius: '50%',
                  background: check.ok ? '#1D9E75' : '#D85A30',
                  display: 'inline-block',
                }} />
                <span style={{ color: 'var(--text-primary)', minWidth: 110 }}>{check.name}</span>
                <span style={{ color: 'var(--text-tertiary)' }}>{check.detail}</span>
              </div>
            ))}
          </div>
        </div>
      </div>

      {(failingChecks.length > 0 || activeProviderHelp) && (
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16, marginBottom: 20 }}>
          <div className="card" style={{ padding: 20 }}>
            <div style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-secondary)', marginBottom: 12 }}>What needs attention</div>
            {failingChecks.length === 0 ? (
              <div style={{ fontSize: 13, color: '#1D9E75' }}>No blocking setup issues are currently reported.</div>
            ) : (
              <div style={{ display: 'grid', gap: 10 }}>
                {failingChecks.map((check) => (
                  <div key={check.name} style={{ background: '#FFF2EE', borderRadius: 10, padding: '12px 14px' }}>
                    <div style={{ fontSize: 12, fontWeight: 600, color: '#A32D2D', marginBottom: 4 }}>{check.name}</div>
                    <div style={{ fontSize: 12, color: 'var(--text-secondary)', marginBottom: check.remedy ? 6 : 0 }}>{check.detail}</div>
                    {check.remedy && <div style={{ fontSize: 12, color: '#7A4428' }}>Next step: {check.remedy}</div>}
                  </div>
                ))}
              </div>
            )}
          </div>
          <div className="card" style={{ padding: 20 }}>
            <div style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-secondary)', marginBottom: 12 }}>
              {activeProviderHelp?.title || 'Provider guidance'}
            </div>
            <div style={{ display: 'grid', gap: 8 }}>
              {(activeProviderHelp?.lines || []).map((line, idx) => (
                <div key={idx} style={{ fontSize: 13, color: 'var(--text-secondary)', lineHeight: 1.7 }}>
                  {idx + 1}. {line}
                </div>
              ))}
              {providerChecks.filter(check => !check.ok).map((check) => (
                <div key={check.name} style={{ marginTop: 10, background: '#FBF6EF', borderRadius: 10, padding: '10px 12px' }}>
                  <div style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-primary)', marginBottom: 4 }}>
                    Recovery for {check.name}
                  </div>
                  {((check.commands || []).length > 0) ? (
                    <>
                      <CodeBlock text={(check.commands || []).join('\n')} />
                      <div style={{ display: 'flex', justifyContent: 'flex-end', marginTop: 8 }}>
                        <button onClick={() => copyText(`provider-${check.name}`, (check.commands || []).join('\n'))} style={smallButton}>
                          {copiedKey === `provider-${check.name}` ? 'Copied' : 'Copy recovery commands'}
                        </button>
                      </div>
                    </>
                  ) : null}
                </div>
              ))}
              {providerChecks.length > 0 && (
                <div style={{ marginTop: 8, fontSize: 12, color: 'var(--text-tertiary)' }}>
                  Active provider checks: {providerChecks.map(check => check.name).join(', ')}
                </div>
              )}
            </div>
          </div>
        </div>
      )}

      <div className="card" style={{ padding: 20, marginBottom: 20 }}>
        <div style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-secondary)', marginBottom: 12 }}>Canonical first-run quickstart</div>
        <CodeBlock text={`agentshrink init --project-name "${config?.project?.name || config?.project_name || 'My AgentShrink Project'}"\nagentshrink doctor\nagentshrink stack up`} />
        <div style={{ marginTop: 10, fontSize: 12, color: 'var(--text-tertiary)', lineHeight: 1.7 }}>
          This is the single canonical local path now: initialize once, run doctor once, then use one foreground stack supervisor.
          After that, open <code>/welcome</code>, copy the right integration snippet, and send traffic through the gateway.
        </div>
      </div>

      <div className="card" style={{ padding: 20, marginBottom: 20 }}>
        <div style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-secondary)', marginBottom: 12 }}>Live stack status</div>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 12 }}>
          {[
            { label: 'Gateway', service: stack?.gateway },
            { label: 'Backend', service: stack?.backend },
            { label: 'Frontend', service: stack?.frontend },
          ].map(({ label, service }) => (
            <div key={label} style={{ border: '0.5px solid var(--border)', borderRadius: 12, padding: 14, background: 'var(--bg-secondary)' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 }}>
                <ServiceDot ok={!!service?.healthy} />
                <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--text-primary)' }}>{label}</div>
              </div>
              <div style={{ fontSize: 12, color: 'var(--text-secondary)', marginBottom: 6 }}>
                {service?.healthy ? 'Healthy' : service?.process_recorded ? 'Started, but not responding' : 'Not started'}
              </div>
              <div style={{ fontSize: 11, color: 'var(--text-tertiary)', wordBreak: 'break-all' }}>
                {service?.configured_url || 'Loading...'}
              </div>
            </div>
          ))}
        </div>
        {!!stack?.recommended_actions?.length && (
          <div style={{ marginTop: 16, display: 'grid', gap: 10 }}>
            <div style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-secondary)' }}>Recommended safe actions</div>
            {stack.recommended_actions.map((action) => (
              <div key={action.id} style={{ background: 'var(--bg-secondary)', borderRadius: 10, padding: '12px 14px' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12, alignItems: 'center', marginBottom: 6, flexWrap: 'wrap' }}>
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
                <CodeBlock text={action.command} />
                <div style={{ display: 'flex', justifyContent: 'flex-end', marginTop: 8 }}>
                  <button onClick={() => copyText(`stack-${action.id}`, action.command)} style={smallButton}>
                    {copiedKey === `stack-${action.id}` ? 'Copied' : 'Copy action'}
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16, marginBottom: 20 }}>
        <div className="card" style={{ padding: 20 }}>
          <div style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-secondary)', marginBottom: 10 }}>1. Start the local stack</div>
          <CodeBlock text={`agentshrink stack up`} />
          <div style={{ marginTop: 10, fontSize: 12, color: 'var(--text-tertiary)' }}>
            This launches gateway, backend, and frontend together using your saved project manifest.
          </div>
          <div style={{ marginTop: 10, fontSize: 12, color: stackReady ? '#1D9E75' : 'var(--text-tertiary)' }}>
            {stackReady ? 'Stack check: all three services are healthy.' : 'The page will auto-refresh service health every few seconds.'}
          </div>
        </div>
        <div className="card" style={{ padding: 20 }}>
          <div style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-secondary)', marginBottom: 10 }}>2. Point your app at AgentShrink</div>
          <div style={{ display: 'flex', justifyContent: 'flex-end', marginBottom: 8 }}>
            <button onClick={() => copyText('sdk', sdkSnippet)} style={smallButton}>
              {copiedKey === 'sdk' ? 'Copied' : 'Copy snippet'}
            </button>
          </div>
          <CodeBlock text={sdkSnippet} />
          <div style={{ marginTop: 10, fontSize: 12, color: 'var(--text-tertiary)' }}>
            Works for OpenAI-compatible SDKs, wrappers, and many plain HTTP apps.
          </div>
        </div>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16, marginBottom: 20 }}>
        <div className="card" style={{ padding: 20 }}>
          <div style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-secondary)', marginBottom: 10 }}>3. Raw HTTP example</div>
          <div style={{ display: 'flex', justifyContent: 'flex-end', marginBottom: 8 }}>
            <button onClick={() => copyText('raw', rawSnippet)} style={smallButton}>
              {copiedKey === 'raw' ? 'Copied' : 'Copy snippet'}
            </button>
          </div>
          <CodeBlock text={rawSnippet} />
        </div>
        <div className="card" style={{ padding: 20 }}>
          <div style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-secondary)', marginBottom: 10 }}>4. LangChain/LangGraph logging snippet</div>
          <div style={{ display: 'flex', justifyContent: 'flex-end', marginBottom: 8 }}>
            <button onClick={() => copyText('langchain-logger', langchainLoggerSnippet)} style={smallButton}>
              {copiedKey === 'langchain-logger' ? 'Copied' : 'Copy snippet'}
            </button>
          </div>
          <CodeBlock text={langchainLoggerSnippet} />
          <div style={{ marginTop: 10, fontSize: 12, color: 'var(--text-tertiary)' }}>
            Start here for LangChain or LangGraph apps when you want to capture traffic with AgentShrink logging before enabling routing.
          </div>
        </div>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16, marginBottom: 20 }}>
        <div className="card" style={{ padding: 20 }}>
          <div style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-secondary)', marginBottom: 10 }}>5. LangChain/LangGraph routed snippet</div>
          <div style={{ display: 'flex', justifyContent: 'flex-end', marginBottom: 8 }}>
            <button onClick={() => copyText('langchain-routed', langchainRoutedSnippet)} style={smallButton}>
              {copiedKey === 'langchain-routed' ? 'Copied' : 'Copy snippet'}
            </button>
          </div>
          <CodeBlock text={langchainRoutedSnippet} />
          <div style={{ marginTop: 10, fontSize: 12, color: 'var(--text-tertiary)' }}>
            Switch to this after analysis and report application when you want AgentShrink to route compatible LangChain or LangGraph calls automatically.
          </div>
        </div>
        <div className="card" style={{ padding: 20 }}>
          <div style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-secondary)', marginBottom: 10 }}>6. What happens next</div>
          <div style={{ fontSize: 13, color: 'var(--text-secondary)', lineHeight: 1.8 }}>
            <div>1. Traffic appears in <strong>Live Routing</strong>.</div>
            <div>2. Repeated call families appear in <strong>Cluster Map</strong>.</div>
            <div>3. You generate a <strong>Replaceability Report</strong>.</div>
            <div>4. Then you apply safe routing and optionally fine-tune borderline clusters.</div>
          </div>
        </div>
      </div>
    </div>
  )
}

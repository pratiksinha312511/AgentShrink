'use client'
import { useEffect, useState } from 'react'
import Link from 'next/link'
import { fetchProductConfig, fetchProductDoctor, fetchProductStack, testProductGateway } from '@/lib/api'
import {
  PageShell, PageHeader, TerminalCard, Badge, PrimaryButton, SecondaryButton,
  CodeBlock, StatusDot, ErrorBlock, SuccessBlock,
} from '@/components/Terminal'

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

  return (
    <PageShell maxWidth={980}>
      {/* Hero */}
      <TerminalCard>
        <div style={{ fontSize: 11, fontWeight: 600, color: '#6C63FF', textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 8 }}>
          Onboarding
        </div>
        <h1 className="font-display" style={{ fontSize: 22, fontWeight: 800, margin: 0, color: '#3D4852', letterSpacing: '-0.01em' }}>
          Connect any AI agent, observe its calls, then shrink the easy steps to cheaper local models.
        </h1>
        <p style={{ marginTop: 10, fontSize: 12, color: 'var(--text-secondary)', lineHeight: 1.7 }}>
          Point an OpenAI-compatible client or raw HTTP app at the AgentShrink gateway.
          Test the full flow for free in mock mode.
        </p>
        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginTop: 12 }}>
          <Badge variant="green">local-first</Badge>
          <Badge variant="blue">openai-compatible</Badge>
          <Badge variant="purple">free mock mode</Badge>
        </div>

        {/* Stack readiness */}
        <div style={{
          marginTop: 16, padding: 14,
          border: 'none',
          background: stackReady ? 'rgba(56, 178, 172, 0.08)' : '#E0E5EC',
          borderRadius: 20,
          boxShadow: 'inset 6px 6px 10px rgb(163,177,198,0.6), inset -6px -6px 10px rgba(255,255,255,0.5)',
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 6 }}>
            <StatusDot ok={stackReady} pulse={stackReady} />
            <div style={{ fontSize: 12, fontWeight: 700, color: stackReady ? '#38B2AC' : '#3D4852' }}>
              {readinessLabel}
            </div>
          </div>
          <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginTop: 10 }}>
            <Link href="/routing"><SecondaryButton>ROUTING</SecondaryButton></Link>
            <Link href="/clusters"><SecondaryButton>CLUSTERS</SecondaryButton></Link>
            <Link href="/report"><SecondaryButton>REPORT</SecondaryButton></Link>
            <SecondaryButton onClick={runGatewayTest} disabled={testingGateway || !stack?.gateway.healthy}>
              {testingGateway ? 'TESTING...' : 'TEST GATEWAY'}
            </SecondaryButton>
          </div>
          {gatewayError && <ErrorBlock message={gatewayError} />}
          {gatewayTest && <SuccessBlock message={gatewayTest.message} />}
        </div>
      </TerminalCard>

      {/* Project info + Doctor checks */}
      <div style={{ display: 'grid', gridTemplateColumns: '1.3fr 1fr', gap: 16 }}>
        <TerminalCard title="LOCAL PROJECT">
          <div style={{ display: 'grid', gap: 6, fontSize: 11 }}>
            {[
              ['account', config?.account?.name || 'Local AgentShrink Workspace'],
              ['project', config?.project?.name || config?.project_name || 'Loading...'],
              ['slug', config?.project?.slug || 'agentshrink-project'],
              ['env', config?.project?.environment || 'local'],
              ['gateway', gatewayUrl],
              ['db', config?.db_path || 'Loading...'],
              ['upstream', config?.gateway.upstream_provider || 'mock'],
              ['model', config?.defaults.gateway_model || 'mock-model'],
              ['token', config?.defaults.gateway_api_key || 'Loading...'],
            ].map(([k, v]) => (
              <div key={k} style={{ display: 'flex', gap: 8 }}>
                <span style={{ color: 'var(--text-tertiary)', minWidth: 70 }}>{k}:</span>
                <code style={{ color: 'var(--text-secondary)', wordBreak: 'break-all' }}>{v}</code>
              </div>
            ))}
          </div>
        </TerminalCard>
        <TerminalCard title="DOCTOR CHECKS">
          <div style={{ display: 'grid', gap: 6 }}>
            {checks.map((check) => (
              <div key={check.name} style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 11 }}>
                <span style={{ color: check.ok ? '#38B2AC' : '#E53E3E', fontWeight: 700, fontSize: 13 }}>
                  {check.ok ? '✓' : '✗'}
                </span>
                <span style={{ color: '#3D4852', minWidth: 100 }}>{check.name}</span>
                <span style={{ color: 'var(--text-tertiary)' }}>{check.detail}</span>
              </div>
            ))}
          </div>
        </TerminalCard>
      </div>

      {/* Attention + provider */}
      {(failingChecks.length > 0 || activeProviderHelp) && (
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
          <TerminalCard title="NEEDS ATTENTION">
            {failingChecks.length === 0 ? (
              <div style={{ fontSize: 11, color: '#38B2AC' }}>No blocking issues.</div>
            ) : (
              <div style={{ display: 'grid', gap: 8 }}>
                {failingChecks.map((check) => (
                  <div key={check.name} style={{ borderLeft: '3px solid #E53E3E', borderRadius: '0 12px 12px 0', padding: '8px 12px', background: 'rgba(229,62,62,0.04)' }}>
                    <div style={{ fontSize: 11, fontWeight: 700, color: '#C53030' }}>{check.name}</div>
                    <div style={{ fontSize: 10, color: 'var(--text-secondary)', marginTop: 2 }}>{check.detail}</div>
                    {check.remedy && <div style={{ fontSize: 10, color: 'var(--terminal-amber)', marginTop: 2 }}>→ {check.remedy}</div>}
                  </div>
                ))}
              </div>
            )}
          </TerminalCard>
          <TerminalCard title={activeProviderHelp?.title?.toUpperCase() || 'PROVIDER GUIDANCE'}>
            <div style={{ display: 'grid', gap: 6 }}>
              {(activeProviderHelp?.lines || []).map((line, idx) => (
                <div key={idx} style={{ fontSize: 11, color: 'var(--text-secondary)', lineHeight: 1.6 }}>
                  {idx + 1}. {line}
                </div>
              ))}
              {providerChecks.filter(check => !check.ok).map((check) => (
                <div key={check.name} style={{ marginTop: 8, borderLeft: '3px solid #D69E2E', borderRadius: '0 12px 12px 0', padding: '8px 12px', background: 'rgba(214,158,46,0.04)' }}>
                  <div style={{ fontSize: 11, fontWeight: 700, color: '#3D4852' }}>Recovery: {check.name}</div>
                  {(check.commands || []).length > 0 && (
                    <CodeBlock text={(check.commands || []).join('\n')} />
                  )}
                </div>
              ))}
            </div>
          </TerminalCard>
        </div>
      )}

      {/* Quickstart */}
      <TerminalCard title="QUICKSTART">
        <CodeBlock text={`agentshrink init --project-name "${config?.project?.name || config?.project_name || 'My AgentShrink Project'}"\nagentshrink doctor\nagentshrink stack up`} />
        <div style={{ marginTop: 8, fontSize: 10, color: 'var(--text-tertiary)', lineHeight: 1.6 }}>
          Initialize once, run doctor once, then use one foreground stack supervisor.
        </div>
      </TerminalCard>

      {/* Stack status */}
      <TerminalCard title="STACK STATUS">
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 12 }}>
          {[
            { label: 'Gateway', service: stack?.gateway },
            { label: 'Backend', service: stack?.backend },
            { label: 'Frontend', service: stack?.frontend },
          ].map(({ label, service }) => (
            <div key={label} style={{ padding: 14, borderRadius: 20, background: '#E0E5EC', boxShadow: '5px 5px 10px rgb(163,177,198,0.6), -5px -5px 10px rgba(255,255,255,0.5)' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 6 }}>
                <StatusDot ok={!!service?.healthy} pulse={!!service?.healthy} />
                <div style={{ fontSize: 12, fontWeight: 700, color: '#3D4852' }}>{label}</div>
              </div>
              <div style={{ fontSize: 10, color: 'var(--text-secondary)' }}>
                {service?.healthy ? 'Healthy' : service?.process_recorded ? 'Started, not responding' : 'Not started'}
              </div>
              <div style={{ fontSize: 9, color: 'var(--text-tertiary)', wordBreak: 'break-all', marginTop: 4 }}>
                {service?.configured_url || 'loading...'}
              </div>
            </div>
          ))}
        </div>
        {!!stack?.recommended_actions?.length && (
          <div style={{ marginTop: 14, display: 'grid', gap: 8 }}>
            {stack.recommended_actions.map((action) => (
              <div key={action.id} style={{ borderLeft: `3px solid ${action.risk === 'caution' ? '#D69E2E' : '#38B2AC'}`, borderRadius: '0 12px 12px 0', padding: '10px 14px', background: 'rgba(0,0,0,0.02)' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8, alignItems: 'center' }}>
                  <div style={{ fontSize: 12, fontWeight: 700, color: '#3D4852' }}>{action.label}</div>
                  <Badge variant={action.risk === 'caution' ? 'amber' : 'green'}>{action.risk.toUpperCase()}</Badge>
                </div>
                <div style={{ fontSize: 10, color: 'var(--text-secondary)', marginTop: 4, marginBottom: 6 }}>{action.reason}</div>
                <CodeBlock text={action.command} />
              </div>
            ))}
          </div>
        )}
      </TerminalCard>

      {/* Integration snippets */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
        <TerminalCard title="1. START STACK">
          <CodeBlock text="agentshrink stack up" />
          <div style={{ marginTop: 8, fontSize: 11, color: stackReady ? '#38B2AC' : '#9CA3AF' }}>
            {stackReady ? 'All services healthy.' : 'Auto-refreshes every few seconds.'}
          </div>
        </TerminalCard>
        <TerminalCard title="2. OPENAI SDK">
          <CodeBlock text={sdkSnippet} />
        </TerminalCard>
      </div>
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
        <TerminalCard title="3. RAW HTTP">
          <CodeBlock text={rawSnippet} />
        </TerminalCard>
        <TerminalCard title="4. LANGCHAIN LOGGER">
          <CodeBlock text={langchainLoggerSnippet} />
        </TerminalCard>
      </div>
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
        <TerminalCard title="5. LANGCHAIN ROUTED">
          <CodeBlock text={langchainRoutedSnippet} />
        </TerminalCard>
        <TerminalCard title="6. WHAT HAPPENS NEXT">
          <div style={{ fontSize: 11, color: 'var(--text-secondary)', lineHeight: 1.8 }}>
            <div>1. Traffic appears in <strong style={{ color: '#3D4852' }}>Live Routing</strong>.</div>
            <div>2. Repeated call families appear in <strong style={{ color: '#3D4852' }}>Cluster Map</strong>.</div>
            <div>3. You generate a <strong style={{ color: '#3D4852' }}>Replaceability Report</strong>.</div>
            <div>4. Apply safe routing and optionally fine-tune borderline clusters.</div>
          </div>
        </TerminalCard>
      </div>
    </PageShell>
  )
}

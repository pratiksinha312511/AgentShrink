import Link from 'next/link'

const sectionCard = {
  background: 'rgba(255,255,255,0.82)',
  border: '0.5px solid var(--border)',
  borderRadius: 18,
  padding: 24,
  backdropFilter: 'blur(10px)',
} as const

export default function PublicLandingPage() {
  return (
    <div style={{
      minHeight: '100vh',
      padding: '28px',
      background: 'linear-gradient(180deg, #F5F0E4 0%, #EFE8D8 48%, #F7F5EF 100%)',
    }}>
      <div style={{ maxWidth: 1100, margin: '0 auto' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', gap: 16, alignItems: 'center', marginBottom: 28, flexWrap: 'wrap' }}>
          <div>
            <div style={{ fontSize: 14, fontWeight: 700, color: 'var(--text-primary)' }}>AgentShrink</div>
            <div style={{ fontSize: 12, color: 'var(--text-tertiary)' }}>Public product preview</div>
          </div>
          <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
            <Link href="/site/docs" style={navLinkStyle}>Docs</Link>
            <Link href="/welcome" style={navLinkStyle}>Open Local App</Link>
          </div>
        </div>

        <section style={{
          ...sectionCard,
          padding: 36,
          background: 'linear-gradient(135deg, rgba(255,255,255,0.92) 0%, rgba(248,244,234,0.92) 100%)',
          marginBottom: 18,
        }}>
          <div style={{ display: 'grid', gridTemplateColumns: '1.4fr 1fr', gap: 20, alignItems: 'center' }}>
            <div>
              <div style={{ fontSize: 11, textTransform: 'uppercase', letterSpacing: '0.08em', color: '#6C675A', marginBottom: 10 }}>
                Hosted-ready V1 Slice
              </div>
              <h1 style={{ fontSize: 44, lineHeight: 1.05, margin: 0, color: 'var(--text-primary)', maxWidth: 680 }}>
                Turn expensive AI agent steps into safe, explainable local routing decisions.
              </h1>
              <p style={{ marginTop: 16, fontSize: 16, lineHeight: 1.8, color: 'var(--text-secondary)', maxWidth: 720 }}>
                AgentShrink captures step-by-step LLM traffic, clusters repeated work, explains what can move local,
                and lets teams apply routing with simulation, rollback, and clearer trust signals.
              </p>
              <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap', marginTop: 18 }}>
                <Link href="/site/docs" style={primaryCtaStyle}>Read the docs</Link>
                <Link href="/welcome" style={secondaryCtaStyle}>Try the local product</Link>
              </div>
            </div>
            <div style={{
              borderRadius: 18,
              padding: 22,
              background: '#171714',
              color: '#F7F4ED',
              fontFamily: 'ui-monospace, SFMono-Regular, Menlo, monospace',
              fontSize: 12,
              lineHeight: 1.6,
              boxShadow: '0 14px 35px rgba(0,0,0,0.12)',
            }}>
              <div>$ client = OpenAI(</div>
              <div>&nbsp;&nbsp;base_url="https://gateway.agentshrink.ai/v1",</div>
              <div>&nbsp;&nbsp;api_key="as_live_your_project_token",</div>
              <div>)</div>
              <div style={{ marginTop: 10 }}>$ run_your_agent()</div>
              <div>$ see routing, clusters, and savings</div>
            </div>
          </div>
        </section>

        <section style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 16, marginBottom: 18 }}>
          {[
            {
              title: 'Observe',
              text: 'Capture OpenAI-compatible, LangChain, and raw HTTP traffic through one gateway or wrapper seam.',
            },
            {
              title: 'Explain',
              text: 'See why AgentShrink recommends Replace now, Fine-tune, or Keep on API before any routing change lands.',
            },
            {
              title: 'Apply Safely',
              text: 'Preview routing changes, preserve fine-tuned routes, and rollback when a new routing config is not what you wanted.',
            },
          ].map((item) => (
            <div key={item.title} style={sectionCard}>
              <div style={{ fontSize: 18, fontWeight: 600, color: 'var(--text-primary)', marginBottom: 8 }}>{item.title}</div>
              <div style={{ fontSize: 14, color: 'var(--text-secondary)', lineHeight: 1.8 }}>{item.text}</div>
            </div>
          ))}
        </section>

        <section style={{ ...sectionCard, marginBottom: 18 }}>
          <div style={{ fontSize: 12, fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.08em', color: 'var(--text-tertiary)', marginBottom: 12 }}>
            Why teams would use this
          </div>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 18 }}>
            <div>
              <div style={{ fontSize: 16, fontWeight: 600, color: 'var(--text-primary)', marginBottom: 8 }}>Trust over blind optimization</div>
              <div style={{ fontSize: 14, color: 'var(--text-secondary)', lineHeight: 1.8 }}>
                The product now surfaces provider recovery guidance, safer stack actions, route explanations, and simulation before apply.
                That gives a real trust layer instead of just “route because the score was high.”
              </div>
            </div>
            <div>
              <div style={{ fontSize: 16, fontWeight: 600, color: 'var(--text-primary)', marginBottom: 8 }}>Hosted-ready contract</div>
              <div style={{ fontSize: 14, color: 'var(--text-secondary)', lineHeight: 1.8 }}>
                This v1 slice introduces the public product shape: marketing/docs surfaces and project-token-based gateway access,
                which is the right boundary for a future hosted dashboard and hosted gateway.
              </div>
            </div>
          </div>
        </section>
      </div>
    </div>
  )
}

const navLinkStyle = {
  textDecoration: 'none',
  color: 'var(--text-primary)',
  fontSize: 13,
  fontWeight: 600,
  padding: '10px 12px',
  borderRadius: 10,
  background: 'rgba(255,255,255,0.68)',
  border: '0.5px solid var(--border)',
} as const

const primaryCtaStyle = {
  textDecoration: 'none',
  color: '#fff',
  fontSize: 14,
  fontWeight: 700,
  padding: '12px 16px',
  borderRadius: 12,
  background: '#0F6E56',
} as const

const secondaryCtaStyle = {
  textDecoration: 'none',
  color: 'var(--text-primary)',
  fontSize: 14,
  fontWeight: 700,
  padding: '12px 16px',
  borderRadius: 12,
  background: 'rgba(255,255,255,0.8)',
  border: '0.5px solid var(--border)',
} as const

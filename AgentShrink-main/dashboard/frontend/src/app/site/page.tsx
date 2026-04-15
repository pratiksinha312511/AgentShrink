import Link from 'next/link'

/* ── SVG Icons ── */
const IconMicroscope = () => (
  <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#6C63FF" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <path d="M6 18h8" /><path d="M3 22h18" /><path d="M14 22a7 7 0 1 0 0-14h-1" />
    <path d="M9 14h2" /><path d="M9 12a2 2 0 0 1-2-2V6h6v4a2 2 0 0 1-2 2Z" />
    <path d="M12 6V3a1 1 0 0 0-1-1H9a1 1 0 0 0-1 1v3" />
  </svg>
)
const IconSearch = () => (
  <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#6C63FF" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <circle cx="11" cy="11" r="8" /><path d="m21 21-4.3-4.3" />
  </svg>
)
const IconLightbulb = () => (
  <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#6C63FF" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <path d="M15 14c.2-1 .7-1.7 1.5-2.5 1-.9 1.5-2.2 1.5-3.5A6 6 0 0 0 6 8c0 1 .2 2.2 1.5 3.5.7.7 1.3 1.5 1.5 2.5" />
    <path d="M9 18h6" /><path d="M10 22h4" />
  </svg>
)
const IconShield = () => (
  <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#6C63FF" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <path d="M20 13c0 5-3.5 7.5-7.66 8.95a1 1 0 0 1-.67-.01C7.5 20.5 4 18 4 13V6a1 1 0 0 1 1-1c2 0 4.5-1.2 6.24-2.72a1.17 1.17 0 0 1 1.52 0C14.51 3.81 17 5 19 5a1 1 0 0 1 1 1z" />
    <path d="m9 12 2 2 4-4" />
  </svg>
)

/* ── Neumorphic style tokens ── */
const neuCard = {
  background: '#E0E5EC',
  borderRadius: 32,
  padding: 28,
  boxShadow: '9px 9px 16px rgb(163,177,198,0.6), -9px -9px 16px rgba(255,255,255,0.5)',
} as const

const neuCardSm = {
  background: '#E0E5EC',
  borderRadius: 24,
  padding: 24,
  boxShadow: '5px 5px 10px rgb(163,177,198,0.6), -5px -5px 10px rgba(255,255,255,0.5)',
} as const

const neuInset = {
  background: '#E0E5EC',
  borderRadius: 20,
  padding: 22,
  boxShadow: 'inset 6px 6px 12px rgb(163,177,198,0.6), inset -6px -6px 12px rgba(255,255,255,0.5)',
} as const

export default function PublicLandingPage() {
  return (
    <div style={{
      minHeight: '100vh',
      padding: '32px',
      background: '#E0E5EC',
      fontFamily: "'DM Sans', sans-serif",
    }}>
      <div style={{ maxWidth: 1120, margin: '0 auto' }}>
        {/* â”€â”€ Nav â”€â”€ */}
        <div style={{ display: 'flex', justifyContent: 'space-between', gap: 16, alignItems: 'center', marginBottom: 32, flexWrap: 'wrap' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
            <div style={{
              width: 40, height: 40, borderRadius: 14,
              background: '#E0E5EC',
              boxShadow: '5px 5px 10px rgb(163,177,198,0.6), -5px -5px 10px rgba(255,255,255,0.5)',
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              fontSize: 20,
            }}><IconMicroscope /></div>
            <div>
              <div className="font-display" style={{ fontSize: 16, fontWeight: 800, color: '#3D4852', letterSpacing: '-0.02em' }}>AgentShrink</div>
              <div style={{ fontSize: 11, color: '#9CA3AF' }}>Intelligent LLM-to-SLM routing</div>
            </div>
          </div>
          <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
            <Link href="/site/docs" style={navLinkStyle}>Docs</Link>
            <Link href="/auth" style={navLinkStyle}>Sign In</Link>
            <Link href="/projects" style={navLinkStyle}>Create Project</Link>
            <Link href="/welcome" style={navLinkStyle}>Dashboard</Link>
          </div>
        </div>

        {/* â”€â”€ Hero â”€â”€ */}
        <section style={{ ...neuCard, padding: 40, marginBottom: 20 }}>
          <div style={{ display: 'grid', gridTemplateColumns: '1.4fr 1fr', gap: 28, alignItems: 'center' }}>
            <div>
              <span style={{
                display: 'inline-block', fontSize: 11, fontWeight: 600,
                color: '#6C63FF', background: 'rgba(108,99,255,0.1)',
                padding: '4px 14px', borderRadius: 9999, marginBottom: 14,
                letterSpacing: '0.04em', textTransform: 'uppercase',
                boxShadow: '3px 3px 6px rgb(163,177,198,0.4), -3px -3px 6px rgba(255,255,255,0.4)',
              }}>
                Based on arXiv:2506.02153
              </span>
              <h1 className="font-display" style={{ fontSize: 42, lineHeight: 1.08, margin: 0, color: '#3D4852', maxWidth: 640, fontWeight: 800, letterSpacing: '-0.02em' }}>
                Cut 70% of your AI agent costs with intelligent local routing
              </h1>
              <p style={{ marginTop: 16, fontSize: 15, lineHeight: 1.8, color: '#6B7280', maxWidth: 580 }}>
                AgentShrink captures every LLM call your agent makes, discovers which ones don&apos;t need GPT-4o,
                and routes them to free local models — with simulation, rollback, and full explainability.
              </p>

              {/* â”€â”€ Benchmark stats â”€â”€ */}
              <div style={{ display: 'flex', gap: 16, marginTop: 20, flexWrap: 'wrap' }}>
                {[
                  { value: '~70%', label: 'Cost reduction' },
                  { value: '60-70%', label: 'Calls routed local' },
                  { value: '~10ms', label: 'Routing latency' },
                ].map(s => (
                  <div key={s.label} style={{ ...neuInset, padding: '12px 18px', borderRadius: 16, textAlign: 'center' as const, minWidth: 110 }}>
                    <div className="font-display" style={{ fontSize: 22, fontWeight: 800, color: '#6C63FF' }}>{s.value}</div>
                    <div style={{ fontSize: 11, color: '#9CA3AF', marginTop: 2 }}>{s.label}</div>
                  </div>
                ))}
              </div>

              <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap', marginTop: 22 }}>
                <Link href="/site/docs" style={primaryCtaStyle}>Read the Docs</Link>
                <Link href="/auth" style={secondaryCtaStyle}>Sign In</Link>
                <Link href="/projects" style={secondaryCtaStyle}>Create Project</Link>
              </div>
            </div>

            {/* â”€â”€ Code snippet â”€â”€ */}
            <div style={{
              ...neuInset, padding: 22, borderRadius: 20,
              fontFamily: 'ui-monospace, SFMono-Regular, Menlo, monospace',
              fontSize: 12.5, lineHeight: 1.7, color: '#3D4852',
            }}>
              <div style={{ color: '#9CA3AF', marginBottom: 6 }}># One-line integration</div>
              <div><span style={{ color: '#6C63FF' }}>from</span> openai <span style={{ color: '#6C63FF' }}>import</span> OpenAI</div>
              <div style={{ marginTop: 8 }}>client = OpenAI(</div>
              <div>&nbsp;&nbsp;base_url=<span style={{ color: '#38B2AC' }}>&quot;http://localhost:8100/v1&quot;</span>,</div>
              <div>&nbsp;&nbsp;api_key=<span style={{ color: '#38B2AC' }}>&quot;as_live_your_project_token&quot;</span>,</div>
              <div>)</div>
              <div style={{ marginTop: 8, color: '#9CA3AF' }}># That&apos;s it. AgentShrink handles routing.</div>
              <div>response = client.chat.completions.create(</div>
              <div>&nbsp;&nbsp;model=<span style={{ color: '#38B2AC' }}>&quot;gpt-4o-mini&quot;</span>,</div>
              <div>&nbsp;&nbsp;messages=[...],</div>
              <div>)</div>
            </div>
          </div>
        </section>

        {/* â”€â”€ How it works (S1-S6) â”€â”€ */}
        <section style={{ ...neuCard, marginBottom: 20, padding: 32 }}>
          <div style={{ fontSize: 11, fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.08em', color: '#9CA3AF', marginBottom: 16 }}>
            The 6-Step Algorithm (S1 \u2192 S6)
          </div>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 14 }}>
            {[
              { step: 'S1', title: 'Instrument', desc: 'Add a 1-line logger or point at the gateway. Captures every LLM call to SQLite.' },
              { step: 'S2', title: 'Curate', desc: 'Remove PII, deduplicate near-identical prompts, and prepare clean training data.' },
              { step: 'S3', title: 'Cluster', desc: 'HDBSCAN on sentence embeddings discovers natural task groups in your agent\'s traffic.' },
              { step: 'S4', title: 'Evaluate', desc: 'Benchmark local SLMs on each cluster using LLM-as-judge scoring (quality, safety, format).' },
              { step: 'S5', title: 'Fine-tune', desc: 'QLoRA fine-tuning on borderline clusters. Supports local, HuggingFace, and Modal backends.' },
              { step: 'S6', title: 'Route', desc: 'ShrinkLLM intercepts calls and routes by centroid similarity in ~10ms. Full fallback safety.' },
            ].map(s => (
              <div key={s.step} style={{ ...neuCardSm, padding: 20 }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 }}>
                  <span style={{
                    display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
                    width: 30, height: 30, borderRadius: 10, fontSize: 12, fontWeight: 700,
                    color: '#6C63FF', background: 'rgba(108,99,255,0.1)',
                    boxShadow: '3px 3px 6px rgb(163,177,198,0.4), -3px -3px 6px rgba(255,255,255,0.4)',
                  }}>{s.step}</span>
                  <span className="font-display" style={{ fontSize: 16, fontWeight: 700, color: '#3D4852' }}>{s.title}</span>
                </div>
                <div style={{ fontSize: 13, color: '#6B7280', lineHeight: 1.7 }}>{s.desc}</div>
              </div>
            ))}
          </div>
        </section>

        {/* â”€â”€ Three pillars â”€â”€ */}
        <section style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 16, marginBottom: 20 }}>
          {[
            { icon: <IconSearch />, title: 'Observe', text: 'Capture OpenAI-compatible, LangChain, LangGraph, and raw HTTP traffic through one gateway or wrapper seam.' },
            { icon: <IconLightbulb />, title: 'Explain', text: 'See why AgentShrink recommends Replace, Fine-tune, or Keep on API \u2014 with confidence scores and detailed reasoning.' },
            { icon: <IconShield />, title: 'Apply Safely', text: 'Simulate routing changes before applying. Preserve fine-tuned routes. One-click rollback when needed.' },
          ].map((item) => (
            <div key={item.title} style={neuCardSm}>
              <div style={{
                width: 42, height: 42, borderRadius: 14, fontSize: 20,
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                background: '#E0E5EC', marginBottom: 12,
                boxShadow: '5px 5px 10px rgb(163,177,198,0.6), -5px -5px 10px rgba(255,255,255,0.5)',
              }}>{typeof item.icon === 'string' ? item.icon : item.icon}</div>
              <div className="font-display" style={{ fontSize: 17, fontWeight: 700, color: '#3D4852', marginBottom: 6 }}>{item.title}</div>
              <div style={{ fontSize: 13, color: '#6B7280', lineHeight: 1.8 }}>{item.text}</div>
            </div>
          ))}
        </section>

        {/* â”€â”€ Why teams use this â”€â”€ */}
        <section style={{ ...neuCard, marginBottom: 20 }}>
          <div style={{ fontSize: 11, fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.08em', color: '#9CA3AF', marginBottom: 16 }}>
            Why Teams Choose AgentShrink
          </div>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 20 }}>
            {[
              { title: 'Trust Over Blind Optimization', desc: 'Every routing decision comes with an explanation, confidence score, and simulation preview. You see what changes before anything moves.' },
              { title: 'Zero Code Rewrite', desc: 'Point your existing OpenAI client at the AgentShrink gateway. Your agent code, tools, memory, and callbacks stay exactly the same.' },
              { title: 'Full Audit Trail', desc: 'Every routing config change is logged with timestamps, user info, and cluster counts. Export audit logs as CSV for compliance.' },
              { title: 'Production Ready', desc: 'Docker deployment, project-token auth, team RBAC, provider registry with BYOK, and a polished dashboard for day-to-day operations.' },
            ].map(item => (
              <div key={item.title} style={{ ...neuInset, padding: 20, borderRadius: 20 }}>
                <div className="font-display" style={{ fontSize: 15, fontWeight: 700, color: '#3D4852', marginBottom: 6 }}>{item.title}</div>
                <div style={{ fontSize: 13, color: '#6B7280', lineHeight: 1.8 }}>{item.desc}</div>
              </div>
            ))}
          </div>
        </section>

        {/* â”€â”€ Supported integrations â”€â”€ */}
        <section style={{ ...neuCard, marginBottom: 20 }}>
          <div style={{ fontSize: 11, fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.08em', color: '#9CA3AF', marginBottom: 16 }}>
            Works With Your Stack
          </div>
          <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap' }}>
            {['OpenAI SDK', 'LangChain', 'LangGraph', 'Raw HTTP', 'Ollama', 'HuggingFace', 'NVIDIA NIM', 'Any OpenAI-compatible API'].map(tag => (
              <span key={tag} style={{
                fontSize: 13, fontWeight: 600, color: '#3D4852',
                padding: '8px 16px', borderRadius: 9999,
                background: '#E0E5EC',
                boxShadow: '5px 5px 10px rgb(163,177,198,0.6), -5px -5px 10px rgba(255,255,255,0.5)',
              }}>{tag}</span>
            ))}
          </div>
        </section>

        {/* â”€â”€ Get started CTA â”€â”€ */}
        <section style={{ ...neuCard, padding: 36, textAlign: 'center' as const, marginBottom: 20 }}>
          <h2 className="font-display" style={{ fontSize: 26, fontWeight: 800, color: '#3D4852', margin: '0 0 10px', letterSpacing: '-0.02em' }}>
            Start Saving in 5 Minutes
          </h2>
          <p style={{ fontSize: 14, color: '#6B7280', maxWidth: 500, margin: '0 auto 20px' }}>
            Create a project, point your agent at the gateway, and let AgentShrink find the savings automatically.
          </p>
          <div style={{ display: 'flex', gap: 12, justifyContent: 'center', flexWrap: 'wrap' }}>
            <Link href="/site/docs" style={primaryCtaStyle}>Read the Docs</Link>
            <Link href="/projects" style={secondaryCtaStyle}>Create a Project</Link>
            <Link href="/welcome" style={secondaryCtaStyle}>Open Dashboard</Link>
          </div>
        </section>

        {/* â”€â”€ Footer â”€â”€ */}
        <footer style={{ textAlign: 'center', padding: '16px 0', fontSize: 12, color: '#9CA3AF' }}>
          AgentShrink · Based on{' '}
          <a href="https://arxiv.org/abs/2506.02153" target="_blank" rel="noopener noreferrer" style={{ color: '#6C63FF', textDecoration: 'none' }}>
            arXiv:2506.02153
          </a>{' '}
          · NVIDIA Research
        </footer>
      </div>
    </div>
  )
}

const navLinkStyle = {
  textDecoration: 'none',
  color: '#3D4852',
  fontSize: 13,
  fontWeight: 600,
  padding: '10px 16px',
  borderRadius: 12,
  background: '#E0E5EC',
  boxShadow: '5px 5px 10px rgb(163,177,198,0.6), -5px -5px 10px rgba(255,255,255,0.5)',
} as const

const primaryCtaStyle = {
  textDecoration: 'none',
  color: '#fff',
  fontSize: 14,
  fontWeight: 700,
  padding: '12px 22px',
  borderRadius: 16,
  background: '#6C63FF',
  boxShadow: '5px 5px 10px rgb(163,177,198,0.6), -5px -5px 10px rgba(255,255,255,0.5)',
} as const

const secondaryCtaStyle = {
  textDecoration: 'none',
  color: '#3D4852',
  fontSize: 14,
  fontWeight: 700,
  padding: '12px 22px',
  borderRadius: 16,
  background: '#E0E5EC',
  boxShadow: '5px 5px 10px rgb(163,177,198,0.6), -5px -5px 10px rgba(255,255,255,0.5)',
} as const

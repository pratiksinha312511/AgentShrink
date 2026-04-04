import Link from 'next/link'

function DocCode({ children }: { children: React.ReactNode }) {
  return (
    <pre style={{
      margin: 0,
      padding: '14px 16px',
      borderRadius: 14,
      background: '#171714',
      color: '#F7F4ED',
      fontSize: 12,
      lineHeight: 1.65,
      overflowX: 'auto',
      whiteSpace: 'pre-wrap',
    }}>
      {children}
    </pre>
  )
}

export default function PublicDocsPage() {
  return (
    <div style={{
      minHeight: '100vh',
      padding: '28px',
      background: 'linear-gradient(180deg, #F8F5EE 0%, #F0EADA 100%)',
    }}>
      <div style={{ maxWidth: 980, margin: '0 auto' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', gap: 16, alignItems: 'center', marginBottom: 24, flexWrap: 'wrap' }}>
          <div>
            <div style={{ fontSize: 14, fontWeight: 700, color: 'var(--text-primary)' }}>AgentShrink Docs</div>
            <div style={{ fontSize: 12, color: 'var(--text-tertiary)' }}>Public quickstart preview</div>
          </div>
          <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
            <Link href="/site" style={navLinkStyle}>Landing</Link>
            <Link href="/welcome" style={navLinkStyle}>Local app</Link>
          </div>
        </div>

        <div style={{ display: 'grid', gap: 16 }}>
          <section style={sectionCard}>
            <div style={sectionLabel}>Quickstart</div>
            <h1 style={{ fontSize: 32, margin: '0 0 10px', color: 'var(--text-primary)' }}>
              Connect an OpenAI-compatible app with a project token
            </h1>
            <p style={bodyStyle}>
              The hosted/public product direction starts with one clear contract: point your app at the AgentShrink gateway,
              authenticate with a project token, and let AgentShrink trace and optimize the repeated work.
            </p>
            <DocCode>{`from openai import OpenAI

client = OpenAI(
    base_url="https://gateway.agentshrink.ai/v1",
    api_key="as_live_your_project_token",
)`}</DocCode>
          </section>

          <section style={{ ...sectionCard, display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
            <div>
              <div style={sectionLabel}>LangChain / LangGraph</div>
              <DocCode>{`from agentshrink import AgentShrinkLogger
from langchain_openai import ChatOpenAI

llm = ChatOpenAI(
    base_url="https://gateway.agentshrink.ai/v1",
    api_key="as_live_your_project_token",
    model="gpt-4o-mini",
    callbacks=[AgentShrinkLogger()],
)`}</DocCode>
            </div>
            <div>
              <div style={sectionLabel}>Raw HTTP</div>
              <DocCode>{`import requests

response = requests.post(
    "https://gateway.agentshrink.ai/v1/chat/completions",
    headers={"Authorization": "Bearer as_live_your_project_token"},
    json={
        "model": "gpt-4o-mini",
        "messages": [{"role": "user", "content": "hello"}],
    },
)`}</DocCode>
            </div>
          </section>

          <section style={sectionCard}>
            <div style={sectionLabel}>How the trust layer works</div>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 14 }}>
              {[
                'Simulation shows what would change before you apply routing.',
                'Rollback restores the previous routing config if a new policy is wrong.',
                'Explainability surfaces why a route is proposed, preserved, or kept on API.',
              ].map((item) => (
                <div key={item} style={{ background: 'var(--bg-secondary)', borderRadius: 12, padding: '14px 16px', fontSize: 13, color: 'var(--text-secondary)', lineHeight: 1.7 }}>
                  {item}
                </div>
              ))}
            </div>
          </section>

          <section style={sectionCard}>
            <div style={sectionLabel}>Current product boundary</div>
            <p style={bodyStyle}>
              This repo now includes the first real v1 slice: a public-facing landing/docs surface and project-token-based gateway access.
              Full hosted accounts, teams, billing, and hosted dashboard separation are still future work, but the auth and public entry shape are now real.
            </p>
          </section>
        </div>
      </div>
    </div>
  )
}

const sectionCard = {
  background: 'rgba(255,255,255,0.88)',
  border: '0.5px solid var(--border)',
  borderRadius: 18,
  padding: 24,
} as const

const sectionLabel = {
  fontSize: 11,
  fontWeight: 700,
  textTransform: 'uppercase' as const,
  letterSpacing: '0.08em',
  color: 'var(--text-tertiary)',
  marginBottom: 10,
} as const

const bodyStyle = {
  fontSize: 14,
  color: 'var(--text-secondary)',
  lineHeight: 1.8,
} as const

const navLinkStyle = {
  textDecoration: 'none',
  color: 'var(--text-primary)',
  fontSize: 13,
  fontWeight: 600,
  padding: '10px 12px',
  borderRadius: 10,
  background: 'rgba(255,255,255,0.72)',
  border: '0.5px solid var(--border)',
} as const

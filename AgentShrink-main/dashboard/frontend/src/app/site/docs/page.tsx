import Link from 'next/link'

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
  padding: 20,
  boxShadow: 'inset 6px 6px 12px rgb(163,177,198,0.6), inset -6px -6px 12px rgba(255,255,255,0.5)',
} as const

function DocCode({ children }: { children: React.ReactNode }) {
  return (
    <pre style={{
      margin: 0,
      ...neuInset,
      padding: '16px 20px',
      fontFamily: 'ui-monospace, SFMono-Regular, Menlo, monospace',
      fontSize: 12.5,
      lineHeight: 1.65,
      overflowX: 'auto',
      whiteSpace: 'pre-wrap',
      color: '#3D4852',
    }}>
      {children}
    </pre>
  )
}

function SectionLabel({ children }: { children: React.ReactNode }) {
  return (
    <div style={{
      fontSize: 11, fontWeight: 700, textTransform: 'uppercase',
      letterSpacing: '0.08em', color: '#9CA3AF', marginBottom: 12,
    }}>
      {children}
    </div>
  )
}

export default function PublicDocsPage() {
  return (
    <div style={{
      minHeight: '100vh',
      padding: '32px',
      background: '#E0E5EC',
      fontFamily: "'DM Sans', sans-serif",
    }}>
      <div style={{ maxWidth: 1000, margin: '0 auto' }}>
        {/* ── Nav ── */}
        <div style={{ display: 'flex', justifyContent: 'space-between', gap: 16, alignItems: 'center', marginBottom: 28, flexWrap: 'wrap' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
            <div style={{
              width: 36, height: 36, borderRadius: 12,
              background: '#E0E5EC',
              boxShadow: '5px 5px 10px rgb(163,177,198,0.6), -5px -5px 10px rgba(255,255,255,0.5)',
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              fontSize: 18,
            }}>📖</div>
            <div>
              <div className="font-display" style={{ fontSize: 15, fontWeight: 800, color: '#3D4852', letterSpacing: '-0.02em' }}>AgentShrink Docs</div>
              <div style={{ fontSize: 11, color: '#9CA3AF' }}>Complete integration guide</div>
            </div>
          </div>
          <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
            <Link href="/site" style={navLinkStyle}>Home</Link>
            <Link href="/auth" style={navLinkStyle}>Sign In</Link>
            <Link href="/projects" style={navLinkStyle}>Projects</Link>
            <Link href="/welcome" style={navLinkStyle}>Dashboard</Link>
          </div>
        </div>

        <div style={{ display: 'grid', gap: 18 }}>
          {/* ── Quickstart ── */}
          <section style={neuCard}>
            <SectionLabel>Quickstart</SectionLabel>
            <h1 className="font-display" style={{ fontSize: 30, margin: '0 0 12px', color: '#3D4852', fontWeight: 800, letterSpacing: '-0.02em' }}>
              Get started in under 5 minutes
            </h1>
            <p style={bodyStyle}>
              AgentShrink works as an OpenAI-compatible proxy. Point your existing AI application at the AgentShrink gateway,
              authenticate with a project token, and let it automatically discover, cluster, and optimize your LLM calls.
            </p>

            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 14, marginTop: 16 }}>
              <div>
                <div style={stepBadge}>Step 1 — Install</div>
                <DocCode>{`git clone https://github.com/your-org/AgentShrink.git
cd AgentShrink
pip install -e .
python -m agentshrink init`}</DocCode>
              </div>
              <div>
                <div style={stepBadge}>Step 2 — Start services</div>
                <DocCode>{`python -m agentshrink stack up

# Gateway  → http://localhost:8100
# Backend  → http://localhost:8000
# Frontend → http://localhost:3000`}</DocCode>
              </div>
            </div>

            <div style={{ marginTop: 14 }}>
              <div style={stepBadge}>Step 3 — Connect your app</div>
              <DocCode>{`from openai import OpenAI

client = OpenAI(
    base_url="http://localhost:8100/v1",
    api_key="your_project_token",  # from /projects page
)

response = client.chat.completions.create(
    model="gpt-4o-mini",
    messages=[{"role": "user", "content": "Classify this ticket..."}],
)
# AgentShrink logs the call, clusters it, and routes it optimally`}</DocCode>
            </div>
          </section>

          {/* ── Integration methods ── */}
          <section style={neuCard}>
            <SectionLabel>Integration Methods</SectionLabel>
            <p style={{ ...bodyStyle, marginBottom: 16 }}>
              Three ways to connect your agent — all produce the same traced, clustered, routable data.
            </p>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 14 }}>
              <div>
                <div style={stepBadge}>OpenAI SDK / Gateway</div>
                <DocCode>{`from openai import OpenAI

client = OpenAI(
    base_url="http://localhost:8100/v1",
    api_key="your_project_token",
)

# Works with: OpenAI SDK, Agents SDK,
# any OpenAI-compatible library`}</DocCode>
              </div>
              <div>
                <div style={stepBadge}>LangChain / LangGraph</div>
                <DocCode>{`from agentshrink import AgentShrinkLogger
from langchain_openai import ChatOpenAI

llm = ChatOpenAI(
    base_url="http://localhost:8100/v1",
    api_key="your_project_token",
    model="gpt-4o-mini",
    callbacks=[AgentShrinkLogger()],
)`}</DocCode>
              </div>
              <div>
                <div style={stepBadge}>Raw HTTP</div>
                <DocCode>{`import requests

response = requests.post(
    "http://localhost:8100/v1/chat/completions",
    headers={
        "Authorization": "Bearer your_token"
    },
    json={
        "model": "gpt-4o-mini",
        "messages": [{"role": "user",
          "content": "hello"}],
    },
)`}</DocCode>
              </div>
            </div>
          </section>

          {/* ── The Algorithm ── */}
          <section style={neuCard}>
            <SectionLabel>How the Algorithm Works</SectionLabel>
            <p style={{ ...bodyStyle, marginBottom: 16 }}>
              AgentShrink implements the S1–S6 conversion algorithm from{' '}
              <a href="https://arxiv.org/abs/2506.02153" target="_blank" rel="noopener noreferrer" style={{ color: '#6C63FF', textDecoration: 'none', fontWeight: 600 }}>
                arXiv:2506.02153
              </a>{' '}
              (NVIDIA Research, June 2025).
            </p>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 14 }}>
              {[
                { step: 'S1 Instrument', desc: 'Every LLM call is intercepted and logged to SQLite with full prompt, response, latency, token counts, and run context.' },
                { step: 'S2 Curate', desc: 'PII masking, prompt deduplication by hash similarity, and data quality filtering produce clean training-ready datasets.' },
                { step: 'S3 Cluster', desc: 'Sentence embeddings (all-MiniLM-L6-v2) + HDBSCAN discover natural task groups. UMAP for visualization.' },
                { step: 'S4 Evaluate', desc: 'Each cluster is benchmarked against local SLMs using LLM-as-judge scoring on quality (40%), safety (40%), and format (20%).' },
                { step: 'S5 Fine-tune', desc: 'Borderline clusters (score 0.60–0.85) get QLoRA fine-tuning. Supports local GPU, HuggingFace, and Modal cloud backends.' },
                { step: 'S6 Route', desc: 'Centroid similarity matching routes calls in ~10ms. Confidence threshold with automatic API fallback ensures safety.' },
              ].map(item => (
                <div key={item.step} style={{ ...neuInset, padding: 16 }}>
                  <div className="font-display" style={{ fontSize: 13, fontWeight: 700, color: '#6C63FF', marginBottom: 6 }}>{item.step}</div>
                  <div style={{ fontSize: 12.5, color: '#6B7280', lineHeight: 1.7 }}>{item.desc}</div>
                </div>
              ))}
            </div>
          </section>

          {/* ── Trust layer ── */}
          <section style={neuCard}>
            <SectionLabel>The Trust Layer</SectionLabel>
            <p style={{ ...bodyStyle, marginBottom: 16 }}>
              AgentShrink doesn&apos;t just optimize — it makes every decision transparent and reversible.
            </p>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 14 }}>
              {[
                { icon: '🔮', title: 'Simulation', desc: 'Preview what would change before applying any routing config. See projected cost savings and which clusters move local.' },
                { icon: '↩️', title: 'Rollback', desc: 'One-click restore to the previous routing config. Every change is timestamped and audited in the routing audit log.' },
                { icon: '📊', title: 'Explainability', desc: 'Every route comes with a reason: score breakdown (quality/safety/format), recommendation rationale, and confidence level.' },
              ].map((item) => (
                <div key={item.title} style={neuCardSm}>
                  <div style={{
                    width: 40, height: 40, borderRadius: 12, fontSize: 20,
                    display: 'flex', alignItems: 'center', justifyContent: 'center',
                    background: '#E0E5EC', marginBottom: 10,
                    boxShadow: '5px 5px 10px rgb(163,177,198,0.6), -5px -5px 10px rgba(255,255,255,0.5)',
                  }}>{item.icon}</div>
                  <div className="font-display" style={{ fontSize: 14, fontWeight: 700, color: '#3D4852', marginBottom: 4 }}>{item.title}</div>
                  <div style={{ fontSize: 13, color: '#6B7280', lineHeight: 1.7 }}>{item.desc}</div>
                </div>
              ))}
            </div>
          </section>

          {/* ── CLI Reference ── */}
          <section style={neuCard}>
            <SectionLabel>CLI Reference</SectionLabel>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 14 }}>
              <div>
                <div style={stepBadge}>Project Management</div>
                <DocCode>{`# Initialize a new AgentShrink project
python -m agentshrink init

# Run system diagnostics
python -m agentshrink doctor

# Check project status
python -m agentshrink status

# Show version
python -m agentshrink --version`}</DocCode>
              </div>
              <div>
                <div style={stepBadge}>Stack Management</div>
                <DocCode>{`# Start all services (gateway + backend + frontend)
python -m agentshrink stack up

# Check service health
python -m agentshrink stack status

# Stop all services
python -m agentshrink stack down`}</DocCode>
              </div>
            </div>
          </section>

          {/* ── Dashboard pages ── */}
          <section style={neuCard}>
            <SectionLabel>Dashboard Pages</SectionLabel>
            <p style={{ ...bodyStyle, marginBottom: 16 }}>
              The web dashboard at <code style={{ color: '#6C63FF', fontSize: 13 }}>http://localhost:3000</code> provides full visibility into your agent&apos;s optimization pipeline.
            </p>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 14 }}>
              {[
                { page: 'Overview', path: '/', desc: 'Pipeline status, call volume, cluster breakdown, and cost savings at a glance.' },
                { page: 'Clusters', path: '/clusters', desc: 'Explore discovered task groups, see sample prompts, and review evaluation scores per cluster.' },
                { page: 'Routing', path: '/routing', desc: 'Live routing decisions with latency, provider info, similarity scores, and confidence thresholds.' },
                { page: 'Report', path: '/report', desc: 'Full analysis report with recommendations (Replace / Fine-tune / Keep) and score breakdowns.' },
                { page: 'Fine-tune', path: '/finetune', desc: 'Launch QLoRA fine-tuning jobs, monitor progress, and deploy trained adapters.' },
                { page: 'Models', path: '/models', desc: 'Model catalog — manage local SLMs, judge models, and registered fine-tuned adapters.' },
                { page: 'Settings', path: '/settings', desc: 'Project config, provider registry, gateway settings, stack logs, and doctor checks.' },
                { page: 'Projects', path: '/projects', desc: 'Multi-project management with team scoping and project token rotation.' },
                { page: 'Teams', path: '/teams', desc: 'Team CRUD, member invitations via magic link, and role-based access control.' },
              ].map(item => (
                <div key={item.page} style={{ ...neuInset, padding: 14, borderRadius: 16 }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 4 }}>
                    <span className="font-display" style={{ fontSize: 13, fontWeight: 700, color: '#3D4852' }}>{item.page}</span>
                    <code style={{ fontSize: 10, color: '#6C63FF' }}>{item.path}</code>
                  </div>
                  <div style={{ fontSize: 12, color: '#6B7280', lineHeight: 1.6 }}>{item.desc}</div>
                </div>
              ))}
            </div>
          </section>

          {/* ── API Endpoints ── */}
          <section style={neuCard}>
            <SectionLabel>Key API Endpoints</SectionLabel>
            <p style={{ ...bodyStyle, marginBottom: 16 }}>
              The backend at <code style={{ color: '#6C63FF', fontSize: 13 }}>http://localhost:8000</code> exposes a REST API with ~58 endpoints.
            </p>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 14 }}>
              {[
                { group: 'Core Pipeline', endpoints: ['GET /api/status', 'GET /api/clusters', 'GET /api/report', 'POST /api/analyse', 'POST /api/apply-report'] },
                { group: 'Routing', endpoints: ['GET /api/routing/stats', 'GET /api/routing/simulate', 'POST /api/routing/rollback', 'GET /api/gateway/activity'] },
                { group: 'Fine-tuning', endpoints: ['GET /api/finetune/jobs', 'POST /api/finetune/start', 'POST /api/finetune/jobs/:id/deploy', 'POST /api/finetune/register'] },
                { group: 'Auth & Teams', endpoints: ['POST /api/public/session/login', 'GET /api/public/teams', 'POST /api/public/teams/:id/invite', 'GET /api/public/projects'] },
              ].map(g => (
                <div key={g.group} style={{ ...neuInset, padding: 16, borderRadius: 16 }}>
                  <div className="font-display" style={{ fontSize: 13, fontWeight: 700, color: '#3D4852', marginBottom: 8 }}>{g.group}</div>
                  {g.endpoints.map(ep => (
                    <div key={ep} style={{ fontSize: 12, fontFamily: 'ui-monospace, SFMono-Regular, Menlo, monospace', color: '#6B7280', lineHeight: 1.8 }}>
                      {ep}
                    </div>
                  ))}
                </div>
              ))}
            </div>
          </section>

          {/* ── Docker Deployment ── */}
          <section style={neuCard}>
            <SectionLabel>Docker Deployment</SectionLabel>
            <p style={{ ...bodyStyle, marginBottom: 16 }}>
              AgentShrink ships with a multi-stage Dockerfile and docker-compose.yml for production deployment.
            </p>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 14 }}>
              <div>
                <div style={stepBadge}>Build & Run</div>
                <DocCode>{`# Copy environment configuration
cp .env.example .env
# Edit .env with your API keys

# Build and start all services
docker-compose up -d --build

# Services:
#   gateway  → :8100 (OpenAI-compatible proxy)
#   backend  → :8000 (REST API + WebSocket)
#   frontend → :3000 (Next.js dashboard)`}</DocCode>
              </div>
              <div>
                <div style={stepBadge}>Environment Variables</div>
                <DocCode>{`# Required for LLM routing
OPENAI_API_KEY=sk-...

# Optional provider keys
NVIDIA_API_KEY=nvapi-...
HF_TOKEN=hf_...

# Data persistence
AGENTSHRINK_DB_PATH=/data/agentshrink.db
AGENTSHRINK_OUTPUT_DIR=/data/output`}</DocCode>
              </div>
            </div>
          </section>

          {/* ── Architecture ── */}
          <section style={neuCard}>
            <SectionLabel>Architecture Overview</SectionLabel>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 14 }}>
              {[
                { title: 'Gateway (Port 8100)', desc: 'FastAPI OpenAI-compatible proxy. Intercepts chat completions (streaming + non-streaming), logs to SQLite, routes to local SLMs or upstream API based on centroid similarity.' },
                { title: 'Backend (Port 8000)', desc: 'FastAPI REST API + WebSocket. Serves the dashboard, runs analysis pipeline, manages fine-tune jobs, handles auth/teams/projects, and provides routing audit logs.' },
                { title: 'Frontend (Port 3000)', desc: 'Next.js 14 App Router with React 18 + TypeScript. Neumorphic Soft UI design system with 15+ pages covering the full pipeline lifecycle.' },
              ].map(item => (
                <div key={item.title} style={neuCardSm}>
                  <div className="font-display" style={{ fontSize: 14, fontWeight: 700, color: '#3D4852', marginBottom: 6 }}>{item.title}</div>
                  <div style={{ fontSize: 13, color: '#6B7280', lineHeight: 1.7 }}>{item.desc}</div>
                </div>
              ))}
            </div>
          </section>

          {/* ── Supported Providers ── */}
          <section style={neuCard}>
            <SectionLabel>Supported Upstream Providers</SectionLabel>
            <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap' }}>
              {[
                { name: 'OpenAI', detail: 'GPT-4o, GPT-4o-mini, etc.' },
                { name: 'Ollama', detail: 'Llama 3, Mistral, Phi-3, Gemma, etc.' },
                { name: 'NVIDIA NIM', detail: 'Via Nebius/NIM endpoints' },
                { name: 'HuggingFace', detail: 'Inference API + gated models' },
                { name: 'Custom BYOK', detail: 'Any OpenAI-compatible API' },
              ].map(p => (
                <div key={p.name} style={{ ...neuInset, padding: '12px 18px', borderRadius: 16 }}>
                  <div className="font-display" style={{ fontSize: 13, fontWeight: 700, color: '#3D4852' }}>{p.name}</div>
                  <div style={{ fontSize: 11, color: '#9CA3AF' }}>{p.detail}</div>
                </div>
              ))}
            </div>
          </section>

          {/* ── Get started CTA ── */}
          <section style={{ ...neuCard, padding: 32, textAlign: 'center' as const }}>
            <h2 className="font-display" style={{ fontSize: 22, fontWeight: 800, color: '#3D4852', margin: '0 0 10px', letterSpacing: '-0.02em' }}>
              Ready to Start?
            </h2>
            <p style={{ fontSize: 14, color: '#6B7280', maxWidth: 460, margin: '0 auto 18px' }}>
              Create your first project, connect your agent, and see the savings within minutes.
            </p>
            <div style={{ display: 'flex', gap: 12, justifyContent: 'center', flexWrap: 'wrap' }}>
              <Link href="/auth" style={primaryCtaStyle}>Sign In</Link>
              <Link href="/projects" style={secondaryCtaStyle}>Create Project</Link>
              <Link href="/welcome" style={secondaryCtaStyle}>Open Dashboard</Link>
            </div>
          </section>
        </div>

        {/* ── Footer ── */}
        <footer style={{ textAlign: 'center', padding: '20px 0 8px', fontSize: 12, color: '#9CA3AF' }}>
          AgentShrink Docs · Based on{' '}
          <a href="https://arxiv.org/abs/2506.02153" target="_blank" rel="noopener noreferrer" style={{ color: '#6C63FF', textDecoration: 'none' }}>
            arXiv:2506.02153
          </a>{' '}
          · NVIDIA Research
        </footer>
      </div>
    </div>
  )
}

const bodyStyle = {
  fontSize: 14,
  color: '#6B7280',
  lineHeight: 1.8,
} as const

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

const stepBadge = {
  display: 'inline-block',
  fontSize: 11,
  fontWeight: 700,
  color: '#6C63FF',
  background: 'rgba(108,99,255,0.1)',
  padding: '3px 12px',
  borderRadius: 9999,
  marginBottom: 8,
  letterSpacing: '0.04em',
  textTransform: 'uppercase' as const,
  boxShadow: '3px 3px 6px rgb(163,177,198,0.4), -3px -3px 6px rgba(255,255,255,0.4)',
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

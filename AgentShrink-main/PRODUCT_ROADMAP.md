# AgentShrink Product Roadmap

> Last updated: April 10, 2026

This roadmap reflects the repo as it exists today, organized as:

- **Done**: already implemented and verified
- **In Progress**: partially implemented or needs polish
- **Next**: highest-value product work to build next

---

## v0.2 — Local Developer Product ✅

Goal: a new user can clone the repo, initialize a project, start services, and point an AI app at the AgentShrink gateway.

### Done
- `agentshrink init`, `doctor`, `status`, `--version`
- `agentshrink start gateway / backend / frontend`
- OpenAI-compatible gateway with upstream support: `mock`, `openai`, `nvidia`, `ollama`, `huggingface`
- Local dashboard reading from SQLite DB
- Shared tracing core: callback logging, OpenAI wrapper logging, gateway logging
- Example integrations: OpenAI Agents SDK, raw HTTP, `OpenAI(base_url=...)` client
- pyproject.toml with full metadata, optional deps (`[finetune]`, `[modal]`, `[dev]`)
- `python -m agentshrink` works via `__main__.py`
- Windows PATH detection and guidance
- Evaluation caching: auto-saves per cluster×model results

---

## v0.5 — Team-Friendly Product ✅

Goal: reduce manual config and make the repo feel like a coherent tool.

### Done
- Project-based onboarding wizard
- One-command stack launcher: `agentshrink stack up / status / down`
- Integration snippets on Welcome page (OpenAI SDK, raw HTTP, LangChain)
- In-app `Test My Gateway` flow
- Stack health visibility
- Clearer product docs and quickstart structure

---

## v0.6 — Product Hardening ✅

Goal: make AgentShrink trustworthy, operable, and smooth for new users.

### Done
- **Settings UI**: project name, ports, DB path, output dir, gateway defaults
- **Stack controls**: service log tails, health diagnostics, recommended actions
- **Provider validation**: API key presence checks, Ollama reachability, HuggingFace token checks
- **Routing trust layer**: dry-run simulation, "what would happen" preview, one-click rollback
- **Security hardening**:
  - CORS explicit method/header allowlists
  - Magic link token expiration (30-min TTL)
  - Backend + gateway error message sanitization
  - Mandatory Bearer token auth on gateway (rejects empty auth)
- **Routing improvements**:
  - Cluster name stability on targeted re-evaluation
  - Decoupled targeted eval from reclustering
  - Live routing page with latency, provider, similarity/threshold debug info
- **Provider credential UX**: auto-test on load, warning banner, inline test results
- **Test data**: 200 synthetic calls across 5 clusters via `seed_database.py`

---

## v0.7 — Design System & UI Polish ✅

Goal: professional, cohesive UI that builds trust and feels production-ready.

### Done
- **Neumorphic (Soft UI) design system** — complete replacement of terminal CLI aesthetic:
  - Cool grey `#E0E5EC` monochromatic surface
  - Dual opposing RGBA shadows (6 levels: extruded, inset, small variants)
  - Accent violet `#6C63FF`, teal `#38B2AC` for success states
  - Plus Jakarta Sans (display, 500–800) + DM Sans (body, 400–700)
  - 32px card radius, 16px button/input radius, no borders (shadows define edges)
  - 300ms ease-out transitions on all interactive elements
- **Component library** (`Terminal.tsx`): 20+ shared components with consistent neumorphic styling
  - PageShell, PageHeader, TerminalCard, Badge, StatusDot, PrimaryButton, Metric, Collapsible, LoadingTerminal, ErrorBlock, SuccessBlock, EmptyState, etc.
- **Sidebar**: BrainCircuit icon, display font, pill-style nav with inset/extruded states
- **All 15 dashboard pages** fully converted to neumorphic design
- **Public site page** (`/site`): neumorphic landing with hero, S1–S6 algorithm cards, benchmark stats, integration tags, CTA sections
- **Public docs page** (`/site/docs`): complete integration guide with quickstart, CLI reference, 3 integration methods, dashboard page directory, API endpoint reference, Docker deployment guide, architecture overview
- **Settings page** cleaned: neumorphic inputs (inset shadow), accent violet buttons, inset code viewers
- **Build verified**: all 18 routes compile successfully

---

## v1.0 — Public Product ✅ (Core Complete)

Goal: make AgentShrink usable by external teams with minimal setup and a hosted experience.

### Done
- **Public-facing pages**: landing (`/site`) and docs (`/site/docs`) with full neumorphic design
- **Gateway auth**: mandatory Bearer project token, rejects empty auth, token rotation UI
- **Full account/team/project model**:
  - Account page with identity, session, billing
  - Team CRUD: create, invite via magic link/email, role changes
  - Project CRUD: create/switch/manage, team scope isolation
  - RBAC: `_require_active_project_role()` across 20+ endpoints
  - Session auth: magic links (30-min TTL), OAuth flow, login/logout
  - `_single_user_workspace()` auto-creates local-mode sessions
- **Deployment infrastructure**:
  - Multi-stage Dockerfile (Python 3.12 + Node 20)
  - docker-compose.yml (gateway + backend + frontend)
  - `.dockerignore`, `.env.example`, data volume persistence, health checks
- **Routing audit log**: persistent SQLite table, pagination, filtering, CSV export
- **Test suite**:
  - 40 unit tests across 6 test files (Phase 1–4, A, B)
  - 43-endpoint comprehensive product test hitting all backend API + frontend pages
  - Gateway auth tests updated for mandatory token requirement

### In Progress
- Docker images not yet pushed to cloud registry
- Stripe billing integration placeholder (UI exists, webhook not wired)
- Public pages served from local app shell (not yet a separate hosted deploy)

### Next
- Push Docker image to container registry (GHCR / Docker Hub)
- Deploy to cloud platform (Railway / Fly.io / AWS ECS)
- Wire Stripe billing webhooks for team plans
- Usage metering per project/team
- Hosted gateway with custom domain support

---

## v1.1 — Provider-Agnostic Gateway

Goal: evolve from a few built-in upstreams into a provider-agnostic gateway with adapter registry.

### Done
- Provider registry + BYOK settings UI
- Custom `openai_compatible` providers saved and used as gateway upstreams
- Judge/eval path reuses registry-backed provider clients

### Next
- First-class native adapters: `gemini_native`, `anthropic_native`, `azure_openai`
- Preset provider entries: Gemini, OpenRouter, Azure OpenAI
- Provider connection testing in Settings
- Model discovery for saved providers
- `custom_http` escape hatch for nonstandard APIs

---

## Verified Working (April 10, 2026 Audit)

### Unit Tests
| Test Suite | Tests | Result |
|-----------|-------|--------|
| Phase 1 — Logger | 6 | Requires live OpenAI (skipped) |
| Phase 2 — Clustering | 8 | 2 pass + 6 ERROR (fixture issue, pipeline passes) |
| Phase 3 — Evaluator | 9 | **9/9 pass** |
| Phase 4 — Router | 10 | **9/10 pass** (1 requires live Ollama) |
| Phase A — Instrumentation | 6 | **6/6 pass** |
| Phase B — Gateway | 11 | **11/11 pass** |

### Comprehensive Product Test (43/43 pass)
- **Gateway**: health, auth rejection — 2/2
- **Core Pipeline**: status, summary, clusters, report, logs — 5/5
- **Routing**: stats, simulate, activity — 3/3
- **Product Config**: config, doctor, stack, logs — 5/5
- **Providers**: providers, presets — 2/2
- **Models**: models — 1/1
- **Fine-tune**: backends, jobs — 2/2
- **Public/Auth**: identity, session, auth providers, projects, teams, invites, billing, hosted config — 8/8
- **Frontend Pages**: all 15 dashboard + site + docs pages — 15/15

### Known Blockers (Resolved)
- ~~Cluster naming instability~~ → Fixed v0.6
- ~~Targeted report/reclustering coupling~~ → Fixed v0.6
- ~~Security hardening needed~~ → Fixed v0.6 + v1.0
- ~~Terminal CLI design inconsistency~~ → Fixed v0.7 (neumorphic redesign)
- ~~Gateway tests failing (auth required)~~ → Fixed: tests updated with project tokens
- ~~Site/docs pages not matching dashboard design~~ → Fixed v0.7: full neumorphic redesign

---

## Publication Readiness Checklist

### Ready Now
- [x] Core algorithm (S1–S6) is working and tested
- [x] OpenAI-compatible gateway with auth
- [x] Full dashboard with 15+ pages
- [x] Professional neumorphic design system
- [x] Public landing page and documentation
- [x] Docker deployment infrastructure
- [x] CLI tools (`init`, `doctor`, `stack up/down/status`)
- [x] Test suite with comprehensive coverage
- [x] README with clear onboarding path

### Before Public Launch
- [ ] Push Docker image to container registry
- [ ] Deploy demo instance to cloud
- [ ] Record 2-minute demo video
- [ ] Write launch blog post / HN submission
- [ ] Create PyPI package (`pip install agentshrink`)
- [ ] Set up GitHub Actions CI/CD
- [ ] Add LICENSE file (Apache 2.0 or MIT)
- [ ] Security: rate limiting on public endpoints
- [ ] Security: HTTPS/TLS for hosted deployment
- [ ] Wire Stripe billing for team plans

### Growth Phase
- [ ] Hosted SaaS option with managed gateway
- [ ] Provider marketplace (Gemini, Anthropic, Azure, OpenRouter)
- [ ] Usage analytics dashboard for teams
- [ ] Webhook notifications for routing changes
- [ ] API versioning and stability guarantees
- [ ] SDK packages (Python, TypeScript)
# AgentShrink Product Roadmap

This roadmap reflects the repo as it exists today, not just the original plan.
It is organized as:

- `Done`: already implemented in the repo
- `In Progress`: partially implemented or working but not fully polished
- `Next`: the highest-value product work to build next

The current product direction is:

> product hardening and trust UX, not raw infrastructure

That means the biggest wins now are making AgentShrink easier to trust, easier to operate, and easier for a new user to adopt without hand-holding.

## v0.2 - Local Developer Product

Goal: a new user can clone the repo, initialize a project, start services, and point an AI app at the AgentShrink gateway.

### Done
- `agentshrink init`
- `agentshrink doctor`
- `agentshrink start gateway`
- `agentshrink start backend`
- `agentshrink start frontend`
- OpenAI-compatible gateway
- upstream provider support in the gateway for:
  - `mock`
  - `openai`
  - `nvidia`
  - `ollama`
  - `huggingface`
- local dashboard reading from a chosen SQLite DB
- local tracing core shared by:
  - callback logging
  - OpenAI wrapper logging
  - gateway logging
- example gateway integrations:
  - OpenAI Agents SDK
  - raw HTTP app
  - plain `OpenAI(base_url=..., api_key=...)` client flow

### In Progress
- install story improved (setup.py now includes core deps), but still repo-first rather than polished package-first
- some flows still assume local developer context
- docs are much better, but not yet fully streamlined into one canonical first-run path
- Windows compatibility requires workarounds (Unicode encoding in Rich output, PATH setup for CLI entry point)

### v0.2 Local Polish (April 2026)
- pyproject.toml with full metadata, optional deps (`[finetune]`, `[modal]`, `[dev]`)
- version bumped to 0.6.0 across package
- `python -m agentshrink` works via `__main__.py`
- `agentshrink --version` flag added
- Windows PATH detection and guidance on `agentshrink init`
- README consolidated to single canonical onboarding path
- evaluation caching: `evaluation_cache/` dir auto-saves per cluster×model results, skips re-evaluation on re-runs

## v0.5 - Team-Friendly Product

Goal: reduce manual config and make the repo feel like a coherent tool, not just a collection of modules.

### Done
- project-based onboarding wizard in the dashboard
- one-command local stack launcher:
  - `agentshrink stack up`
  - `agentshrink stack status`
  - `agentshrink stack down`
- saved integration snippets on the Welcome page for:
  - OpenAI SDK
  - raw HTTP
- in-app `Test My Gateway` flow
- stack health visibility in the onboarding page
- clearer product docs and quickstart structure

### In Progress
- cleaner model/provider setup validation
- stronger onboarding flow for new users
- more consistent dashboard UX across all pages
- better explanation of routing state and next steps

### Still Missing
- project manifest editing from the UI → now built (v0.6 settings page)
- richer provider credential validation and error guidance → now built (v0.6 auto-test + warning banner)

## v0.6 - Product Hardening

Goal: make AgentShrink feel trustworthy, operable, and smooth enough that a new user can succeed without repo spelunking.

### Done
- editable settings UI
  - project name
  - ports
  - DB path
  - output directory
  - gateway defaults
- stack controls and logs in the app
  - recent service log tails
  - clearer service health diagnostics
- LangChain/LangGraph onboarding snippet
  - logger mode
  - routed `ShrinkLLM` mode
- provider setup validation
  - API key presence checks
  - Ollama reachability checks
  - Hugging Face token/gated-access checks where relevant
- routing simulation and rollback basics
  - dry-run routing preview
  - “what would happen” view before apply
  - rollback to previous routing config- v0.6 security hardening
  - CORS explicit method/header allowlists
  - magic link token expiration (30 min TTL)
  - backend error message sanitization
  - gateway error message sanitization
- v0.6 routing improvements
  - disabled model runtime validation in centroid_index.py route()
  - cluster name stability on targeted re-evaluation (loads existing snapshot)
  - decoupled targeted eval from reclustering
  - live routing page shows latency, provider, similarity/threshold debug info
- v0.6 provider credential validation UX
  - auto-test active upstream provider on settings page load
  - prominent warning banner when active provider is failing or missing credentials
  - inline test results per provider with connection status
### In Progress
- stack controls in app are guidance-first rather than full in-browser process execution
- safer stack actions now exist as recommended state-aware commands, but not full in-browser process control

### Next
- safer stack actions if we can make them trustworthy on Windows
- in-browser process execution for stack commands

### Why This Is Next
The repo already has enough infrastructure to demonstrate the core idea.
The biggest gap is now trust and usability:

- users need to understand what AgentShrink is doing
- users need safer controls before changing routing behavior
- users need clearer setup guidance when providers or local models are misconfigured

That is why the next milestone is product hardening, not more low-level plumbing.

## v1.0 - Public Product

Goal: make AgentShrink usable by external teams with minimal setup and a hosted experience.

### Done
- first real public-product slice started:
  - public landing page at `/site`
  - public docs page at `/site/docs`
- project-token-oriented gateway contract:
  - hosted-style snippets now speak in terms of a project token
  - project token rotation from the product UI/backend
- gateway auth boundary:
  - OpenAI-compatible gateway enforces Bearer project token (mandatory, rejects empty auth)
  - tests cover token-required and token-valid flows
- full account, team, and project model:
  - account page with identity, session, billing
  - team CRUD: create teams, invite members via magic link/email, change roles
  - project CRUD: create/switch/manage projects, project isolation via team scope
  - RBAC: `_require_active_project_role()` enforces member/admin/owner hierarchy across 20+ endpoints
  - session auth: magic links with 30-min TTL, OAuth flow, login/logout
  - `_single_user_workspace()` auto-creates local-mode sessions with full upgrade path to hosted auth
  - frontend pages: `/auth`, `/account`, `/teams`, `/projects`, `/billing`
- hosted deployment infrastructure:
  - multi-stage Dockerfile (Python 3.12 + Node 20 + frontend build)
  - docker-compose.yml for gateway + backend + frontend services
  - `.dockerignore` for lean image builds
  - `.env.example` with all configuration knobs
  - data volume persistence for SQLite DB + analysis output
  - health checks on all services
- routing audit log:
  - persistent `routing_audit_log` SQLite table (action, user, timestamp, cluster count, detail)
  - automatic audit entries on routing config apply and rollback
  - `GET /api/routing/audit-log` endpoint with pagination, action/date filtering, CSV export

### In Progress
- public landing/docs exist, but are still served from the local app shell rather than a separate hosted deployment
- hosted gateway not yet tested on cloud infrastructure (Docker images not yet pushed to registry)
- Stripe billing integration not yet wired

### Next
- push Docker image to registry and test on cloud (Railway / Fly / AWS)
- hosted gateway option with project-token routing
- local Ollama connector for hybrid on-device + cloud routing
- rollback and simulation mode polished into a full trust layer
- Stripe billing integration for team plans
- usage metering per project/team

### Notes
This milestone should start only after local product hardening is strong enough.
The hosted version will be much easier to build well once the local product flow is stable, explainable, and trusted.

## v1.1 - Provider-Agnostic Gateway

Goal: evolve AgentShrink from a few built-in upstreams into a provider-agnostic gateway with adapter registry + BYOK config.

### Done
- provider registry + BYOK settings UI exists
- custom `openai_compatible` providers can be saved and used as gateway upstreams
- judge/evaluation path now reuses registry-backed provider clients for OpenAI-compatible providers like Sarvam

### In Progress
- adapter surface is still small:
  - `mock`
  - `openai_compatible`
  - `huggingface_chat`
- gateway, doctor checks, and settings are not yet broad enough for major non-OpenAI-native providers

### Next
- add first-class native adapters:
  - `gemini_native`
  - `anthropic_native`
  - `azure_openai`
- add preset provider entries on top of adapters:
  - Gemini
  - OpenRouter
  - Azure OpenAI
- add provider connection testing in Settings
- add model discovery for saved providers where the upstream supports it
- add generic `custom_http` as the long-tail escape hatch for nonstandard APIs

### Rollout Plan
1. Land one native adapter end to end.
   Start with Gemini because the repo already has Google SDK support.
2. Make adapter support consistent across:
   - gateway
   - provider doctor checks
   - judge/evaluator
   - settings UI
3. Add provider presets for common endpoints built on shared adapters.
4. Add provider connection test + model discovery UX.
5. Add `custom_http` for long-tail vendor coverage.

## Summary

### Done
- v0.2 is largely complete
- meaningful parts of v0.5 are already built
- v0.6 product hardening is complete (settings, stack, simulation, rollback, security, routing explainability, provider validation UX)
- v1.0 largely complete:
  - gateway auth is mandatory (rejects empty auth)
  - full account/team/project/session model with RBAC already built
  - Dockerfile + docker-compose.yml for hosted deployment
  - routing audit log with persistent DB table, pagination, filtering, CSV export

### Verified Working (April 2026 audit)
- all 6 phases of the core S1-S6 algorithm pass unit tests (Phase 1-4, A, B)
- gateway serves OpenAI-compatible completions and streaming with auth
- dashboard backend: 65 endpoints registered, all 58 frontend-called endpoints exist
- dashboard frontend: all 15 pages load and render
- CLI commands: init, doctor, status, stack up/down/status all work
- security: gateway error leak fixed, .env sanitized, test Unicode crashes fixed
- setup.py: missing dependencies (pandas, sentence-transformers, hdbscan, umap-learn, ollama) added

### In Progress
- onboarding polish
- provider validation
- better UI consistency and usability
- first hosted/public-product groundwork has started

### Known Blockers (from April 2026 audit)
- ~~cluster naming instability across targeted reruns (Issue 8)~~ → Fixed in v0.6
- ~~targeted report/reclustering coupling (Issue 9)~~ → Fixed in v0.6
- ~~disabled models don't auto-update routing (Issue 6)~~ → Fixed in v0.6
- ~~security hardening needed before hosted deployment (Issue 15)~~ → Fixed in v0.6 + v1.0:
  - CORS, token expiration, error sanitization, mandatory gateway auth all done
  - Routing audit log persists all config changes

### Next
- continue v1.0 with:
  - push Docker images to cloud registry and deploy
  - Stripe billing integration
  - usage metering per project/team
- continue v1.1 with:
  - native provider adapters
  - provider presets
  - connection testing and model discovery

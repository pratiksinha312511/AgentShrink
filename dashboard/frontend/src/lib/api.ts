const API = process.env.NEXT_PUBLIC_API_BASE_URL || 'http://localhost:8000'
const WS_API = API.replace(/^http:/, 'ws:').replace(/^https:/, 'wss:')

async function readJsonOrThrow(r: Response, fallback: string) {
  let data: any = null
  try {
    data = await r.json()
  } catch {}
  if (!r.ok) throw new Error(data?.detail || data?.message || fallback)
  return data
}

export async function fetchStatus() {
  const r = await fetch(`${API}/api/status`, { cache: 'no-store' })
  return readJsonOrThrow(r, 'Failed to fetch status')
}

export async function fetchDashboardSummary() {
  const r = await fetch(`${API}/api/dashboard/summary`, { cache: 'no-store' })
  return readJsonOrThrow(r, 'Failed to fetch dashboard summary')
}

export async function fetchClusters() {
  const r = await fetch(`${API}/api/clusters`, { cache: 'no-store' })
  return readJsonOrThrow(r, 'No cluster data - run agentshrink analyse')
}

export async function fetchReport(clusterId?: number) {
  const suffix = typeof clusterId === 'number' ? `?cluster_id=${clusterId}` : ''
  const r = await fetch(`${API}/api/report${suffix}`, { cache: 'no-store' })
  return readJsonOrThrow(r, 'No report - run agentshrink analyse')
}

export async function fetchAnalysisLogs() {
  const r = await fetch(`${API}/api/analysis/logs`, { cache: 'no-store' })
  return readJsonOrThrow(r, 'Failed to fetch analysis logs')
}

export async function fetchRoutingStats() {
  const r = await fetch(`${API}/api/routing/stats`, { cache: 'no-store' })
  return readJsonOrThrow(r, 'Failed to fetch routing stats')
}

export async function fetchGatewayActivity(limit = 50) {
  const r = await fetch(`${API}/api/gateway/activity?limit=${limit}`, { cache: 'no-store' })
  return readJsonOrThrow(r, 'Failed to fetch gateway activity')
}

export async function fetchProductConfig() {
  const r = await fetch(`${API}/api/product/config`, { cache: 'no-store' })
  return readJsonOrThrow(r, 'Failed to fetch product config')
}

export async function fetchProductProviders() {
  const r = await fetch(`${API}/api/product/providers`, { cache: 'no-store' })
  return readJsonOrThrow(r, 'Failed to fetch provider registry')
}

export async function fetchProductProviderPresets() {
  const r = await fetch(`${API}/api/product/provider-presets`, { cache: 'no-store' })
  return readJsonOrThrow(r, 'Failed to fetch provider presets')
}

export async function saveProductProvider(provider: any) {
  const r = await fetch(`${API}/api/product/providers`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(provider),
  })
  return readJsonOrThrow(r, 'Failed to save provider config')
}

export async function deleteProductProvider(providerId: string) {
  const r = await fetch(`${API}/api/product/providers/${encodeURIComponent(providerId)}`, {
    method: 'DELETE',
  })
  return readJsonOrThrow(r, 'Failed to delete provider config')
}

export async function testProductProvider(providerId: string) {
  const r = await fetch(`${API}/api/product/providers/${encodeURIComponent(providerId)}/test`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
  })
  return readJsonOrThrow(r, 'Failed to test provider connection')
}

export async function fetchProductProviderModels(providerId: string) {
  const r = await fetch(`${API}/api/product/providers/${encodeURIComponent(providerId)}/models`, { cache: 'no-store' })
  return readJsonOrThrow(r, 'Failed to discover provider models')
}

export async function fetchPublicIdentity() {
  const r = await fetch(`${API}/api/public/identity`, { cache: 'no-store' })
  return readJsonOrThrow(r, 'Failed to fetch public identity')
}

export async function fetchPublicSession() {
  const r = await fetch(`${API}/api/public/session`, { cache: 'no-store' })
  return readJsonOrThrow(r, 'Failed to fetch public session')
}

export async function fetchPublicInvites() {
  const r = await fetch(`${API}/api/public/invites`, { cache: 'no-store' })
  return readJsonOrThrow(r, 'Failed to fetch invites')
}

export async function loginPublicSession(payload: { user_name: string; user_email: string }) {
  const r = await fetch(`${API}/api/public/session/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  return readJsonOrThrow(r, 'Failed to create session')
}

export async function requestPublicMagicLink(payload: { user_email: string; user_name?: string }) {
  const r = await fetch(`${API}/api/public/session/magic-link/request`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  return readJsonOrThrow(r, 'Failed to request magic link')
}

export async function consumePublicMagicLink(payload: { token: string }) {
  const r = await fetch(`${API}/api/public/session/magic-link/consume`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  return readJsonOrThrow(r, 'Failed to consume magic link')
}

export async function fetchPublicAuthProviders() {
  const r = await fetch(`${API}/api/public/auth/providers`, { cache: 'no-store' })
  return readJsonOrThrow(r, 'Failed to fetch auth providers')
}

export async function startPublicExternalAuth(payload: { redirect_uri?: string } = {}) {
  const r = await fetch(`${API}/api/public/auth/start`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  return readJsonOrThrow(r, 'Failed to start external auth')
}

export async function completePublicExternalAuth(payload: { code: string; redirect_uri?: string }) {
  const r = await fetch(`${API}/api/public/auth/callback`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  return readJsonOrThrow(r, 'Failed to complete external auth')
}

export async function logoutPublicSession() {
  const r = await fetch(`${API}/api/public/session/logout`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
  })
  return readJsonOrThrow(r, 'Failed to clear session')
}

export async function acceptPublicInvite(token: string, payload: { user_name?: string; user_email?: string } = {}) {
  const r = await fetch(`${API}/api/public/invites/${encodeURIComponent(token)}/accept`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  return readJsonOrThrow(r, 'Failed to accept invite')
}

export async function fetchPublicProjects() {
  const r = await fetch(`${API}/api/public/projects`, { cache: 'no-store' })
  return readJsonOrThrow(r, 'Failed to fetch public projects')
}

export async function fetchPublicTeams() {
  const r = await fetch(`${API}/api/public/teams`, { cache: 'no-store' })
  return readJsonOrThrow(r, 'Failed to fetch public teams')
}

export async function createPublicTeam(payload: { name: string; slug?: string }) {
  const r = await fetch(`${API}/api/public/teams`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  return readJsonOrThrow(r, 'Failed to create team')
}

export async function invitePublicTeamMember(teamId: string, payload: { user_name: string; user_email: string; role?: string }) {
  const r = await fetch(`${API}/api/public/teams/${encodeURIComponent(teamId)}/invite`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  return readJsonOrThrow(r, 'Failed to invite team member')
}

export async function updatePublicTeamMemberRole(teamId: string, userEmail: string, payload: { role: string }) {
  const r = await fetch(`${API}/api/public/teams/${encodeURIComponent(teamId)}/members/${encodeURIComponent(userEmail)}/role`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  return readJsonOrThrow(r, 'Failed to update team role')
}

export async function createPublicProject(payload: { name: string; environment?: string; upstream_provider?: string }) {
  const r = await fetch(`${API}/api/public/projects`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  return readJsonOrThrow(r, 'Failed to create project')
}

export async function activatePublicProject(projectId: string) {
  const r = await fetch(`${API}/api/public/projects/${encodeURIComponent(projectId)}/activate`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
  })
  return readJsonOrThrow(r, 'Failed to switch project')
}

export async function fetchPublicProjectActivity(projectId: string, limit = 20) {
  const r = await fetch(`${API}/api/public/projects/${encodeURIComponent(projectId)}/activity?limit=${limit}`, { cache: 'no-store' })
  return readJsonOrThrow(r, 'Failed to fetch project activity')
}

export async function fetchPublicProjectRouting(projectId: string, limit = 50) {
  const r = await fetch(`${API}/api/public/projects/${encodeURIComponent(projectId)}/routing?limit=${limit}`, { cache: 'no-store' })
  return readJsonOrThrow(r, 'Failed to fetch project routing')
}

export async function fetchPublicProjectReport(projectId: string) {
  const r = await fetch(`${API}/api/public/projects/${encodeURIComponent(projectId)}/report`, { cache: 'no-store' })
  return readJsonOrThrow(r, 'Failed to fetch project report')
}

export async function fetchPublicProjectSummary(projectId: string) {
  const r = await fetch(`${API}/api/public/projects/${encodeURIComponent(projectId)}/summary`, { cache: 'no-store' })
  return readJsonOrThrow(r, 'Failed to fetch project summary')
}

export async function fetchPublicProjectClusters(projectId: string) {
  const r = await fetch(`${API}/api/public/projects/${encodeURIComponent(projectId)}/clusters`, { cache: 'no-store' })
  return readJsonOrThrow(r, 'Failed to fetch project clusters')
}

export async function fetchHostedConfig() {
  const r = await fetch(`${API}/api/public/hosted/config`, { cache: 'no-store' })
  return readJsonOrThrow(r, 'Failed to fetch hosted config')
}

export async function saveHostedConfig(config: any) {
  const r = await fetch(`${API}/api/public/hosted/config`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ config }),
  })
  return readJsonOrThrow(r, 'Failed to save hosted config')
}

export async function fetchPublicBilling() {
  const r = await fetch(`${API}/api/public/billing`, { cache: 'no-store' })
  return readJsonOrThrow(r, 'Failed to fetch billing')
}

export async function createPublicBillingCheckout(payload: { return_url?: string } = {}) {
  const r = await fetch(`${API}/api/public/billing/checkout`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  return readJsonOrThrow(r, 'Failed to create billing checkout')
}

export async function saveProductConfig(config: any) {
  const r = await fetch(`${API}/api/product/config`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(config),
  })
  return readJsonOrThrow(r, 'Failed to save product config')
}

export async function rotateProductToken() {
  const r = await fetch(`${API}/api/product/token/rotate`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
  })
  return readJsonOrThrow(r, 'Failed to rotate project token')
}

export async function fetchProductDoctor() {
  const r = await fetch(`${API}/api/product/doctor`, { cache: 'no-store' })
  return readJsonOrThrow(r, 'Failed to fetch product doctor')
}

export async function fetchProductStack() {
  const r = await fetch(`${API}/api/product/stack`, { cache: 'no-store' })
  return readJsonOrThrow(r, 'Failed to fetch product stack')
}

export async function fetchProductLogs(service: string, stream: 'stdout' | 'stderr' = 'stdout', lines = 80) {
  const r = await fetch(`${API}/api/product/logs?service=${encodeURIComponent(service)}&stream=${stream}&lines=${lines}`, { cache: 'no-store' })
  return readJsonOrThrow(r, 'Failed to fetch product logs')
}

export async function testProductGateway() {
  const r = await fetch(`${API}/api/product/test-gateway`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
  })
  return readJsonOrThrow(r, 'Failed to test gateway')
}

export async function fetchConfig() {
  const r = await fetch(`${API}/api/config`, { cache: 'no-store' })
  return readJsonOrThrow(r, 'Failed to fetch config')
}

export async function fetchModels() {
  const r = await fetch(`${API}/api/models`, { cache: 'no-store' })
  return readJsonOrThrow(r, 'Failed to fetch models')
}

export async function saveModel(model: any) {
  const r = await fetch(`${API}/api/models`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(model),
  })
  return readJsonOrThrow(r, 'Failed to save model')
}

export async function deleteModel(modelId: string) {
  const r = await fetch(`${API}/api/models/${modelId}`, {
    method: 'DELETE',
  })
  return readJsonOrThrow(r, 'Failed to delete model')
}

export async function saveJudgeModel(modelId: string | null) {
  const r = await fetch(`${API}/api/models/judge`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ model_id: modelId }),
  })
  return readJsonOrThrow(r, 'Failed to save judge model')
}

export async function applyReport() {
  const r = await fetch(`${API}/api/apply-report`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
  })
  return readJsonOrThrow(r, 'Failed to apply report')
}

export async function fetchRoutingSimulation() {
  const r = await fetch(`${API}/api/routing/simulate`, { cache: 'no-store' })
  return readJsonOrThrow(r, 'Failed to fetch routing simulation')
}

export async function rollbackRoutingConfig() {
  const r = await fetch(`${API}/api/routing/rollback`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
  })
  return readJsonOrThrow(r, 'Failed to rollback routing config')
}

export async function fetchFineTunePreview(clusterId: number, limit = 5) {
  const r = await fetch(`${API}/api/finetune/preview/${clusterId}?limit=${limit}`, { cache: 'no-store' })
  return readJsonOrThrow(r, 'Failed to fetch fine-tune preview')
}

export async function exportFineTuneData(clusterId: number) {
  const r = await fetch(`${API}/api/finetune/export`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ cluster_id: clusterId }),
  })
  return readJsonOrThrow(r, 'Failed to export fine-tune data')
}

export async function fetchFineTuneBackends() {
  const r = await fetch(`${API}/api/finetune/backends`, { cache: 'no-store' })
  return readJsonOrThrow(r, 'Failed to fetch fine-tune backends')
}

export async function fetchFineTuneJobs() {
  const r = await fetch(`${API}/api/finetune/jobs`, { cache: 'no-store' })
  return readJsonOrThrow(r, 'Failed to fetch fine-tune jobs')
}

export async function fetchFineTuneJob(jobId: string) {
  const r = await fetch(`${API}/api/finetune/jobs/${jobId}`, { cache: 'no-store' })
  return readJsonOrThrow(r, 'Failed to fetch fine-tune job')
}

export async function startFineTuneJob(payload: {
  cluster_id: number
  backend: string
  config?: Record<string, any>
  hf_token?: string
}) {
  const r = await fetch(`${API}/api/finetune/start`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  return readJsonOrThrow(r, 'Failed to start fine-tune job')
}

export async function stopFineTuneJob(jobId: string) {
  const r = await fetch(`${API}/api/finetune/jobs/${jobId}/stop`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
  })
  return readJsonOrThrow(r, 'Failed to stop fine-tune job')
}

export async function deployFineTuneJob(jobId: string) {
  const r = await fetch(`${API}/api/finetune/jobs/${jobId}/deploy`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
  })
  return readJsonOrThrow(r, 'Failed to deploy fine-tuned model')
}

export async function registerFineTunedModel(clusterId: number, ollamaName: string, displayName: string) {
  const r = await fetch(`${API}/api/finetune/register`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      cluster_id: clusterId,
      ollama_name: ollamaName,
      display_name: displayName,
    }),
  })
  return readJsonOrThrow(r, 'Failed to register fine-tuned model')
}

export async function fetchOllamaModels() {
  const r = await fetch(`${API}/api/ollama/models`, { cache: 'no-store' })
  return readJsonOrThrow(r, 'Failed to fetch Ollama models')
}

export async function triggerAnalyse(opts: {
  min_cluster_size?: number
  skip_eval?: boolean
  no_llm_labels?: boolean
  cluster_ids?: number[]
}) {
  const r = await fetch(`${API}/api/analyse`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(opts),
  })
  return r.json()
}

export function createRoutingWebSocket(
  onMessage: (data: any) => void,
  onClose?: () => void
): WebSocket {
  const ws = new WebSocket(`${WS_API}/ws/routing-trace`)
  ws.onmessage = e => {
    try { onMessage(JSON.parse(e.data)) }
    catch {}
  }
  ws.onclose = onClose || (() => {})
  return ws
}

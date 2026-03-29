const API = 'http://localhost:8000'

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
  const ws = new WebSocket(`ws://localhost:8000/ws/routing-trace`)
  ws.onmessage = e => {
    try { onMessage(JSON.parse(e.data)) }
    catch {}
  }
  ws.onclose = onClose || (() => {})
  return ws
}

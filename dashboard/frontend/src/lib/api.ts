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

export async function fetchReport() {
  const r = await fetch(`${API}/api/report`, { cache: 'no-store' })
  return readJsonOrThrow(r, 'No report - run agentshrink analyse')
}

export async function fetchRoutingStats() {
  const r = await fetch(`${API}/api/routing/stats`, { cache: 'no-store' })
  return readJsonOrThrow(r, 'Failed to fetch routing stats')
}

export async function fetchConfig() {
  const r = await fetch(`${API}/api/config`, { cache: 'no-store' })
  return readJsonOrThrow(r, 'Failed to fetch config')
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

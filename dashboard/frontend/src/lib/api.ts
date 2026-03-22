const API = 'http://localhost:8000'

export async function fetchStatus() {
  const r = await fetch(`${API}/api/status`, { cache: 'no-store' })
  if (!r.ok) throw new Error('Failed to fetch status')
  return r.json()
}

export async function fetchClusters() {
  const r = await fetch(`${API}/api/clusters`, { cache: 'no-store' })
  if (!r.ok) throw new Error('No cluster data — run agentshrink analyse')
  return r.json()
}

export async function fetchReport() {
  const r = await fetch(`${API}/api/report`, { cache: 'no-store' })
  if (!r.ok) throw new Error('No report — run agentshrink analyse')
  return r.json()
}

export async function fetchRoutingStats() {
  const r = await fetch(`${API}/api/routing/stats`, { cache: 'no-store' })
  if (!r.ok) throw new Error('Failed to fetch routing stats')
  return r.json()
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

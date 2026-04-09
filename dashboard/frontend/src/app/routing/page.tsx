'use client'
import { useEffect, useRef, useState } from 'react'
import ProjectScopeBar from '@/components/ProjectScopeBar'
import { createRoutingWebSocket, fetchGatewayActivity, fetchPublicProjects, fetchPublicProjectRouting, fetchRoutingStats } from '@/lib/api'

interface RouteEvent {
  cluster_name: string
  model_name: string
  model_display: string
  confidence: number
  is_local: boolean
  nearest_cluster_name?: string
  nearest_similarity?: number
  threshold?: number
  reason?: string
  prompt_preview?: string
  latency_ms?: number
  timestamp: number
}

function ModelBadge({ isLocal, model }: { isLocal: boolean; model: string }) {
  return (
    <span className="badge" style={{
      background: isLocal ? '#EAF3DE' : '#EEEDFE',
      color: isLocal ? '#27500A' : '#3C3489',
      fontFamily: 'monospace',
    }}>
      {model}
    </span>
  )
}

function formatTs(ts: number) {
  return new Date(ts * 1000).toLocaleTimeString('en-US', {
    hour12: false, hour: '2-digit', minute: '2-digit', second: '2-digit'
  })
}

function toEpochSeconds(value: string | number | undefined) {
  if (typeof value === 'number') return value
  if (!value) return Date.now() / 1000
  const parsed = Date.parse(value)
  return Number.isNaN(parsed) ? Date.now() / 1000 : parsed / 1000
}

export default function RoutingPage() {
  const [events, setEvents] = useState<RouteEvent[]>([])
  const [stats, setStats] = useState<any>(null)
  const [connected, setConnected] = useState(false)
  const [totals, setTotals] = useState({ local: 0, api: 0 })
  const [selectedProjectId, setSelectedProjectId] = useState('')
  const [activeProjectId, setActiveProjectId] = useState('')
  const [selectedProjectName, setSelectedProjectName] = useState('AgentShrink Project')
  const [clearedAt, setClearedAt] = useState<number | null>(null)
  const wsRef = useRef<WebSocket | null>(null)
  const bottomRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    fetchPublicProjects().then((data) => {
      const activeId = data.active_project_id || ''
      setSelectedProjectId(activeId)
      setActiveProjectId(activeId)
      const active = (data.projects || []).find((project: any) => project.id === activeId)
      setSelectedProjectName(active?.name || 'AgentShrink Project')
    }).catch(() => {})
  }, [])

  useEffect(() => {
    if (!selectedProjectId) return

    const applyLoadedEvents = (rawEvents: any[]) => {
      let loaded = (rawEvents || []).map((ev: any) => ({ ...ev, timestamp: toEpochSeconds(ev.timestamp) })).reverse()
      if (clearedAt) {
        loaded = loaded.filter((ev: RouteEvent) => ev.timestamp > clearedAt)
      }
      setEvents(loaded)
      setTotals({
        local: loaded.filter((ev: RouteEvent) => ev.is_local).length,
        api: loaded.filter((ev: RouteEvent) => !ev.is_local).length,
      })
    }

    const load = async () => {
      if (selectedProjectId === activeProjectId || !activeProjectId) {
        fetchRoutingStats().then(setStats).catch(() => {})
        fetchGatewayActivity(50).then((data) => {
          applyLoadedEvents(data.events || [])
        }).catch(() => {})
        return
      }

      fetchPublicProjectRouting(selectedProjectId, 50).then((data) => {
        setStats(data.stats)
        setSelectedProjectName(data.project?.name || 'Selected project')
        applyLoadedEvents(data.events || [])
      }).catch(() => {})
    }

    load()

    const poll = setInterval(() => {
      const next = (selectedProjectId !== activeProjectId && activeProjectId)
        ? fetchPublicProjectRouting(selectedProjectId, 50).then((data) => ({ stats: data.stats, events: data.events || [] }))
        : Promise.all([fetchRoutingStats(), fetchGatewayActivity(50)]).then(([statsData, activityData]) => ({ stats: statsData, events: activityData.events || [] }))

      next.then((data: any) => {
        setStats(data.stats)
        let loaded = (data.events || []).map((ev: any) => ({ ...ev, timestamp: toEpochSeconds(ev.timestamp) })).reverse()
        if (clearedAt) {
          loaded = loaded.filter((ev: RouteEvent) => ev.timestamp > clearedAt)
        }
        setEvents(prev => {
          if (loaded.length === 0) return clearedAt ? [] : prev
          const prevKey = prev.map(ev => `${ev.timestamp}-${ev.cluster_name}-${ev.model_name}`).join('|')
          const nextKey = loaded.map((ev: RouteEvent) => `${ev.timestamp}-${ev.cluster_name}-${ev.model_name}`).join('|')
          if (prevKey === nextKey) return prev
          return loaded
        })
        setTotals({
          local: loaded.filter((ev: RouteEvent) => ev.is_local).length,
          api: loaded.filter((ev: RouteEvent) => !ev.is_local).length,
        })
      }).catch(() => {})
    }, 4000)

    if (selectedProjectId !== activeProjectId && activeProjectId) {
      setConnected(false)
      return () => clearInterval(poll)
    }

    const connect = () => {
      const ws = createRoutingWebSocket(
        (data) => {
          if (data.type === 'connected') {
            setConnected(true)
          } else if (data.type === 'routing_decision') {
            const ev: RouteEvent = {
              cluster_name: data.cluster_name ?? 'unknown',
              model_name: data.model_name ?? 'unknown',
              model_display: data.model_display ?? data.model_name ?? 'unknown',
              confidence: data.confidence ?? 0,
              is_local: data.is_local ?? false,
              nearest_cluster_name: data.nearest_cluster_name,
              nearest_similarity: data.nearest_similarity,
              threshold: data.threshold,
              reason: data.reason,
              prompt_preview: data.prompt_preview,
              latency_ms: data.latency_ms,
              timestamp: data.timestamp ?? Date.now() / 1000,
            }
            if (clearedAt && ev.timestamp <= clearedAt) {
              return
            }
            setEvents(prev => [...prev.slice(-199), ev])
            setTotals(prev => ({
              local: prev.local + (ev.is_local ? 1 : 0),
              api: prev.api + (ev.is_local ? 0 : 1),
            }))
          }
        },
        () => {
          setConnected(false)
          setTimeout(connect, 3000)
        }
      )
      wsRef.current = ws
    }

    connect()
    return () => {
      clearInterval(poll)
      wsRef.current?.close()
    }
  }, [selectedProjectId, activeProjectId, clearedAt])

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [events])

  const total = totals.local + totals.api
  const localPct = total > 0 ? Math.round(totals.local / total * 100) : 0
  const viewingSavedProject = Boolean(selectedProjectId && activeProjectId && selectedProjectId !== activeProjectId)

  return (
    <div style={{ maxWidth: 900 }}>
      <ProjectScopeBar selectedProjectId={selectedProjectId} onChange={setSelectedProjectId} />

      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 24 }}>
        <div>
          <h1 style={{ fontSize: 22, fontWeight: 500, color: 'var(--text-primary)', marginBottom: 4 }}>
            Live Routing
          </h1>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 13 }}>
            <span
              className="live-dot"
              style={{
                width: 8, height: 8, borderRadius: '50%',
                background: viewingSavedProject ? '#7F77DD' : connected ? '#1D9E75' : '#D85A30',
                display: 'inline-block',
              }}
            />
            <span style={{ color: viewingSavedProject ? '#7F77DD' : connected ? '#1D9E75' : '#D85A30' }}>
              {viewingSavedProject ? `Viewing saved routing history for ${selectedProjectName}` : connected ? 'Connected — listening for routing events' : 'Reconnecting...'}
            </span>
          </div>
        </div>
        <button
          onClick={() => {
            setClearedAt(Date.now() / 1000)
            setEvents([])
            setTotals({ local: 0, api: 0 })
          }}
          style={{
            background: 'transparent', border: '0.5px solid var(--border)',
            borderRadius: 6, padding: '6px 12px',
            fontSize: 12, color: 'var(--text-secondary)', cursor: 'pointer',
          }}
        >
          Clear
        </button>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr 1fr', gap: 10, marginBottom: 20 }}>
        <div className="metric-card">
          <div className="metric-num">{total}</div>
          <div className="metric-label">Total calls this session</div>
        </div>
        <div className="metric-card">
          <div className="metric-num" style={{ color: '#1D9E75' }}>{totals.local}</div>
          <div className="metric-label">→ Local SLM</div>
        </div>
        <div className="metric-card">
          <div className="metric-num" style={{ color: '#7F77DD' }}>{totals.api}</div>
          <div className="metric-label">→ Remote/API</div>
        </div>
        <div className="metric-card">
          <div className="metric-num" style={{ color: localPct >= 60 ? '#1D9E75' : '#EF9F27' }}>
            {localPct}%
          </div>
          <div className="metric-label">Local routing rate</div>
        </div>
      </div>

      {stats?.configured && (
        <div className="card" style={{ padding: '12px 16px', marginBottom: 20 }}>
          <div style={{ fontSize: 11, fontWeight: 500, color: 'var(--text-tertiary)', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: 8 }}>
            Routing configuration
          </div>
          <div style={{ display: 'flex', gap: 16, flexWrap: 'wrap' }}>
            {Object.entries(stats.routing ?? {}).map(([cid, cfg]: [string, any]) => (
              <div key={cid} style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 12 }}>
                <span style={{
                  width: 7, height: 7, borderRadius: '50%',
                  background: cfg.local ? '#1D9E75' : '#D85A30',
                  display: 'inline-block',
                }} />
                <span style={{ color: 'var(--text-secondary)' }}>{cfg.name}</span>
                <span style={{ color: 'var(--text-tertiary)' }}>→</span>
                <code style={{ fontSize: 10, color: cfg.local ? '#1D9E75' : '#7F77DD' }}>
                  {(cfg.provider ? `${cfg.provider}:` : '') + cfg.model}
                </code>
              </div>
            ))}
          </div>
        </div>
      )}

      <div className="card" style={{ overflow: 'hidden' }}>
        <div style={{
          display: 'grid',
          gridTemplateColumns: '72px 1fr 120px 180px 70px',
          gap: 10, padding: '8px 14px',
          background: 'var(--bg-secondary)',
          borderBottom: '0.5px solid var(--border)',
          fontSize: 10, fontWeight: 500,
          color: 'var(--text-tertiary)',
          textTransform: 'uppercase', letterSpacing: '0.05em',
        }}>
          <span>Time</span>
          <span>Prompt / Cluster</span>
          <span>Routed to</span>
          <span>Routing debug</span>
          <span>Confidence</span>
        </div>

        <div style={{ maxHeight: 480, overflowY: 'auto', padding: '8px' }}>
          {events.length === 0 ? (
            <div style={{ padding: '40px 16px', textAlign: 'center', color: 'var(--text-tertiary)', fontSize: 13 }}>
              {viewingSavedProject
                ? 'No saved routing activity found yet for this project.'
                : connected
                  ? 'Waiting for routing events...\nRun your agent with ShrinkLLM to see live decisions here.'
                  : 'Connecting to routing feed...'}
            </div>
          ) : (
            events.map((ev, i) => (
              <div
                key={i}
                style={{
                  display: 'grid',
                  gridTemplateColumns: '72px 1fr 120px 180px 70px',
                  gap: 10, padding: '7px 12px',
                  background: i % 2 === 0 ? 'var(--bg-secondary)' : 'transparent',
                  borderRadius: 5,
                  alignItems: 'start',
                }}
              >
                <div style={{ fontSize: 11, color: 'var(--text-tertiary)', paddingTop: 2 }}>{formatTs(ev.timestamp)}</div>
                <div style={{ minWidth: 0 }}>
                  <div style={{ fontSize: 12, fontWeight: 500, color: 'var(--text-primary)', marginBottom: 2 }}>
                    [{ev.cluster_name || 'unknown'}]
                  </div>
                  <div style={{ fontSize: 12, color: 'var(--text-secondary)', lineHeight: 1.5, whiteSpace: 'normal', overflowWrap: 'anywhere' }}>
                    {ev.prompt_preview || '—'}
                  </div>
                </div>
                <div style={{ minWidth: 0 }}>
                  <ModelBadge isLocal={ev.is_local} model={ev.model_display || ev.model_name} />
                </div>
                <div style={{ fontSize: 11, color: 'var(--text-secondary)', lineHeight: 1.55, whiteSpace: 'normal', overflowWrap: 'anywhere' }}>
                  <div>{ev.reason || (ev.is_local ? 'Local route' : 'API fallback')}</div>
                  {typeof ev.threshold === 'number' && (
                    <div style={{ color: 'var(--text-tertiary)', marginTop: 2 }}>
                      similarity {Math.round((ev.nearest_similarity || 0) * 100)}% · threshold {Math.round(ev.threshold * 100)}%
                    </div>
                  )}
                </div>
                <div style={{ fontSize: 11, color: 'var(--text-primary)', paddingTop: 2 }}>
                  {Math.round((ev.confidence || 0) * 100)}%
                </div>
              </div>
            ))
          )}
          <div ref={bottomRef} />
        </div>
      </div>
    </div>
  )
}

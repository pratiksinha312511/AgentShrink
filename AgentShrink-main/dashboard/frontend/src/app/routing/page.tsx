'use client'
import { useEffect, useRef, useState } from 'react'
import ProjectScopeBar from '@/components/ProjectScopeBar'
import {
  PageShell, PageHeader, TerminalCard, MetricRow, Metric,
  Badge, SecondaryButton, StatusDot, LoadingTerminal, EmptyState,
} from '@/components/Terminal'
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
  provider?: string
  timestamp: number
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
              provider: data.provider,
              timestamp: data.timestamp ?? Date.now() / 1000,
            }
            if (clearedAt && ev.timestamp <= clearedAt) return
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
    <PageShell maxWidth={960}>
      <ProjectScopeBar selectedProjectId={selectedProjectId} onChange={setSelectedProjectId} />

      <PageHeader
        tag="realtime"
        title="LIVE ROUTING"
        description={viewingSavedProject ? `Viewing saved history for ${selectedProjectName}` : undefined}
        right={
          <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 12 }}>
              <StatusDot ok={viewingSavedProject ? true : connected} pulse={!viewingSavedProject && connected} />
              <span style={{ color: viewingSavedProject ? 'var(--terminal-purple)' : connected ? 'var(--terminal-green)' : 'var(--terminal-red)' }}>
                {viewingSavedProject ? 'HISTORY' : connected ? 'CONNECTED' : 'RECONNECTING'}
              </span>
            </div>
            <SecondaryButton
              onClick={() => {
                setClearedAt(Date.now() / 1000)
                setEvents([])
                setTotals({ local: 0, api: 0 })
              }}
              style={{ padding: '4px 10px', fontSize: 10 }}
            >
              CLEAR
            </SecondaryButton>
          </div>
        }
      />

      {/* ── Metrics ── */}
      <MetricRow>
        <Metric label="TOTAL" value={total} />
        <Metric label="LOCAL SLM" value={totals.local} color="var(--terminal-green)" />
        <Metric label="REMOTE API" value={totals.api} color="var(--terminal-purple)" />
        <Metric
          label="LOCAL RATE"
          value={`${localPct}%`}
          color={localPct >= 60 ? 'var(--terminal-green)' : 'var(--terminal-amber)'}
        />
      </MetricRow>

      {/* ── Routing config + Feed (2-column layout) ── */}
      <div style={{ display: 'grid', gridTemplateColumns: '280px 1fr', gap: 16 }}>
        {/* ── Routing config sidebar ── */}
        {stats?.configured && (
          <TerminalCard title="ROUTING CONFIG">
            <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 11, color: 'var(--text-tertiary)', marginBottom: 4 }}>
                <span>{Object.keys(stats.routing ?? {}).length} clusters</span>
                <span>{Object.values(stats.routing ?? {}).filter((c: any) => c.local).length} local</span>
              </div>
              <input
                type="text"
                placeholder="Filter clusters..."
                onChange={e => {
                  const val = e.target.value.toLowerCase()
                  const el = e.target.parentElement?.querySelector('[data-routing-list]') as HTMLElement
                  if (!el) return
                  Array.from(el.children).forEach((child: any) => {
                    const name = child.getAttribute('data-name') ?? ''
                    child.style.display = name.includes(val) ? '' : 'none'
                  })
                }}
                style={{
                  padding: '5px 10px', fontSize: 11,
                  background: '#E0E5EC', border: 'none', borderRadius: 10,
                  boxShadow: 'inset 3px 3px 6px rgb(163,177,198,0.4), inset -3px -3px 6px rgba(255,255,255,0.3)',
                  color: 'var(--text-primary)', outline: 'none',
                }}
              />
              <div data-routing-list="" style={{ display: 'flex', flexDirection: 'column', gap: 8, maxHeight: 440, overflowY: 'auto' }}>
              {Object.entries(stats.routing ?? {}).map(([cid, cfg]: [string, any]) => (
                <div key={cid} data-name={(cfg.name ?? '').toLowerCase()} style={{
                  padding: '8px 12px',
                  background: '#E0E5EC',
                  borderRadius: 14,
                  boxShadow: 'inset 4px 4px 8px rgb(163,177,198,0.5), inset -4px -4px 8px rgba(255,255,255,0.4)',
                }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 3 }}>
                    <span style={{
                      width: 7, height: 7, borderRadius: 9999,
                      background: cfg.local ? 'var(--terminal-green)' : 'var(--terminal-purple)',
                      display: 'inline-block',
                      boxShadow: `0 0 6px ${cfg.local ? 'rgba(56,178,172,0.5)' : 'rgba(108,99,255,0.5)'}`,
                    }} />
                    <span style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-primary)' }}>{cfg.name}</span>
                  </div>
                  <code style={{ fontSize: 10, color: cfg.local ? 'var(--terminal-green)' : 'var(--terminal-purple)' }}>
                    {(cfg.provider ? `${cfg.provider}:` : '') + cfg.model}
                  </code>
                </div>
              ))}
              </div>
            </div>
          </TerminalCard>
        )}

        {/* ── Event feed ── */}
        <TerminalCard title="ROUTING FEED" noPadding>
        {/* Header row */}
        <div style={{
          display: 'grid',
          gridTemplateColumns: '72px 1fr 120px 180px 70px 60px',
          gap: 10, padding: '8px 14px',
          borderBottom: '1px solid var(--border)',
          fontSize: 11, fontWeight: 700,
          color: '#6B7280',
          textTransform: 'uppercase', letterSpacing: '0.06em',
        }}>
          <span>TIME</span>
          <span>CLUSTER / PROMPT</span>
          <span>ROUTED TO</span>
          <span>DEBUG</span>
          <span>CONF</span>
          <span>MS</span>
        </div>

        <div style={{ maxHeight: 480, overflowY: 'auto' }}>
          {events.length === 0 ? (
            <EmptyState
              message={viewingSavedProject
                ? 'No saved routing activity found for this project.'
                : connected
                  ? 'Waiting for routing events...'
                  : 'Connecting to routing feed...'}
              hint={!viewingSavedProject && connected ? 'Run your agent with ShrinkLLM to see live decisions' : undefined}
            />
          ) : (
            events.map((ev, i) => (
              <div
                key={i}
                style={{
                  display: 'grid',
                  gridTemplateColumns: '72px 1fr 120px 180px 70px 60px',
                  gap: 10,
                  padding: '6px 14px',
                  borderBottom: '1px solid var(--border)',
                  alignItems: 'start',
                  fontSize: 11,
                }}
              >
                <div style={{ color: '#9CA3AF', paddingTop: 2 }}>
                  {formatTs(ev.timestamp)}
                </div>
                <div style={{ minWidth: 0 }}>
                  <div style={{ fontWeight: 600, color: 'var(--terminal-green)', marginBottom: 2 }}>
                    [{ev.cluster_name || 'unknown'}]
                  </div>
                  <div style={{ color: 'var(--text-secondary)', lineHeight: 1.5, overflowWrap: 'anywhere' }}>
                    {ev.prompt_preview || '—'}
                  </div>
                </div>
                <div style={{ minWidth: 0 }}>
                  <Badge variant={ev.is_local ? 'green' : 'purple'}>
                    {ev.model_display || ev.model_name}
                  </Badge>
                  {ev.provider && (
                    <div style={{ fontSize: 9, color: 'var(--text-tertiary)', marginTop: 2 }}>
                      via {ev.provider}
                    </div>
                  )}
                </div>
                <div style={{ color: 'var(--text-secondary)', lineHeight: 1.5, overflowWrap: 'anywhere' }}>
                  <div>{ev.reason || (ev.is_local ? 'local route' : 'api fallback')}</div>
                  {typeof ev.threshold === 'number' && (
                    <div style={{ color: 'var(--text-tertiary)', marginTop: 2, fontSize: 10 }}>
                      sim {Math.round((ev.nearest_similarity || 0) * 100)}% · thr {Math.round(ev.threshold * 100)}%
                    </div>
                  )}
                </div>
                <div style={{ color: ev.confidence >= 0.75 ? 'var(--terminal-green)' : 'var(--terminal-amber)', paddingTop: 2 }}>
                  {Math.round((ev.confidence || 0) * 100)}%
                </div>
                <div style={{ color: 'var(--text-tertiary)', paddingTop: 2 }}>
                  {ev.latency_ms != null ? `${ev.latency_ms}ms` : '—'}
                </div>
              </div>
            ))
          )}
          <div ref={bottomRef} />
        </div>
      </TerminalCard>
      </div>
    </PageShell>
  )
}

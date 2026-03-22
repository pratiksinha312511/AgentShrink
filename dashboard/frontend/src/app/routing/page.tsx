'use client'
import { useEffect, useState, useRef } from 'react'
import { createRoutingWebSocket, fetchRoutingStats } from '@/lib/api'

interface RouteEvent {
  cluster_name:  string
  model_name:    string
  model_display: string
  confidence:    number
  is_local:      boolean
  prompt_preview?: string
  latency_ms?:   number
  timestamp:     number
}

function ModelBadge({ isLocal, model }: { isLocal: boolean; model: string }) {
  return (
    <span className="badge" style={{
      background: isLocal ? '#EAF3DE' : '#EEEDFE',
      color:      isLocal ? '#27500A' : '#3C3489',
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

export default function RoutingPage() {
  const [events, setEvents]     = useState<RouteEvent[]>([])
  const [stats, setStats]       = useState<any>(null)
  const [connected, setConnected] = useState(false)
  const [totals, setTotals]     = useState({ local: 0, api: 0 })
  const wsRef  = useRef<WebSocket | null>(null)
  const bottomRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    // Load routing config stats
    fetchRoutingStats().then(setStats).catch(() => {})

    // Connect WebSocket
    const connect = () => {
      const ws = createRoutingWebSocket(
        (data) => {
          if (data.type === 'connected') {
            setConnected(true)
          } else if (data.type === 'routing_decision') {
            const ev: RouteEvent = {
              cluster_name:  data.cluster_name  ?? 'unknown',
              model_name:    data.model_name    ?? 'unknown',
              model_display: data.model_display ?? data.model_name ?? 'unknown',
              confidence:    data.confidence    ?? 0,
              is_local:      data.is_local      ?? false,
              prompt_preview: data.prompt_preview,
              latency_ms:    data.latency_ms,
              timestamp:     data.timestamp     ?? Date.now() / 1000,
            }
            setEvents(prev => [...prev.slice(-199), ev])  // Keep last 200
            setTotals(prev => ({
              local: prev.local + (ev.is_local ? 1 : 0),
              api:   prev.api   + (ev.is_local ? 0 : 1),
            }))
          }
        },
        () => {
          setConnected(false)
          // Reconnect after 3 seconds
          setTimeout(connect, 3000)
        }
      )
      wsRef.current = ws
    }

    connect()
    return () => wsRef.current?.close()
  }, [])

  // Auto-scroll to bottom
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [events])

  const total = totals.local + totals.api
  const localPct = total > 0 ? Math.round(totals.local / total * 100) : 0

  return (
    <div style={{ maxWidth: 900 }}>
      {/* Header */}
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
                background: connected ? '#1D9E75' : '#D85A30',
                display: 'inline-block',
              }}
            />
            <span style={{ color: connected ? '#1D9E75' : '#D85A30' }}>
              {connected ? 'Connected — listening for routing events' : 'Reconnecting...'}
            </span>
          </div>
        </div>
        <button
          onClick={() => { setEvents([]); setTotals({ local: 0, api: 0 }) }}
          style={{
            background: 'transparent', border: '0.5px solid var(--border)',
            borderRadius: 6, padding: '6px 12px',
            fontSize: 12, color: 'var(--text-secondary)', cursor: 'pointer',
          }}
        >
          Clear
        </button>
      </div>

      {/* Session stats */}
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
          <div className="metric-label">→ API fallback</div>
        </div>
        <div className="metric-card">
          <div className="metric-num" style={{ color: localPct >= 60 ? '#1D9E75' : '#EF9F27' }}>
            {localPct}%
          </div>
          <div className="metric-label">Local routing rate</div>
        </div>
      </div>

      {/* Routing config summary */}
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
                <code style={{ fontSize: 10, color: cfg.local ? '#1D9E75' : '#7F77DD' }}>{cfg.model}</code>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Live feed */}
      <div className="card" style={{ overflow: 'hidden' }}>
        {/* Column headers */}
        <div style={{
          display: 'grid',
          gridTemplateColumns: '72px 1fr 120px 70px',
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
          <span>Confidence</span>
        </div>

        {/* Events */}
        <div style={{ maxHeight: 480, overflowY: 'auto', padding: '8px' }}>
          {events.length === 0 ? (
            <div style={{ padding: '40px 16px', textAlign: 'center', color: 'var(--text-tertiary)', fontSize: 13 }}>
              {connected
                ? 'Waiting for routing events...\nRun your agent with ShrinkLLM to see live decisions here.'
                : 'Connecting to routing feed...'
              }
            </div>
          ) : (
            events.map((ev, i) => (
              <div
                key={i}
                style={{
                  display: 'grid',
                  gridTemplateColumns: '72px 1fr 120px 70px',
                  gap: 10, padding: '7px 12px',
                  background: i % 2 === 0 ? 'var(--bg-secondary)' : 'transparent',
                  borderRadius: 5,
                  alignItems: 'start',
                  marginBottom: 2,
                  borderLeft: `2px solid ${ev.is_local ? '#1D9E75' : '#7F77DD'}`,
                }}
              >
                <div style={{ fontSize: 10, fontFamily: 'monospace', color: 'var(--text-tertiary)', paddingTop: 2 }}>
                  {formatTs(ev.timestamp)}
                </div>
                <div>
                  <div style={{ fontSize: 11, fontWeight: 500, color: 'var(--text-secondary)', marginBottom: 2 }}>
                    [{ev.cluster_name}]
                  </div>
                  {ev.prompt_preview && (
                    <div style={{ fontSize: 11, color: 'var(--text-tertiary)', fontStyle: 'italic', overflow: 'hidden', whiteSpace: 'nowrap', textOverflow: 'ellipsis' }}>
                      {ev.prompt_preview}
                    </div>
                  )}
                </div>
                <ModelBadge isLocal={ev.is_local} model={ev.model_display} />
                <div style={{ fontSize: 11, fontFamily: 'monospace', color: 'var(--text-tertiary)', paddingTop: 2 }}>
                  {(ev.confidence * 100).toFixed(0)}%
                  {ev.latency_ms && <span style={{ display: 'block', fontSize: 10 }}>{Math.round(ev.latency_ms)}ms</span>}
                </div>
              </div>
            ))
          )}
          <div ref={bottomRef} />
        </div>
      </div>

      {/* Info bar */}
      {!stats?.configured && (
        <div style={{ marginTop: 12, padding: '10px 14px', background: '#FAEEDA', borderRadius: 8, fontSize: 12, color: '#633806' }}>
          Routing not yet configured. Run <code>agentshrink analyse</code> first, then use <code>ShrinkLLM</code> in your agent.
        </div>
      )}
    </div>
  )
}

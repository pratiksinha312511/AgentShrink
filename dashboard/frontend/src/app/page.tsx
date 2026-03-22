'use client'
import { useEffect, useState } from 'react'
import {
  BarChart, Bar, XAxis, YAxis, Tooltip,
  ResponsiveContainer, Cell
} from 'recharts'
import { fetchStatus, triggerAnalyse } from '@/lib/api'

interface Status {
  total_calls: number
  total_runs: number
  total_tokens: number
  total_cost_usd: number
  nodes: Array<{ node_name: string; count: number; avg_latency: number; avg_cost: number }>
  daily_counts: Array<{ day: string; count: number }>
  has_data: boolean
  analysis_done: boolean
  report_done: boolean
  ready_for_analysis: boolean
}

export default function OverviewPage() {
  const [status, setStatus]     = useState<Status | null>(null)
  const [loading, setLoading]   = useState(true)
  const [analysing, setAnalysing] = useState(false)

  useEffect(() => {
    const load = async () => {
      try { setStatus(await fetchStatus()) }
      catch (e) { console.error(e) }
      finally { setLoading(false) }
    }
    load()
    const interval = setInterval(load, 5000)
    return () => clearInterval(interval)
  }, [])

  const handleAnalyse = async () => {
    setAnalysing(true)
    await triggerAnalyse({ min_cluster_size: 5, skip_eval: false })
    setTimeout(() => setAnalysing(false), 3000)
  }

  const phaseLabel = () => {
    if (!status?.has_data)       return { text: 'Phase 0 — No data', color: '#888' }
    if (!status.ready_for_analysis) return { text: 'Phase 1 — Collecting data', color: '#EF9F27' }
    if (!status.analysis_done)   return { text: 'Ready for analysis', color: '#185FA5' }
    if (!status.report_done)     return { text: 'Phase 2 — Clustered', color: '#7F77DD' }
    return { text: 'Phase 3 — Report ready', color: '#1D9E75' }
  }

  const phase = phaseLabel()

  if (loading) return (
    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: 300 }}>
      <div style={{ color: 'var(--text-tertiary)', fontSize: 13 }}>Loading...</div>
    </div>
  )

  return (
    <div style={{ maxWidth: 900 }}>
      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 24 }}>
        <div>
          <h1 style={{ fontSize: 22, fontWeight: 500, color: 'var(--text-primary)', marginBottom: 4 }}>
            Overview
          </h1>
          <div style={{ fontSize: 13, color: 'var(--text-secondary)' }}>
            customer_support_agent
          </div>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <span className="badge" style={{ background: phase.color + '22', color: phase.color }}>
            {phase.text}
          </span>
          {status?.ready_for_analysis && !analysing && (
            <button
              onClick={handleAnalyse}
              style={{
                background: '#7F77DD', color: 'white',
                border: 'none', borderRadius: 8,
                padding: '8px 16px', fontSize: 12,
                fontWeight: 500, cursor: 'pointer',
              }}
            >
              Run Analysis →
            </button>
          )}
          {analysing && (
            <span style={{ fontSize: 12, color: '#7F77DD' }}>Running...</span>
          )}
        </div>
      </div>

      {/* Metrics strip */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr 1fr', gap: 10, marginBottom: 24 }}>
        {[
          { label: 'LLM calls captured', value: status?.total_calls?.toLocaleString() ?? '0', change: 'total' },
          { label: 'Agent runs',         value: status?.total_runs?.toLocaleString() ?? '0', change: 'unique' },
          { label: 'Total tokens',       value: status?.total_tokens ? (status.total_tokens / 1000).toFixed(1) + 'K' : '0', change: 'used' },
          { label: 'Est. API cost',      value: `$${status?.total_cost_usd?.toFixed(4) ?? '0.0000'}`, change: 'before shrink' },
        ].map(m => (
          <div className="metric-card" key={m.label}>
            <div className="metric-num">{m.value}</div>
            <div className="metric-label">{m.label}</div>
            <div style={{ fontSize: 10, color: 'var(--text-tertiary)', marginTop: 3 }}>{m.change}</div>
          </div>
        ))}
      </div>

      {/* Daily calls chart */}
      <div className="card" style={{ padding: '16px 20px', marginBottom: 20 }}>
        <div style={{ fontSize: 12, fontWeight: 500, color: 'var(--text-secondary)', marginBottom: 14 }}>
          Calls per day — last 14 days
        </div>
        {status?.daily_counts && status.daily_counts.length > 0 ? (
          <ResponsiveContainer width="100%" height={160}>
            <BarChart data={status.daily_counts} margin={{ top: 0, right: 0, left: -20, bottom: 0 }}>
              <XAxis
                dataKey="day"
                tick={{ fontSize: 10, fill: 'var(--text-tertiary)' }}
                tickFormatter={v => v.slice(5)}  // Show only MM-DD
              />
              <YAxis tick={{ fontSize: 10, fill: 'var(--text-tertiary)' }} />
              <Tooltip
                contentStyle={{
                  background: 'var(--bg-primary)',
                  border: '0.5px solid var(--border)',
                  borderRadius: 6,
                  fontSize: 12,
                }}
              />
              <Bar dataKey="count" fill="#7F77DD" radius={[3, 3, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        ) : (
          <div style={{ height: 160, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
            <div style={{ color: 'var(--text-tertiary)', fontSize: 13 }}>
              No data yet — run your agent with AgentShrinkLogger attached
            </div>
          </div>
        )}
      </div>

      {/* Per-node table */}
      {status?.nodes && status.nodes.length > 0 && (
        <div className="card" style={{ overflow: 'hidden' }}>
          <div style={{ padding: '14px 20px', borderBottom: '0.5px solid var(--border)', fontSize: 12, fontWeight: 500, color: 'var(--text-secondary)' }}>
            Calls per agent node
          </div>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12 }}>
            <thead>
              <tr style={{ background: 'var(--bg-secondary)' }}>
                {['Node name', 'Calls', 'Avg latency', 'Avg cost', 'Status'].map(h => (
                  <th key={h} style={{ padding: '8px 14px', textAlign: 'left', fontSize: 10, fontWeight: 500, color: 'var(--text-tertiary)', textTransform: 'uppercase', letterSpacing: '0.05em', borderBottom: '0.5px solid var(--border)' }}>
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {status.nodes.map((node, i) => (
                <tr key={node.node_name} style={{ borderBottom: i < status.nodes.length - 1 ? '0.5px solid var(--border)' : 'none' }}>
                  <td style={{ padding: '9px 14px', fontWeight: 500, color: 'var(--text-primary)' }}>{node.node_name}</td>
                  <td style={{ padding: '9px 14px', color: 'var(--text-secondary)' }}>{node.count}</td>
                  <td style={{ padding: '9px 14px', color: 'var(--text-secondary)' }}>{Math.round(node.avg_latency)}ms</td>
                  <td style={{ padding: '9px 14px', color: 'var(--text-secondary)' }}>${(node.avg_cost || 0).toFixed(5)}</td>
                  <td style={{ padding: '9px 14px' }}>
                    <span className="badge badge-purple">not clustered</span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Empty state */}
      {!status?.has_data && (
        <div className="card" style={{ padding: 32, textAlign: 'center' }}>
          <div style={{ fontSize: 15, fontWeight: 500, color: 'var(--text-primary)', marginBottom: 8 }}>
            No data captured yet
          </div>
          <div style={{ fontSize: 13, color: 'var(--text-secondary)', lineHeight: 1.7 }}>
            Add AgentShrinkLogger to your agent and run it:<br />
            <code style={{ fontFamily: 'monospace', background: 'var(--bg-secondary)', padding: '2px 6px', borderRadius: 4 }}>
              from agentshrink import AgentShrinkLogger
            </code>
          </div>
        </div>
      )}
    </div>
  )
}

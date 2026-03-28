'use client'
import { useEffect, useState } from 'react'
import {
  BarChart, Bar, XAxis, YAxis, Tooltip,
  ResponsiveContainer, Cell
} from 'recharts'
import { fetchStatus, triggerAnalyse } from '@/lib/api'

const ANALYSIS_STORAGE_KEY = 'agentshrink.analysis.running'

interface Status {
  total_calls: number
  total_runs: number
  total_tokens: number
  total_cost_usd: number
  estimated_baseline_model?: string
  estimated_baseline_cost_usd?: number
  estimated_savings_usd?: number
  estimated_savings_pct?: number
  local_call_count?: number
  fallback_call_count?: number
  nodes: Array<{ node_name: string; count: number; avg_latency: number; avg_cost: number }>
  daily_counts: Array<{ day: string; count: number }>
  has_data: boolean
  analysis_done: boolean
  report_done: boolean
  ready_for_analysis: boolean
  node_statuses?: Record<string, {
    status: string
    cluster_count: number
    prompt_count: number
    cluster_names: string[]
  }>
}

export default function OverviewPage() {
  const [status, setStatus]     = useState<Status | null>(null)
  const [loading, setLoading]   = useState(true)
  const [analysing, setAnalysing] = useState(false)
  const [analysisMsg, setAnalysisMsg] = useState('')

  useEffect(() => {
    const persistedAnalysis = window.localStorage.getItem(ANALYSIS_STORAGE_KEY) === 'true'
    if (persistedAnalysis) {
      setAnalysing(true)
      setAnalysisMsg('Analysis is still running...')
    }

    const load = async () => {
      try {
        const nextStatus = await fetchStatus()
        setStatus(nextStatus)

        const running = window.localStorage.getItem(ANALYSIS_STORAGE_KEY) === 'true'
        if (nextStatus.analysis_done && running) {
          window.localStorage.removeItem(ANALYSIS_STORAGE_KEY)
          setAnalysing(false)
          setAnalysisMsg('Analysis complete. Cluster data is ready.')
        } else if (running) {
          setAnalysing(true)
          setAnalysisMsg('Analysis is still running...')
        }
      }
      catch (e) { console.error(e) }
      finally { setLoading(false) }
    }
    load()
    const interval = setInterval(load, 5000)
    return () => clearInterval(interval)
  }, [])

  const handleAnalyse = async () => {
    setAnalysing(true)
    window.localStorage.setItem(ANALYSIS_STORAGE_KEY, 'true')
    setAnalysisMsg('Starting analysis...')
    try {
      const result = await triggerAnalyse({
        min_cluster_size: 5,
        skip_eval: true,
        no_llm_labels: true,
      })
      setAnalysisMsg(result?.message ?? 'Analysis started. This will keep running if you change tabs.')
    } catch (e) {
      console.error(e)
      window.localStorage.removeItem(ANALYSIS_STORAGE_KEY)
      setAnalysing(false)
      setAnalysisMsg('Failed to start analysis')
    }
  }

  const phaseLabel = () => {
    if (!status?.has_data)       return { text: 'Phase 0 — No data', color: '#888' }
    if (!status.ready_for_analysis) return { text: 'Phase 1 — Collecting data', color: '#EF9F27' }
    if (!status.analysis_done)   return { text: 'Ready for analysis', color: '#185FA5' }
    if (!status.report_done)     return { text: 'Phase 2 — Clustered', color: '#7F77DD' }
    return { text: 'Phase 3 — Report ready', color: '#1D9E75' }
  }

  const phase = phaseLabel()

  const formatMoney = (value: number | undefined, opts?: { maxDecimals?: number }) => {
    const amount = value ?? 0
    const maxDecimals = opts?.maxDecimals ?? 4
    if (amount === 0) return '$0.0000'
    if (amount >= 0.01) return `$${amount.toFixed(4)}`
    if (amount >= 0.0001) return `$${amount.toFixed(Math.max(maxDecimals, 5))}`
    return `$${amount.toExponential(2)}`
  }

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

      {analysisMsg && (
        <div className="card" style={{ padding: '10px 14px', marginBottom: 16, fontSize: 12, color: 'var(--text-secondary)' }}>
          {analysisMsg}
        </div>
      )}

      {status?.has_data && (
        <div className="card" style={{ padding: '12px 14px', marginBottom: 16 }}>
          <div style={{ fontSize: 12, fontWeight: 500, color: 'var(--text-primary)', marginBottom: 4 }}>
            Local-only savings estimate
          </div>
          <div style={{ fontSize: 12, color: 'var(--text-secondary)', lineHeight: 1.6 }}>
            If these calls had all gone to <span style={{ fontFamily: 'monospace' }}>{status.estimated_baseline_model ?? 'gpt-4o-mini'}</span>,
            you would have spent about <strong style={{ color: 'var(--text-primary)' }}> ${status.estimated_baseline_cost_usd?.toFixed(4) ?? '0.0000'}</strong>.
            Based on the models used in your logs, AgentShrink avoided about
            <strong style={{ color: '#1D9E75' }}> {formatMoney(status.estimated_savings_usd)}</strong>
            {' '}({status.estimated_savings_pct?.toFixed(1) ?? '0.0'}%).
          </div>
          <div style={{ fontSize: 11, color: 'var(--text-tertiary)', marginTop: 6 }}>
            Local calls: {status.local_call_count ?? 0} · fallback/strong-model calls: {status.fallback_call_count ?? 0}
          </div>
        </div>
      )}

      {/* Metrics strip */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr 1fr', gap: 10, marginBottom: 24 }}>
        {[
          { label: 'LLM calls captured', value: status?.total_calls?.toLocaleString() ?? '0', change: 'total' },
          { label: 'Agent runs',         value: status?.total_runs?.toLocaleString() ?? '0', change: 'unique' },
          { label: 'Total tokens',       value: status?.total_tokens ? (status.total_tokens / 1000).toFixed(1) + 'K' : '0', change: 'used' },
          { label: 'Spend avoided',      value: formatMoney(status?.estimated_savings_usd), change: `vs ${status?.estimated_baseline_model ?? 'gpt-4o-mini'}` },
        ].map(m => (
          <div className="metric-card" key={m.label}>
            <div className="metric-num">{m.value}</div>
            <div className="metric-label">{m.label}</div>
            <div style={{ fontSize: 10, color: 'var(--text-tertiary)', marginTop: 3 }}>{m.change}</div>
          </div>
        ))}
      </div>

      {status?.has_data && (
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10, marginBottom: 24 }}>
          <div className="metric-card" style={{ alignItems: 'flex-start' }}>
            <div className="metric-num" style={{ color: 'var(--text-primary)' }}>
              {formatMoney(status?.estimated_baseline_cost_usd)}
            </div>
            <div className="metric-label">Estimated cloud cost</div>
            <div style={{ fontSize: 10, color: 'var(--text-tertiary)', marginTop: 3 }}>
              if every call used {status?.estimated_baseline_model ?? 'gpt-4o-mini'}
            </div>
          </div>
          <div className="metric-card" style={{ alignItems: 'flex-start' }}>
            <div className="metric-num" style={{ color: '#7F77DD' }}>
              {formatMoney(status?.total_cost_usd)}
            </div>
            <div className="metric-label">Observed spend in logs</div>
            <div style={{ fontSize: 10, color: 'var(--text-tertiary)', marginTop: 3 }}>
              actual cost captured from your current providers
            </div>
          </div>
        </div>
      )}

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
                  <td
                    style={{ padding: '9px 14px', color: 'var(--text-secondary)' }}
                    title={`Exact avg cost: $${(node.avg_cost || 0).toFixed(8)}`}
                  >
                    {formatMoney(node.avg_cost, { maxDecimals: 6 })}
                  </td>
                  <td style={{ padding: '9px 14px' }}>
                    {status.node_statuses?.[node.node_name] ? (
                      <span
                        className="badge"
                        title={status.node_statuses[node.node_name].cluster_names.join(', ')}
                        style={{ background: '#EEEDFE', color: '#3C3489' }}
                      >
                        clustered ({status.node_statuses[node.node_name].cluster_count})
                      </span>
                    ) : (
                      <span className="badge" style={{ background: '#F5F1EA', color: '#8A7E72' }}>
                        not clustered
                      </span>
                    )}
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

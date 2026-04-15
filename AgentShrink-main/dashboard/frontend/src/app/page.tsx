'use client'
import { useEffect, useState } from 'react'
import Link from 'next/link'
import ProjectScopeBar from '@/components/ProjectScopeBar'
import {
  PageShell, PageHeader, TerminalCard, MetricRow, Metric,
  Badge, PrimaryButton, AnimatedActionButton, LoadingTerminal, EmptyState, CodeBlock,
} from '@/components/Terminal'
import {
  BarChart, Bar, XAxis, YAxis, Tooltip,
  ResponsiveContainer
} from 'recharts'
import { fetchAnalysisLogs, fetchDashboardSummary, fetchPublicProjectSummary, fetchPublicProjects, triggerAnalyse } from '@/lib/api'

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
  gateway_event_count?: number
  latest_timestamp?: string | null
  source_of_truth?: string
  node_statuses?: Record<string, {
    status: string
    cluster_count: number
    prompt_count: number
    cluster_names: string[]
  }>
}

interface DashboardSummary {
  status: Status
  sources: {
    traffic: { kind: string; ready: boolean; call_count: number; gateway_event_count: number; latest_timestamp?: string | null }
    analysis: { kind: string; ready: boolean; cluster_count: number }
    report: { kind: string; ready: boolean }
    routing: { kind: string; ready: boolean; cluster_count: number }
  }
  account?: { name?: string }
  project?: { name?: string; environment?: string }
}

export default function OverviewPage() {
  const [status, setStatus]     = useState<Status | null>(null)
  const [summary, setSummary]   = useState<DashboardSummary | null>(null)
  const [loading, setLoading]   = useState(true)
  const [analysing, setAnalysing] = useState(false)
  const [analysisMsg, setAnalysisMsg] = useState('')
  const [activeProjectId, setActiveProjectId] = useState('')
  const [selectedProjectId, setSelectedProjectId] = useState('')

  useEffect(() => {
    const persistedAnalysis = window.localStorage.getItem(ANALYSIS_STORAGE_KEY) === 'true'
    if (persistedAnalysis) {
      setAnalysing(true)
      setAnalysisMsg('Analysis is still running...')
    }

    const load = async () => {
      try {
        const projects = await fetchPublicProjects()
        const nextActiveProjectId = projects?.active_project_id || ''
        const nextSelectedProjectId = selectedProjectId || nextActiveProjectId
        const analysisState = await fetchAnalysisLogs().catch(() => ({ running: false }))
        const nextSummary = nextSelectedProjectId && nextSelectedProjectId !== nextActiveProjectId
          ? await fetchPublicProjectSummary(nextSelectedProjectId)
          : await fetchDashboardSummary()
        const nextStatus = nextSummary.status
        setActiveProjectId(nextActiveProjectId)
        setSelectedProjectId(nextSelectedProjectId)
        setSummary(nextSummary)
        setStatus(nextStatus)

        const running = window.localStorage.getItem(ANALYSIS_STORAGE_KEY) === 'true'
        if (nextSelectedProjectId === nextActiveProjectId && nextStatus.analysis_done && running) {
          window.localStorage.removeItem(ANALYSIS_STORAGE_KEY)
          setAnalysing(false)
          setAnalysisMsg('Analysis complete. Cluster data is ready.')
        } else if (running && nextSelectedProjectId === nextActiveProjectId && !analysisState?.running) {
          window.localStorage.removeItem(ANALYSIS_STORAGE_KEY)
          setAnalysing(false)
          setAnalysisMsg(nextStatus.analysis_done
            ? 'Analysis complete. Cluster data is ready.'
            : 'Previous analysis is no longer running. You can start it again.')
        } else if (running && nextSelectedProjectId === nextActiveProjectId) {
          setAnalysing(true)
          setAnalysisMsg('Analysis is still running...')
        } else if (!running && !analysisState?.running && analysing) {
          setAnalysing(false)
        }
      }
      catch (e) { console.error(e) }
      finally { setLoading(false) }
    }
    load()
    const interval = setInterval(load, 5000)
    return () => clearInterval(interval)
  }, [selectedProjectId])

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
      setAnalysisMsg(result?.message ?? 'Analysis started. Cluster Map and Report will refresh automatically.')
    } catch (e) {
      console.error(e)
      window.localStorage.removeItem(ANALYSIS_STORAGE_KEY)
      setAnalysing(false)
      setAnalysisMsg('Failed to start analysis')
    }
  }

  const phaseLabel = () => {
    if (!status?.has_data)       return { text: 'NO DATA', variant: 'default' as const }
    if (!status.ready_for_analysis) return { text: 'COLLECTING', variant: 'amber' as const }
    if (analysing)               return { text: 'ANALYSING', variant: 'blue' as const }
    if (!status.analysis_done)   return { text: 'READY', variant: 'blue' as const }
    if (!status.report_done)     return { text: 'CLUSTERED', variant: 'purple' as const }
    return { text: 'REPORT READY', variant: 'green' as const }
  }
  const phase = phaseLabel()

  const formatMoney = (value: number | undefined) => {
    const amount = value ?? 0
    if (amount === 0) return '$0.00'
    if (amount >= 0.01) return `$${amount.toFixed(4)}`
    return `$${amount.toExponential(2)}`
  }

  if (loading) return <LoadingTerminal message="loading dashboard" />

  return (
    <PageShell maxWidth={960}>
      <ProjectScopeBar selectedProjectId={selectedProjectId} onChange={setSelectedProjectId} />

      <PageHeader
        tag="dashboard"
        title="OVERVIEW"
        description={summary?.project?.name || 'AgentShrink Project'}
        right={
          <>
            <Badge variant={phase.variant}>{phase.text}</Badge>
            {selectedProjectId === activeProjectId && status?.ready_for_analysis && !analysing && (
              <AnimatedActionButton onClick={handleAnalyse} label="RUN ANALYSIS" icon="play" />
            )}
            {selectedProjectId === activeProjectId && analysing && (
              <AnimatedActionButton onClick={() => {}} label="ANALYSING..." icon="spinner" disabled active />
            )}
          </>
        }
      />

      {selectedProjectId && activeProjectId && selectedProjectId !== activeProjectId && (
        <TerminalCard>
          <div style={{ fontSize: 12, color: 'var(--terminal-amber)' }}>
            [WARN] Viewing a saved project. Runtime actions only work on the active project.
          </div>
        </TerminalCard>
      )}

      {analysisMsg && (
        <TerminalCard>
          <div style={{ fontSize: 12, color: 'var(--text-secondary)' }}>
            {analysisMsg}
          </div>
        </TerminalCard>
      )}

      {!status?.has_data && (
        <TerminalCard title="GET STARTED">
          <div style={{ fontSize: 12, color: 'var(--text-secondary)', marginBottom: 12, lineHeight: 1.7 }}>
            No data captured yet. Start from the guided onboarding page to launch the stack,
            copy the right integration snippet, and test the gateway in free mock mode.
          </div>
          <Link href="/welcome" style={{
            fontSize: 13,
            color: '#6C63FF',
            fontWeight: 600,
            textDecoration: 'none',
          }}>
            Go to Get Started →
          </Link>
        </TerminalCard>
      )}

      {/* ── Metrics ── */}
      <MetricRow>
        <Metric label="LLM CALLS" value={status?.total_calls?.toLocaleString() ?? '0'} />
        <Metric label="AGENT RUNS" value={status?.total_runs?.toLocaleString() ?? '0'} />
        <Metric label="TOKENS" value={status?.total_tokens ? (status.total_tokens / 1000).toFixed(1) + 'K' : '0'} />
        <Metric label="SPEND AVOIDED" value={formatMoney(status?.estimated_savings_usd)} color="#38B2AC" />
      </MetricRow>

      {status?.has_data && (
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 12 }}>
          <TerminalCard title="PIPELINE STATUS">
            <div style={{ display: 'grid', gap: 8, fontSize: 12 }}>
              <StatusLine label="source" value={status.source_of_truth || 'sqlite:llm_calls'} />
              <StatusLine label="calls" value={String(status.total_calls)} />
              <StatusLine label="gateway events" value={String(status.gateway_event_count ?? 0)} />
              <StatusLine label="clusters" value={String(summary?.sources.analysis.cluster_count ?? 0)} />
              <StatusLine label="routing entries" value={String(summary?.sources.routing.cluster_count ?? 0)} />
              <StatusLine label="local calls" value={String(status.local_call_count ?? 0)} />
              <StatusLine label="fallback calls" value={String(status.fallback_call_count ?? 0)} />
            </div>
          </TerminalCard>
          <TerminalCard title="SAVINGS ESTIMATE">
            <div style={{ display: 'grid', gap: 8, fontSize: 12 }}>
              <StatusLine label="baseline model" value={status.estimated_baseline_model ?? 'gpt-4o-mini'} />
              <StatusLine label="baseline cost" value={formatMoney(status.estimated_baseline_cost_usd)} />
              <StatusLine label="observed spend" value={formatMoney(status.total_cost_usd)} />
              <StatusLine
                label="savings"
                value={`${formatMoney(status.estimated_savings_usd)} (${status.estimated_savings_pct?.toFixed(1) ?? '0.0'}%)`}
                highlight
              />
              <StatusLine label="last activity" value={status.latest_timestamp ? status.latest_timestamp.slice(0, 19).replace('T', ' ') : 'n/a'} />
            </div>
          </TerminalCard>

          {/* ── Daily calls chart (inline) ── */}
          <TerminalCard title="CALLS PER DAY">
            {status?.daily_counts && status.daily_counts.length > 0 ? (
              <ResponsiveContainer width="100%" height={180}>
                <BarChart data={status.daily_counts} margin={{ top: 0, right: 0, left: -20, bottom: 0 }}>
                  <XAxis
                    dataKey="day"
                    tick={{ fontSize: 10, fill: '#6B7280' }}
                    tickFormatter={v => v.slice(5)}
                    stroke="transparent"
                  />
                  <YAxis
                    tick={{ fontSize: 10, fill: '#6B7280' }}
                    stroke="transparent"
                  />
                  <Tooltip
                    contentStyle={{
                      background: '#E0E5EC',
                      border: 'none',
                      borderRadius: 16,
                      fontSize: 12,
                      color: '#3D4852',
                      boxShadow: '5px 5px 10px rgb(163,177,198,0.6), -5px -5px 10px rgba(255,255,255,0.5)',
                    }}
                  />
                  <Bar dataKey="count" fill="#6C63FF" radius={[6, 6, 0, 0]} opacity={0.8} />
                </BarChart>
              </ResponsiveContainer>
            ) : (
              <EmptyState message="No chart data yet" />
            )}
          </TerminalCard>
        </div>
      )}

      {/* ── Per-node table ── */}
      {status?.nodes && status.nodes.length > 0 && (
        <TerminalCard title="AGENT NODES" noPadding>
          <table className="terminal-table">
            <thead>
              <tr>
                <th>NODE</th>
                <th>CALLS</th>
                <th>AVG LATENCY</th>
                <th>AVG COST</th>
                <th>STATUS</th>
              </tr>
            </thead>
            <tbody>
              {status.nodes.map((node) => (
                <tr key={node.node_name}>
                  <td style={{ fontWeight: 600, color: '#6C63FF' }}>{node.node_name}</td>
                  <td>{node.count}</td>
                  <td>{Math.round(node.avg_latency)}ms</td>
                  <td>{formatMoney(node.avg_cost)}</td>
                  <td>
                    {status.node_statuses?.[node.node_name] ? (
                      <Badge variant="purple">
                        clustered ({status.node_statuses[node.node_name].cluster_count})
                      </Badge>
                    ) : (
                      <Badge>unclustered</Badge>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </TerminalCard>
      )}

      {/* ── Empty state ── */}
      {!status?.has_data && (
        <TerminalCard>
          <EmptyState
            message="No data captured yet"
            hint="Add AgentShrinkLogger to your agent and run it"
          />
          <div style={{ textAlign: 'center', marginTop: 8 }}>
            <CodeBlock text="from agentshrink import AgentShrinkLogger" copyable />
          </div>
        </TerminalCard>
      )}
    </PageShell>
  )
}

function StatusLine({ label, value, highlight }: { label: string; value: string; highlight?: boolean }) {
  return (
    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
      <span style={{ color: '#6B7280' }}>{label}:</span>
      <span style={{
        color: highlight ? '#6C63FF' : '#3D4852',
        fontWeight: highlight ? 700 : 400,
      }}>{value}</span>
    </div>
  )
}

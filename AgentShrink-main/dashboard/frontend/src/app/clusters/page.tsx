'use client'
import { useEffect, useState } from 'react'
import Link from 'next/link'
import ProjectScopeBar from '@/components/ProjectScopeBar'
import { ScatterChart, Scatter, XAxis, YAxis, Tooltip, ResponsiveContainer } from 'recharts'
import { fetchClusters, fetchPublicProjectClusters, fetchPublicProjects, fetchReport, triggerAnalyse } from '@/lib/api'
import {
  PageShell, PageHeader, TerminalCard, Badge, PrimaryButton, SecondaryButton,
  AnimatedActionButton, LoadingTerminal, ErrorBlock, EmptyState,
} from '@/components/Terminal'

const ANALYSIS_STORAGE_KEY = 'agentshrink.analysis.running'
const TARGET_CLUSTER_STORAGE_KEY = 'agentshrink.target_cluster_eval'

interface ClusterPoint {
  x: number; y: number
  cluster_id: number; cluster_name: string
  color: string; prompt_preview: string; node_name: string
}

interface ClusterData {
  n_clusters: number; n_noise: number
  cluster_names: Record<string, string>
  clusters: Record<string, any>
  points: ClusterPoint[]
}

const CustomDot = (props: any) => {
  const { cx, cy, payload } = props
  return (
    <circle
      cx={cx} cy={cy} r={5}
      fill={payload.color}
      fillOpacity={0.75}
      stroke={payload.color}
      strokeWidth={0.5}
      strokeOpacity={0.9}
      style={{ cursor: 'pointer', transition: 'r 0.15s' }}
      onMouseEnter={e => { (e.target as SVGCircleElement).setAttribute('r', '8') }}
      onMouseLeave={e => { (e.target as SVGCircleElement).setAttribute('r', '5') }}
    />
  )
}

const CustomTooltip = ({ active, payload }: any) => {
  if (!active || !payload?.length) return null
  const p = payload[0].payload
  return (
    <div style={{
      background: 'var(--bg-secondary)',
      border: '1px solid var(--border)',
      padding: '10px 12px',
      fontSize: 11, maxWidth: 260,
    }}>
        <div style={{ fontWeight: 700, color: '#6C63FF', marginBottom: 4 }}>
        {p.cluster_name}
      </div>
      <div style={{ color: 'var(--text-secondary)', lineHeight: 1.5 }}>
        {p.prompt_preview}
      </div>
      <div style={{ marginTop: 6, color: 'var(--text-tertiary)', fontSize: 10 }}>
        node: {p.node_name}
      </div>
    </div>
  )
}

export default function ClustersPage() {
  const [data, setData]       = useState<ClusterData | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError]     = useState('')
  const [selected, setSelected] = useState<string | null>(null)
  const [waitingForAnalysis, setWaitingForAnalysis] = useState(false)
  const [evaluatingClusterId, setEvaluatingClusterId] = useState<string | null>(null)
  const [evaluatingAll, setEvaluatingAll] = useState(false)
  const [actionMsg, setActionMsg] = useState('')
  const [reportClusterId, setReportClusterId] = useState<string | null>(null)
  const [targetedRunReady, setTargetedRunReady] = useState(false)
  const [fullReportBaseline, setFullReportBaseline] = useState<string | null>(null)
  const [activeProjectId, setActiveProjectId] = useState('')
  const [selectedProjectId, setSelectedProjectId] = useState('')
  const [showAllPills, setShowAllPills] = useState(false)
  const [showAllCards, setShowAllCards] = useState(false)

  useEffect(() => {
    const persistedTargetCluster = window.localStorage.getItem(TARGET_CLUSTER_STORAGE_KEY)
    if (persistedTargetCluster) {
      setReportClusterId(persistedTargetCluster)
      setActionMsg(`Targeted evaluation is still running for cluster ${persistedTargetCluster}.`)
    }

    const loadClusters = async () => {
      try {
        const projects = await fetchPublicProjects()
        const nextActiveProjectId = projects?.active_project_id || ''
        const nextSelectedProjectId = selectedProjectId || nextActiveProjectId
        const nextData = nextSelectedProjectId && nextSelectedProjectId !== nextActiveProjectId
          ? await fetchPublicProjectClusters(nextSelectedProjectId)
          : await fetchClusters()
        setActiveProjectId(nextActiveProjectId)
        setSelectedProjectId(nextSelectedProjectId)
        setData(nextData)
        setError('')
        setWaitingForAnalysis(false)
        if (nextData.n_clusters > 0 && nextSelectedProjectId === nextActiveProjectId) {
          window.localStorage.removeItem(ANALYSIS_STORAGE_KEY)
        }
      } catch (e: any) {
        setError(e.message)
        setWaitingForAnalysis(window.localStorage.getItem(ANALYSIS_STORAGE_KEY) === 'true')
      } finally {
        setLoading(false)
      }
    }

    loadClusters()
    const interval = setInterval(loadClusters, 5000)
    return () => clearInterval(interval)
  }, [selectedProjectId])

  useEffect(() => {
    if (!reportClusterId || targetedRunReady) return

    let cancelled = false
    const pollTargetedReport = async () => {
      try {
        await fetchReport(Number(reportClusterId))
        if (cancelled) return
        setTargetedRunReady(true)
        setEvaluatingClusterId(null)
        setWaitingForAnalysis(false)
        window.localStorage.removeItem(ANALYSIS_STORAGE_KEY)
        window.localStorage.removeItem(TARGET_CLUSTER_STORAGE_KEY)
        setActionMsg(`Targeted evaluation complete for cluster ${reportClusterId}.`)
      } catch {
        if (!cancelled) {
          setActionMsg(`Targeted evaluation in progress for cluster ${reportClusterId}...`)
        }
      }
    }

    pollTargetedReport()
    const interval = setInterval(pollTargetedReport, 5000)
    return () => {
      cancelled = true
      clearInterval(interval)
    }
  }, [reportClusterId, targetedRunReady])

  useEffect(() => {
    if (!evaluatingAll) return

    let cancelled = false
    const pollFullReport = async () => {
      try {
        const report = await fetchReport()
        const generatedAt = report?.generated_at ?? null
        if (cancelled) return
        if (generatedAt && generatedAt !== fullReportBaseline) {
          setEvaluatingAll(false)
          setWaitingForAnalysis(false)
          setFullReportBaseline(generatedAt)
          window.localStorage.removeItem(ANALYSIS_STORAGE_KEY)
          setActionMsg('Evaluate all complete. The main replaceability report has been refreshed.')
        } else {
          setActionMsg('Evaluate all is running. We are waiting for the main report to refresh.')
        }
      } catch {
        if (!cancelled) {
          setActionMsg('Evaluate all is running. We are waiting for the main report to refresh.')
        }
      }
    }

    pollFullReport()
    const interval = setInterval(pollFullReport, 5000)
    return () => {
      cancelled = true
      clearInterval(interval)
    }
  }, [evaluatingAll, fullReportBaseline])

  if (loading) return <LoadingTerminal message="loading cluster map" />

  if (error) return (
    <PageShell maxWidth={920}>
      {waitingForAnalysis ? (
        <TerminalCard title="ANALYSIS RUNNING">
          <div style={{ color: 'var(--terminal-amber)', fontSize: 12 }}>
            This page refreshes automatically every 5 seconds.
          </div>
        </TerminalCard>
      ) : (
        <EmptyState message="No cluster data yet. Run: agentshrink analyse" />
      )}
    </PageShell>
  )

  const clusterIds = Object.keys(data?.cluster_names ?? {})
  const selectedInfo = selected ? data?.clusters?.[selected] : null

  const handleEvaluateCluster = async (clusterId: string) => {
    setEvaluatingClusterId(clusterId)
    setActionMsg('')
    setReportClusterId(clusterId)
    setTargetedRunReady(false)
    window.localStorage.setItem(ANALYSIS_STORAGE_KEY, 'true')
    window.localStorage.setItem(TARGET_CLUSTER_STORAGE_KEY, clusterId)
    setWaitingForAnalysis(true)
    try {
      const result = await triggerAnalyse({
        min_cluster_size: 5,
        skip_eval: false,
        no_llm_labels: true,
        cluster_ids: [Number(clusterId)],
      })
      setActionMsg(
        result?.message
          ? `${result.message} for cluster ${clusterId}. We will keep checking for the report automatically.`
          : `Targeted evaluation started for cluster ${clusterId} from the saved snapshot. We will keep checking for the report automatically.`
      )
    } catch (e: any) {
      window.localStorage.removeItem(ANALYSIS_STORAGE_KEY)
      window.localStorage.removeItem(TARGET_CLUSTER_STORAGE_KEY)
      setWaitingForAnalysis(false)
      setActionMsg(e?.message || `Failed to start evaluation for cluster ${clusterId}.`)
      setReportClusterId(null)
    } finally {
      setEvaluatingClusterId(null)
    }
  }

  const handleEvaluateAll = async () => {
    setEvaluatingAll(true)
    setEvaluatingClusterId(null)
    setReportClusterId(null)
    setTargetedRunReady(false)
    setActionMsg('')
    setWaitingForAnalysis(true)
    window.localStorage.setItem(ANALYSIS_STORAGE_KEY, 'true')
    window.localStorage.removeItem(TARGET_CLUSTER_STORAGE_KEY)

    try {
      let baseline: string | null = null
      try {
        const report = await fetchReport()
        baseline = report?.generated_at ?? null
      } catch {
        baseline = null
      }
      setFullReportBaseline(baseline)

      const result = await triggerAnalyse({
        min_cluster_size: 5,
        skip_eval: false,
        no_llm_labels: true,
      })
      setActionMsg(
        result?.message
          ? `${result.message} for all clusters. We will keep checking for the refreshed report automatically.`
          : 'Started evaluation for all clusters. We will keep checking for the refreshed report automatically.'
      )
    } catch (e: any) {
      setEvaluatingAll(false)
      setWaitingForAnalysis(false)
      window.localStorage.removeItem(ANALYSIS_STORAGE_KEY)
      setActionMsg(e?.message || 'Failed to start evaluate all.')
    }
  }

  // Filter points by selected cluster
  const visiblePoints = selected
    ? data?.points.filter(p => String(p.cluster_id) === selected) ?? []
    : data?.points ?? []

  return (
    <PageShell maxWidth={920}>
      <ProjectScopeBar selectedProjectId={selectedProjectId} onChange={setSelectedProjectId} />
      <PageHeader
        tag="pipeline"
        title="CLUSTER MAP"
        description={`${data?.points.length ?? 0} prompts → ${data?.n_clusters ?? 0} task clusters${(data?.n_noise ?? 0) > 0 ? ` (${data?.n_noise} noise excluded)` : ''}`}
        right={
          evaluatingAll ? (
            <AnimatedActionButton onClick={() => {}} label="EVALUATING..." icon="spinner" disabled active />
          ) : (
            <AnimatedActionButton
              onClick={handleEvaluateAll}
              label={selectedProjectId && selectedProjectId !== activeProjectId ? 'READ-ONLY' : 'EVALUATE ALL'}
              icon="play"
              disabled={evaluatingAll || (!!selectedProjectId && selectedProjectId !== activeProjectId)}
            />
          )
        }
      />

      {/* Action / selection status */}
      {(actionMsg || (selected && selectedInfo)) && (
        <TerminalCard>
          {selected && selectedInfo && (
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 12, marginBottom: actionMsg ? 10 : 0 }}>
              <div>
                <div style={{ fontSize: 13, fontWeight: 700, color: '#6C63FF' }}>
                  Selected: {data?.cluster_names?.[selected] ?? `cluster_${selected}`}
                </div>
                <div style={{ fontSize: 11, color: 'var(--text-secondary)', marginTop: 4 }}>
                  {selectedInfo.size ?? 0} prompts · targeted eval reuses the saved snapshot
                </div>
                {reportClusterId === selected && !targetedRunReady && (
                  <div style={{ fontSize: 11, color: 'var(--terminal-amber)', marginTop: 4 }}>
                    Evaluation in progress...
                  </div>
                )}
              </div>
              <SecondaryButton
                onClick={() => handleEvaluateCluster(selected)}
                disabled={!!(selectedProjectId && selectedProjectId !== activeProjectId) || evaluatingClusterId === selected || (reportClusterId === selected && !targetedRunReady)}
              >
                {evaluatingClusterId === selected ? 'STARTING...' : (reportClusterId === selected && !targetedRunReady) ? 'RUNNING...' : 'EVALUATE'}
              </SecondaryButton>
            </div>
          )}
          {actionMsg && (
            <div style={{ fontSize: 11, color: 'var(--text-secondary)' }}>
              {actionMsg}
              {reportClusterId && targetedRunReady && (
                <div style={{ marginTop: 6 }}>
                  <Link href={`/report?cluster_id=${reportClusterId}`} style={{ color: 'var(--terminal-green)', fontWeight: 700 }}>
                    → Open targeted report
                  </Link>
                </div>
              )}
            </div>
          )}
        </TerminalCard>
      )}

      {/* Cluster filter pills */}
      <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', alignItems: 'center' }}>
        <button
          onClick={() => setSelected(null)}
          className={!selected ? 'btn btn-secondary' : 'btn'}
          style={{ padding: '3px 10px', fontSize: 10 }}
        >
          ALL
        </button>
        {(showAllPills ? clusterIds : clusterIds.slice(0, 10)).map(cid => {
          const info = data?.clusters?.[cid]
          const color = data?.points.find(p => String(p.cluster_id) === cid)?.color ?? 'var(--terminal-green)'
          const active = selected === cid
          return (
            <button
              key={cid}
              onClick={() => setSelected(active ? null : cid)}
              className="btn"
              style={{
                padding: '3px 10px', fontSize: 10,
                borderColor: active ? color : undefined,
                color: active ? color : undefined,
                display: 'flex', alignItems: 'center', gap: 5,
              }}
            >
              <span style={{ width: 6, height: 6, background: color, display: 'inline-block' }} />
              {data?.cluster_names[cid] ?? `cluster_${cid}`}
              <span style={{ opacity: 0.5 }}>({info?.size ?? 0})</span>
            </button>
          )
        })}
        {clusterIds.length > 10 && (
          <button
            onClick={() => setShowAllPills(v => !v)}
            className="btn"
            style={{ padding: '3px 12px', fontSize: 10, color: '#6C63FF', fontWeight: 700 }}
          >
            {showAllPills ? 'SHOW LESS' : `SEE ALL (${clusterIds.length})`}
          </button>
        )}
      </div>

      {/* Scatter plot */}
      <TerminalCard title="EMBEDDING SPACE">
        <div style={{ fontSize: 10, color: 'var(--text-tertiary)', marginBottom: 8 }}>
          Each dot = one LLM call. Hover to see the prompt. Nearby dots = similar prompts.
        </div>
        <ResponsiveContainer width="100%" height={380}>
          <ScatterChart margin={{ top: 10, right: 20, bottom: 10, left: 0 }}>
            <XAxis dataKey="x" type="number" tick={false} axisLine={false} tickLine={false} />
            <YAxis dataKey="y" type="number" tick={false} axisLine={false} tickLine={false} />
            <Tooltip content={<CustomTooltip />} />
            <Scatter data={visiblePoints} shape={<CustomDot />} />
          </ScatterChart>
        </ResponsiveContainer>
      </TerminalCard>

      {/* Cluster info cards */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 10 }}>
        {(showAllCards ? clusterIds : clusterIds.slice(0, 9)).map(cid => {
          const info = data?.clusters?.[cid]
          const name = data?.cluster_names?.[cid] ?? `cluster_${cid}`
          const color = data?.points.find(p => String(p.cluster_id) === cid)?.color ?? 'var(--terminal-green)'
          const isSel = selected === cid
          return (
            <div
              key={cid}
              className="card"
              style={{
                padding: '12px 14px',
                cursor: 'pointer',
                borderColor: isSel ? color : undefined,
              }}
              onClick={() => setSelected(isSel ? null : cid)}
            >
              <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8, marginBottom: 6 }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                  <span style={{ width: 7, height: 7, background: color }} />
                  <div style={{ fontSize: 11, fontWeight: 700, color: isSel ? color : '#3D4852' }}>{name}</div>
                </div>
                <button
                  onClick={(e) => { e.stopPropagation(); handleEvaluateCluster(cid) }}
                  disabled={!!(selectedProjectId && selectedProjectId !== activeProjectId) || evaluatingClusterId === cid || (reportClusterId === cid && !targetedRunReady)}
                  className="btn"
                  style={{ padding: '2px 8px', fontSize: 9, color: 'var(--terminal-green)', borderColor: 'var(--terminal-green)' }}
                >
                  {evaluatingClusterId === cid ? 'STARTING' : (reportClusterId === cid && !targetedRunReady) ? 'RUNNING' : 'EVAL'}
                </button>
              </div>
              <div style={{ fontSize: 10, color: 'var(--text-tertiary)', lineHeight: 1.6 }}>
                {info?.size ?? 0} prompts
                {info?.avg_latency_ms ? ` · ${Math.round(info.avg_latency_ms)}ms avg` : ''}
              </div>
              {info?.sample_prompts?.[0] && (
                <div style={{
                  marginTop: 6, fontSize: 10, color: 'var(--text-secondary)',
                  lineHeight: 1.4,
                  background: 'var(--bg-secondary)', padding: '4px 6px',
                    borderLeft: `3px solid ${color}`,
                    borderRadius: '0 12px 12px 0',
                }}>
                  &quot;{info.sample_prompts[0].slice(0, 70)}...&quot;
                </div>
              )}
            </div>
          )
        })}
      </div>
      {clusterIds.length > 9 && (
        <div style={{ textAlign: 'center', marginTop: 4 }}>
          <button
            onClick={() => setShowAllCards(v => !v)}
            style={{
              padding: '6px 24px', fontSize: 11, fontWeight: 700,
              background: '#E0E5EC', border: 'none', borderRadius: 14,
              boxShadow: '5px 5px 10px rgb(163,177,198,0.6), -5px -5px 10px rgba(255,255,255,0.5)',
              color: '#6C63FF', cursor: 'pointer', letterSpacing: '0.04em',
            }}
          >
            {showAllCards ? 'SHOW LESS' : `SEE ALL CLUSTERS (${clusterIds.length})`}
          </button>
        </div>
      )}
    </PageShell>
  )
}

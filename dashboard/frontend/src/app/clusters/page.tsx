'use client'
import { useEffect, useState } from 'react'
import Link from 'next/link'
import ProjectScopeBar from '@/components/ProjectScopeBar'
import { ScatterChart, Scatter, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell } from 'recharts'
import { fetchClusters, fetchPublicProjectClusters, fetchPublicProjects, fetchReport, triggerAnalyse } from '@/lib/api'

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
      background: 'var(--bg-primary)',
      border: '0.5px solid var(--border)',
      borderRadius: 8, padding: '10px 12px',
      fontSize: 12, maxWidth: 260,
      boxShadow: '0 4px 12px rgba(0,0,0,0.1)',
    }}>
      <div style={{ fontWeight: 500, color: 'var(--text-primary)', marginBottom: 4 }}>
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

  if (loading) return <div style={{ color: 'var(--text-tertiary)', padding: 40, textAlign: 'center' }}>Loading cluster map...</div>

  if (error) return (
    <div className="card" style={{ padding: 32, textAlign: 'center' }}>
      <div style={{ fontSize: 15, fontWeight: 500, color: 'var(--text-primary)', marginBottom: 8 }}>
        {waitingForAnalysis ? 'Analysis is still running' : 'No cluster data yet'}
      </div>
      <div style={{ fontSize: 13, color: 'var(--text-secondary)' }}>
        {waitingForAnalysis ? 'This page refreshes automatically every 5 seconds.' : <>Run: <code>agentshrink analyse</code></>}
      </div>
    </div>
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
    <div style={{ maxWidth: 900 }}>
      <ProjectScopeBar selectedProjectId={selectedProjectId} onChange={setSelectedProjectId} />
      <div style={{ marginBottom: 24 }}>
        <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: 12 }}>
          <div>
            <h1 style={{ fontSize: 22, fontWeight: 500, color: 'var(--text-primary)', marginBottom: 4 }}>Cluster Map</h1>
            <div style={{ fontSize: 13, color: 'var(--text-secondary)' }}>
              {data?.points.length ?? 0} prompts {'->'} {data?.n_clusters ?? 0} task clusters
              {(data?.n_noise ?? 0) > 0 && ` (${data?.n_noise} noise points excluded)`}
            </div>
          </div>
          <button
            onClick={handleEvaluateAll}
            disabled={evaluatingAll || (!!selectedProjectId && selectedProjectId !== activeProjectId)}
            style={{
              background: '#1D9E75',
              color: 'white',
              border: 'none',
              borderRadius: 8,
              padding: '9px 14px',
              fontSize: 12,
              fontWeight: 600,
              cursor: evaluatingAll ? 'default' : 'pointer',
              opacity: evaluatingAll ? 0.7 : 1,
              flexShrink: 0,
            }}
          >
            {selectedProjectId && selectedProjectId !== activeProjectId ? 'Read-only scope' : (evaluatingAll ? 'Evaluating all...' : 'Evaluate All')}
          </button>
        </div>
        <div style={{ fontSize: 12, color: 'var(--text-tertiary)', marginTop: 8 }}>
          {selectedProjectId && selectedProjectId !== activeProjectId
            ? 'This is a saved project-scoped cluster view. Switch back to the active project to run fresh evaluation.'
            : 'Use individual `Evaluate` buttons for targeted reports, or `Evaluate All` to refresh the main replaceability report for every current cluster.'}
        </div>
      </div>

      {(actionMsg || selected) && (
        <div className="card" style={{ padding: '12px 14px', marginBottom: 16 }}>
          {selected && selectedInfo && (
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 12, marginBottom: actionMsg ? 10 : 0 }}>
              <div>
                <div style={{ fontSize: 13, fontWeight: 500, color: 'var(--text-primary)' }}>
                  Selected cluster: {data?.cluster_names?.[selected] ?? `cluster_${selected}`}
                </div>
                <div style={{ fontSize: 12, color: 'var(--text-secondary)' }}>
                  {selectedInfo.size ?? 0} prompts. A targeted run reuses the saved clustering snapshot, evaluates only this cluster, and saves a separate report file.
                </div>
                {reportClusterId === selected && !targetedRunReady && (
                  <div style={{ fontSize: 11, color: '#1D9E75', marginTop: 6 }}>
                    Evaluation in progress from the saved cluster snapshot. The page will auto-detect when the targeted report is ready.
                  </div>
                )}
              </div>
              <button
                onClick={() => handleEvaluateCluster(selected)}
                disabled={!!selectedProjectId && selectedProjectId !== activeProjectId || evaluatingClusterId === selected || (reportClusterId === selected && !targetedRunReady)}
                style={{
                  background: '#1D9E75',
                  color: 'white',
                  border: 'none',
                  borderRadius: 8,
                  padding: '8px 14px',
                  fontSize: 12,
                  fontWeight: 500,
                  cursor: (!!selectedProjectId && selectedProjectId !== activeProjectId) || (evaluatingClusterId === selected || (reportClusterId === selected && !targetedRunReady)) ? 'default' : 'pointer',
                  opacity: (!!selectedProjectId && selectedProjectId !== activeProjectId) || (evaluatingClusterId === selected || (reportClusterId === selected && !targetedRunReady)) ? 0.7 : 1,
                  flexShrink: 0,
                }}
              >
                {selectedProjectId && selectedProjectId !== activeProjectId ? 'Read-only' : (evaluatingClusterId === selected ? 'Starting...' : (reportClusterId === selected && !targetedRunReady) ? 'Running...' : 'Evaluate Cluster')}
              </button>
            </div>
          )}
          {actionMsg && (
            <div style={{ fontSize: 12, color: 'var(--text-secondary)' }}>
              <div>{actionMsg}</div>
              {reportClusterId && targetedRunReady && (
                <div style={{ marginTop: 6 }}>
                  <Link href={`/report?cluster_id=${reportClusterId}`} style={{ color: '#1D9E75', fontWeight: 500 }}>
                    Open targeted report
                  </Link>
                </div>
              )}
            </div>
          )}
        </div>
      )}

      {/* Cluster filter pills */}
      <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginBottom: 16 }}>
        <button
          onClick={() => setSelected(null)}
          style={{
            fontSize: 11, padding: '3px 10px', borderRadius: 20, cursor: 'pointer',
            border: `0.5px solid ${!selected ? '#7F77DD' : 'var(--border)'}`,
            background: !selected ? '#EEEDFE' : 'transparent',
            color: !selected ? '#3C3489' : 'var(--text-secondary)',
          }}
        >
          All clusters
        </button>
        {clusterIds.map(cid => {
          const info = data?.clusters?.[cid]
          const color = data?.points.find(p => String(p.cluster_id) === cid)?.color ?? '#888'
          const active = selected === cid
          return (
            <button
              key={cid}
              onClick={() => setSelected(active ? null : cid)}
              style={{
                fontSize: 11, padding: '3px 10px', borderRadius: 20, cursor: 'pointer',
                border: `0.5px solid ${active ? color : 'var(--border)'}`,
                background: active ? color + '22' : 'transparent',
                color: active ? color : 'var(--text-secondary)',
                display: 'flex', alignItems: 'center', gap: 5,
              }}
            >
              <span style={{ width: 7, height: 7, borderRadius: '50%', background: color, display: 'inline-block' }} />
              {data?.cluster_names[cid] ?? `cluster_${cid}`}
              <span style={{ opacity: 0.6 }}>({info?.size ?? 0})</span>
            </button>
          )
        })}
      </div>

      {/* Scatter plot */}
      <div className="card" style={{ padding: '16px 8px 8px', marginBottom: 20 }}>
        <div style={{ padding: '0 12px 10px', fontSize: 11, color: 'var(--text-tertiary)' }}>
          Each dot = one LLM call. Hover to see the prompt. Nearby dots = similar prompts.
        </div>
        <ResponsiveContainer width="100%" height={400}>
          <ScatterChart margin={{ top: 10, right: 20, bottom: 10, left: 0 }}>
            <XAxis dataKey="x" type="number" tick={false} axisLine={false} tickLine={false} />
            <YAxis dataKey="y" type="number" tick={false} axisLine={false} tickLine={false} />
            <Tooltip content={<CustomTooltip />} />
            <Scatter data={visiblePoints} shape={<CustomDot />} />
          </ScatterChart>
        </ResponsiveContainer>
      </div>

      {/* Cluster info cards */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 10 }}>
        {clusterIds.map(cid => {
          const info = data?.clusters?.[cid]
          const name = data?.cluster_names?.[cid] ?? `cluster_${cid}`
          const color = data?.points.find(p => String(p.cluster_id) === cid)?.color ?? '#888'
          return (
            <div
              key={cid}
              className="card"
              style={{
                padding: '12px 14px',
                cursor: 'pointer',
                borderColor: selected === cid ? color : undefined,
              }}
              onClick={() => setSelected(selected === cid ? null : cid)}
            >
              <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: 8, marginBottom: 6 }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 7 }}>
                  <span style={{ width: 8, height: 8, borderRadius: '50%', background: color, flexShrink: 0 }} />
                  <div style={{ fontSize: 12, fontWeight: 500, color: 'var(--text-primary)' }}>{name}</div>
                </div>
                <button
                  onClick={(e) => {
                    e.stopPropagation()
                    handleEvaluateCluster(cid)
                  }}
                  disabled={!!selectedProjectId && selectedProjectId !== activeProjectId || evaluatingClusterId === cid || (reportClusterId === cid && !targetedRunReady)}
                  style={{
                    background: 'transparent',
                    color: '#1D9E75',
                    border: '0.5px solid #1D9E75',
                    borderRadius: 999,
                    padding: '3px 8px',
                    fontSize: 10,
                    fontWeight: 500,
                    cursor: (!!selectedProjectId && selectedProjectId !== activeProjectId) || (evaluatingClusterId === cid || (reportClusterId === cid && !targetedRunReady)) ? 'default' : 'pointer',
                    opacity: (!!selectedProjectId && selectedProjectId !== activeProjectId) || (evaluatingClusterId === cid || (reportClusterId === cid && !targetedRunReady)) ? 0.6 : 1,
                    flexShrink: 0,
                  }}
                >
                  {selectedProjectId && selectedProjectId !== activeProjectId ? 'Read-only' : (evaluatingClusterId === cid ? 'Starting...' : (reportClusterId === cid && !targetedRunReady) ? 'Running...' : 'Evaluate')}
                </button>
              </div>
              <div style={{ fontSize: 11, color: 'var(--text-tertiary)', lineHeight: 1.6 }}>
                {info?.size ?? 0} prompts<br />
                {info?.avg_latency_ms ? `${Math.round(info.avg_latency_ms)}ms avg` : ''}
              </div>
              {info?.sample_prompts?.[0] && (
                <div style={{
                  marginTop: 8, fontSize: 11, color: 'var(--text-secondary)',
                  fontStyle: 'italic', lineHeight: 1.4,
                  background: 'var(--bg-secondary)', padding: '6px 8px', borderRadius: 4,
                }}>
                  "{info.sample_prompts[0].slice(0, 70)}..."
                </div>
              )}
            </div>
          )
        })}
      </div>
    </div>
  )
}

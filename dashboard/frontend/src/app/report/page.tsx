'use client'
import { Suspense, useEffect, useRef, useState } from 'react'
import { useSearchParams } from 'next/navigation'
import { applyReport, createRoutingWebSocket, fetchAnalysisLogs, fetchReport, fetchRoutingSimulation, rollbackRoutingConfig } from '@/lib/api'

const REC_CONFIG: Record<string, { label: string; color: string; bg: string }> = {
  replace_now: { label: 'Replace now', color: '#27500A', bg: '#EAF3DE' },
  fine_tune: { label: 'Fine-tune', color: '#633806', bg: '#FAEEDA' },
  keep_llm: { label: 'Keep on API', color: '#A32D2D', bg: '#FCEBEB' },
}

function QualityBar({ score }: { score: number }) {
  const pct = Math.round(score * 100)
  const color = pct >= 85 ? '#1D9E75' : pct >= 60 ? '#EF9F27' : '#D85A30'
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
      <div style={{ width: 72, height: 5, background: 'var(--border)', borderRadius: 3, overflow: 'hidden' }}>
        <div style={{ width: `${pct}%`, height: '100%', background: color, borderRadius: 3 }} />
      </div>
      <span style={{ fontSize: 12, fontWeight: 500, color }}>{pct}%</span>
    </div>
  )
}

function ReportPageContent() {
  const searchParams = useSearchParams()
  const clusterIdParam = searchParams.get('cluster_id')
  const targetedClusterId = clusterIdParam ? Number(clusterIdParam) : undefined
  const [report, setReport] = useState<any>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [expanded, setExpanded] = useState<number | null>(null)
  const [applying, setApplying] = useState(false)
  const [applyMsg, setApplyMsg] = useState('')
  const [simulation, setSimulation] = useState<any>(null)
  const [simulationError, setSimulationError] = useState('')
  const [rollingBack, setRollingBack] = useState(false)
  const [logLines, setLogLines] = useState<Array<{ line: string; stream: string; timestamp?: number }>>([])
  const [analysisRunning, setAnalysisRunning] = useState(false)
  const terminalEndRef = useRef<HTMLDivElement | null>(null)

  useEffect(() => {
    fetchReport(Number.isFinite(targetedClusterId) ? targetedClusterId : undefined)
      .then(setReport)
      .catch(e => setError(e.message))
      .finally(() => setLoading(false))
  }, [targetedClusterId])

  useEffect(() => {
    if (Number.isFinite(targetedClusterId)) return
    fetchRoutingSimulation()
      .then(setSimulation)
      .catch(e => setSimulationError(e.message))
  }, [targetedClusterId])

  useEffect(() => {
    fetchAnalysisLogs()
      .then((data) => {
        setLogLines(data?.lines ?? [])
        setAnalysisRunning(Boolean(data?.running))
      })
      .catch(() => {})

    const ws = createRoutingWebSocket(
      (data) => {
        if (data.type === 'analysis_log') {
          setLogLines(prev => [...prev.slice(-399), {
            line: data.line ?? '',
            stream: data.stream ?? 'stdout',
            timestamp: data.timestamp,
          }])
        } else if (data.type === 'analysis_complete') {
          setAnalysisRunning(false)
        } else if (data.type === 'analysis_error') {
          setAnalysisRunning(false)
          setLogLines(prev => [...prev.slice(-399), {
            line: data.message ?? 'Analysis failed',
            stream: 'stderr',
            timestamp: data.timestamp,
          }])
        } else if (data.type === 'analysis_progress') {
          setAnalysisRunning(true)
        }
      },
      () => {}
    )

    return () => ws.close()
  }, [])

  useEffect(() => {
    terminalEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [logLines])

  if (loading) return <div style={{ color: 'var(--text-tertiary)', padding: 40, textAlign: 'center' }}>Loading report...</div>
  if (error) return (
    <div className="card" style={{ padding: 32, textAlign: 'center' }}>
      <div style={{ fontSize: 15, fontWeight: 500, color: 'var(--text-primary)', marginBottom: 8 }}>No report yet</div>
      <div style={{ fontSize: 13, color: 'var(--text-secondary)' }}>Run: <code>agentshrink analyse</code></div>
    </div>
  )

  const summary = report?.summary ?? {}
  const clusters = report?.clusters ?? []
  const heuristic = report?.heuristic === true

  const handleApply = async () => {
    setApplying(true)
    setApplyMsg('')
    try {
      const res = await applyReport()
      setApplyMsg(res?.message ?? 'Report applied.')
      fetchRoutingSimulation().then(setSimulation).catch(() => {})
    } catch {
      setApplyMsg('Failed to apply report.')
    } finally {
      setApplying(false)
    }
  }

  const handleRollback = async () => {
    setRollingBack(true)
    setApplyMsg('')
    try {
      const res = await rollbackRoutingConfig()
      setApplyMsg(res?.message ?? 'Routing config rolled back.')
      fetchRoutingSimulation().then(setSimulation).catch(() => {})
    } catch {
      setApplyMsg('Failed to rollback routing config.')
    } finally {
      setRollingBack(false)
    }
  }

  return (
    <div style={{ maxWidth: 900 }}>
      <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', marginBottom: 24 }}>
        <div>
          <h1 style={{ fontSize: 22, fontWeight: 500, color: 'var(--text-primary)', marginBottom: 4 }}>
            {Number.isFinite(targetedClusterId) ? `Cluster ${targetedClusterId} Report` : 'Replaceability Report'}
          </h1>
          <div style={{ fontSize: 13, color: 'var(--text-secondary)' }}>
            Generated at {report?.generated_at?.slice(0, 10)}
          </div>
        </div>
        <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
          {!Number.isFinite(targetedClusterId) && (
            <button
              onClick={handleRollback}
              disabled={rollingBack || !(simulation?.has_backup)}
              style={{
                background: 'transparent', color: 'var(--text-primary)', border: '0.5px solid var(--border)',
                borderRadius: 8, padding: '8px 14px', fontSize: 12,
                fontWeight: 500, cursor: 'pointer', opacity: rollingBack || !(simulation?.has_backup) ? 0.6 : 1,
              }}
            >
              {rollingBack ? 'Rolling back...' : 'Rollback'}
            </button>
          )}
          <button
            onClick={handleApply}
            disabled={applying}
            style={{
              background: '#1D9E75', color: 'white', border: 'none',
              borderRadius: 8, padding: '8px 18px', fontSize: 12,
              fontWeight: 500, cursor: 'pointer', opacity: applying ? 0.7 : 1,
            }}
          >
            {applying ? 'Applying...' : 'Apply Report ->'}
          </button>
        </div>
      </div>

      {(heuristic || applyMsg) && (
        <div className="card" style={{ padding: '10px 14px', marginBottom: 16, fontSize: 12, color: 'var(--text-secondary)' }}>
          {Number.isFinite(targetedClusterId) && <div style={{ marginBottom: heuristic || applyMsg ? 8 : 0 }}>Showing a targeted report for cluster {targetedClusterId}.</div>}
          {heuristic && <div>This is a heuristic local-only report because full evaluator mode was skipped.</div>}
          {applyMsg && <div>{applyMsg}</div>}
        </div>
      )}

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 10, marginBottom: 24 }}>
        <div className="metric-card">
          <div className="metric-num" style={{ color: '#1D9E75' }}>
            {summary.pct_calls_replaceable_now ?? 0}%
          </div>
          <div className="metric-label">calls replaceable now</div>
        </div>
        <div className="metric-card">
          <div className="metric-num" style={{ color: '#7F77DD' }}>
            {summary.pct_calls_replaceable_with_finetune ?? 0}%
          </div>
          <div className="metric-label">with fine-tuning</div>
        </div>
        <div className="metric-card">
          <div className="metric-num">
            {summary.replace_now_count ?? 0}/{summary.total_clusters ?? 0}
          </div>
          <div className="metric-label">clusters {'->'} replace now</div>
        </div>
      </div>

      {!Number.isFinite(targetedClusterId) && (
        <div className="card" style={{ padding: 16, marginBottom: 20 }}>
          <div style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-secondary)', marginBottom: 10 }}>
            Routing simulation
          </div>
          {simulationError ? (
            <div style={{ fontSize: 12, color: '#A32D2D' }}>{simulationError}</div>
          ) : simulation ? (
            <>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 10, marginBottom: 14 }}>
                <div className="metric-card">
                  <div className="metric-num">{simulation.summary.changed}</div>
                  <div className="metric-label">changed</div>
                </div>
                <div className="metric-card">
                  <div className="metric-num">{simulation.summary.added}</div>
                  <div className="metric-label">added</div>
                </div>
                <div className="metric-card">
                  <div className="metric-num">{simulation.summary.unchanged}</div>
                  <div className="metric-label">unchanged</div>
                </div>
                <div className="metric-card">
                  <div className="metric-num">{simulation.has_backup ? 'Yes' : 'No'}</div>
                  <div className="metric-label">rollback available</div>
                </div>
              </div>
              <div style={{ display: 'grid', gap: 8 }}>
                {(simulation.changes || []).filter((c: any) => c.change_type !== 'unchanged').slice(0, 8).map((change: any) => (
                  <div key={change.cluster_id} style={{ background: 'var(--bg-secondary)', borderRadius: 8, padding: '10px 12px' }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8, marginBottom: 4 }}>
                      <div style={{ fontSize: 13, fontWeight: 500, color: 'var(--text-primary)' }}>{change.cluster_name}</div>
                      <span className="badge" style={{
                        background: change.change_type === 'changed' ? '#FAEEDA' : '#EEEDFE',
                        color: change.change_type === 'changed' ? '#633806' : '#3C3489',
                      }}>
                        {change.change_type}
                      </span>
                    </div>
                    <div style={{ fontSize: 12, color: 'var(--text-secondary)', lineHeight: 1.7 }}>
                      <div>Before: <code>{change.before ? `${change.before.provider}:${change.before.model}` : 'none'}</code></div>
                      <div>After: <code>{change.after ? `${change.after.provider}:${change.after.model}` : 'none'}</code></div>
                    </div>
                    {change.explanation && (
                      <div style={{
                        marginTop: 8,
                        fontSize: 12,
                        color: 'var(--text-secondary)',
                        lineHeight: 1.6,
                        overflowWrap: 'anywhere',
                      }}>
                        Why: {change.explanation}
                      </div>
                    )}
                  </div>
                ))}
                {(simulation.changes || []).filter((c: any) => c.change_type !== 'unchanged').length === 0 && (
                  <div style={{ fontSize: 12, color: 'var(--text-tertiary)' }}>
                    Current routing config already matches the proposed report output.
                  </div>
                )}
              </div>
            </>
          ) : (
            <div style={{ fontSize: 12, color: 'var(--text-tertiary)' }}>Loading simulation...</div>
          )}
        </div>
      )}

      <div className="card" style={{ overflow: 'hidden' }}>
        <div style={{ padding: '14px 20px', borderBottom: '0.5px solid var(--border)', fontSize: 12, fontWeight: 500, color: 'var(--text-secondary)' }}>
          Cluster analysis
        </div>
        {clusters.map((cluster: any, i: number) => {
          const rec = REC_CONFIG[cluster.recommendation] ?? REC_CONFIG.keep_llm
          const isExpanded = expanded === i
          return (
            <div key={cluster.cluster_id}>
              <div
                style={{
                  display: 'grid',
                  gridTemplateColumns: '200px 1fr 100px 80px 120px 36px',
                  gap: 10, padding: '12px 20px',
                  borderBottom: '0.5px solid var(--border)',
                  alignItems: 'center', cursor: 'pointer',
                }}
                onClick={() => setExpanded(isExpanded ? null : i)}
              >
                <div style={{ fontSize: 13, fontWeight: 500, color: 'var(--text-primary)' }}>
                  {cluster.cluster_name}
                </div>
                <div style={{ fontSize: 12, color: 'var(--text-secondary)' }}>
                  {cluster.best_slm_display ?? `Keep ${cluster.incumbent_slm_display ?? 'incumbent baseline'}`}
                  {(cluster.best_provider || cluster.incumbent_provider) ? (
                    <span style={{ marginLeft: 6, color: 'var(--text-tertiary)', fontFamily: 'monospace' }}>
                      {cluster.best_provider ?? cluster.incumbent_provider}
                    </span>
                  ) : null}
                </div>
                <QualityBar score={cluster.best_score ?? cluster.incumbent_score ?? 0} />
                <div style={{ fontSize: 12, color: 'var(--text-secondary)', fontFamily: 'monospace' }}>
                  {cluster.cluster_size} calls
                </div>
                <div>
                  <span className="badge" style={{ background: rec.bg, color: rec.color }}>
                    {rec.label}
                  </span>
                </div>
                <div style={{ fontSize: 14, color: 'var(--text-tertiary)', textAlign: 'center' }}>
                  {isExpanded ? '▲' : '▼'}
                </div>
              </div>

              {isExpanded && (
                <div style={{ padding: '16px 20px', background: 'var(--bg-secondary)', borderBottom: '0.5px solid var(--border)' }}>
                  <div style={{ marginBottom: 14 }}>
                    {cluster.recommendation_explanation && (
                      <div style={{
                        background: rec.bg,
                        color: rec.color,
                        borderRadius: 8,
                        padding: '10px 12px',
                        fontSize: 12,
                        lineHeight: 1.6,
                        marginBottom: 10,
                      }}>
                        Why: {cluster.recommendation_explanation}
                      </div>
                    )}
                    <div style={{
                      background: 'var(--bg-primary)', borderRadius: 6,
                      padding: '10px 12px', border: '0.5px solid var(--border)', marginBottom: 10,
                    }}>
                      <div style={{ fontSize: 11, fontWeight: 500, color: 'var(--text-tertiary)', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: 6 }}>
                        Incumbent baseline
                      </div>
                      <div style={{ fontSize: 13, color: 'var(--text-primary)', fontWeight: 500 }}>
                        {cluster.incumbent_slm_display ?? '-'}
                      </div>
                      <div style={{ fontSize: 10, color: 'var(--text-tertiary)', marginTop: 4, fontFamily: 'monospace' }}>
                        {cluster.incumbent_provider}:{cluster.incumbent_slm}
                      </div>
                      <div style={{ marginTop: 6 }}>
                        <QualityBar score={cluster.incumbent_score ?? 0} />
                      </div>
                    </div>
                    <div style={{ fontSize: 11, fontWeight: 500, color: 'var(--text-tertiary)', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: 8 }}>
                      Model evaluation scores
                    </div>
                    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 8 }}>
                      {cluster.evaluations?.map((ev: any) => (
                        <div key={ev.slm_name} style={{
                          background: 'var(--bg-primary)', borderRadius: 6,
                          padding: '10px 12px', border: '0.5px solid var(--border)',
                        }}>
                          <div style={{ fontSize: 12, fontWeight: 500, color: 'var(--text-primary)', marginBottom: 6 }}>
                            {ev.slm_display}
                          </div>
                          <div style={{ fontSize: 10, color: 'var(--text-tertiary)', marginBottom: 6, fontFamily: 'monospace' }}>
                            {ev.provider}:{ev.slm_name}
                          </div>
                          {[
                            { label: 'Correctness', val: ev.correctness_score },
                            { label: 'Format', val: ev.format_score },
                            { label: 'Completeness', val: ev.completeness_score },
                            { label: 'Composite', val: ev.composite_score },
                            { label: 'Selection', val: ev.selection_score },
                          ].map(s => (
                            <div key={s.label} style={{ display: 'flex', justifyContent: 'space-between', fontSize: 11, color: 'var(--text-secondary)', marginBottom: 3 }}>
                              <span>{s.label}</span>
                              <span style={{ fontWeight: 500, color: s.val >= 0.85 ? '#1D9E75' : s.val >= 0.6 ? '#EF9F27' : '#D85A30' }}>
                                {Math.round(s.val * 100)}%
                              </span>
                            </div>
                          ))}
                          <div style={{ marginTop: 6, fontSize: 10, color: 'var(--text-tertiary)' }}>
                            {ev.avg_latency_ms?.toFixed(0)}ms avg · {ev.n_evaluated} samples · tier {ev.quality_tier}/5
                          </div>
                          <div style={{ marginTop: 4, fontSize: 10, color: 'var(--text-tertiary)' }}>
                            ${Number(ev.cost_in_per_1k ?? 0).toFixed(6)} in · ${Number(ev.cost_out_per_1k ?? 0).toFixed(6)} out
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>

                  {cluster.evaluations?.[0]?.sample_comparisons?.length > 0 && (
                    <div>
                      <div style={{ fontSize: 11, fontWeight: 500, color: 'var(--text-tertiary)', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: 8 }}>
                        Sample comparison (reference vs best local model)
                      </div>
                      {cluster.evaluations[0].sample_comparisons.slice(0, 1).map((cmp: any, j: number) => (
                        <div key={j} style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8 }}>
                          <div style={{ background: 'var(--bg-primary)', borderRadius: 6, padding: '10px 12px', border: '0.5px solid var(--border)' }}>
                            <div style={{ fontSize: 10, fontWeight: 500, color: '#993C1D', textTransform: 'uppercase', marginBottom: 6 }}>Reference response</div>
                            <div style={{ fontSize: 11, color: 'var(--text-secondary)', fontFamily: 'monospace', whiteSpace: 'pre-wrap' }}>{cmp.reference}</div>
                          </div>
                          <div style={{ background: 'var(--bg-primary)', borderRadius: 6, padding: '10px 12px', border: '0.5px solid #1D9E75' }}>
                            <div style={{ fontSize: 10, fontWeight: 500, color: '#0F6E56', textTransform: 'uppercase', marginBottom: 6 }}>Local model response</div>
                            <div style={{ fontSize: 11, color: 'var(--text-secondary)', fontFamily: 'monospace', whiteSpace: 'pre-wrap' }}>{cmp.candidate}</div>
                          </div>
                        </div>
                      ))}
                    </div>
                  )}

                  {cluster.needs_fine_tuning && (
                    <div style={{ marginTop: 12, padding: '8px 12px', background: '#FAEEDA', borderRadius: 6, fontSize: 12, color: '#633806' }}>
                      Fine-tuning needed on {cluster.fine_tune_base_model} to reach the target threshold.
                    </div>
                  )}
                </div>
              )}
            </div>
          )
        })}
      </div>

      <div className="card" style={{ marginTop: 20, overflow: 'hidden' }}>
        <div style={{
          padding: '12px 16px',
          borderBottom: '0.5px solid var(--border)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
        }}>
          <div style={{ fontSize: 12, fontWeight: 500, color: 'var(--text-secondary)' }}>
            Analysis Terminal
          </div>
          <div style={{ fontSize: 11, color: analysisRunning ? '#1D9E75' : 'var(--text-tertiary)' }}>
            {analysisRunning ? 'Running...' : 'Idle'}
          </div>
        </div>
        <div style={{
          background: '#121417',
          color: '#D7DEE7',
          fontFamily: 'ui-monospace, SFMono-Regular, Menlo, monospace',
          fontSize: 11,
          lineHeight: 1.5,
          maxHeight: 260,
          overflowY: 'auto',
          padding: '12px 14px',
        }}>
          {logLines.length === 0 ? (
            <div style={{ color: '#94A3B8' }}>
              No analysis logs yet. Start analysis from Overview or evaluate a cluster to stream logs here.
            </div>
          ) : (
            logLines.map((entry, idx) => (
              <div
                key={`${idx}-${entry.timestamp ?? idx}`}
                style={{
                  color:
                    entry.stream === 'stderr' ? '#FCA5A5' :
                    entry.stream === 'meta' ? '#93C5FD' :
                    '#D7DEE7',
                  whiteSpace: 'pre-wrap',
                  wordBreak: 'break-word',
                }}
              >
                {entry.line}
              </div>
            ))
          )}
          <div ref={terminalEndRef} />
        </div>
      </div>
    </div>
  )
}

export default function ReportPage() {
  return (
    <Suspense fallback={<div style={{ color: 'var(--text-tertiary)', padding: 40, textAlign: 'center' }}>Loading report...</div>}>
      <ReportPageContent />
    </Suspense>
  )
}

'use client'
import { Suspense, useEffect, useRef, useState } from 'react'
import { useSearchParams } from 'next/navigation'
import ProjectScopeBar from '@/components/ProjectScopeBar'
import { applyReport, createRoutingWebSocket, fetchAnalysisLogs, fetchPublicProjectReport, fetchPublicProjects, fetchReport, fetchRoutingSimulation, rollbackRoutingConfig } from '@/lib/api'
import {
  PageShell, PageHeader, TerminalCard, MetricRow, Metric, Badge,
  PrimaryButton, SecondaryButton, DangerButton,
  LoadingTerminal, ErrorBlock, EmptyState, Collapsible,
} from '@/components/Terminal'

const REC_CONFIG: Record<string, { label: string; variant: 'green' | 'amber' | 'red' }> = {
  replace_now: { label: 'REPLACE NOW', variant: 'green' },
  fine_tune: { label: 'FINE-TUNE', variant: 'amber' },
  keep_llm: { label: 'KEEP ON API', variant: 'red' },
}

function QualityBar({ score }: { score: number }) {
  const pct = Math.round(score * 100)
  const color = pct >= 85 ? 'var(--terminal-green)' : pct >= 60 ? 'var(--terminal-amber)' : 'var(--terminal-red)'
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
      <div style={{ width: 72, height: 4, background: 'var(--bg-tertiary)', overflow: 'hidden' }}>
        <div style={{ width: `${pct}%`, height: '100%', background: color }} />
      </div>
      <span style={{ fontSize: 11, fontWeight: 700, color }}>{pct}%</span>
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
  const [searchQuery, setSearchQuery] = useState('')
  const [filterRec, setFilterRec] = useState<string>('all')
  const [visibleCount, setVisibleCount] = useState(15)
  const [selectedProjectId, setSelectedProjectId] = useState('')
  const [activeProjectId, setActiveProjectId] = useState('')
  const [selectedProjectName, setSelectedProjectName] = useState('AgentShrink Project')
  const terminalEndRef = useRef<HTMLDivElement | null>(null)

  useEffect(() => {
    fetchPublicProjects().then((data) => {
      const activeId = data.active_project_id || ''
      setSelectedProjectId(activeId)
      setActiveProjectId(activeId)
      const active = (data.projects || []).find((project: any) => project.id === activeId)
      setSelectedProjectName(active?.name || 'AgentShrink Project')
    }).catch(() => {})
  }, [targetedClusterId])

  useEffect(() => {
    if (!selectedProjectId) return
    setLoading(true)
    if (selectedProjectId === activeProjectId || !activeProjectId) {
      fetchReport(Number.isFinite(targetedClusterId) ? targetedClusterId : undefined)
        .then(setReport)
        .catch(e => setError(e.message))
        .finally(() => setLoading(false))
      return
    }
    fetchPublicProjectReport(selectedProjectId)
      .then((data) => {
        setReport(data.report)
        setSelectedProjectName(data.project?.name || 'Selected project')
      })
      .catch(e => setError(e.message))
      .finally(() => setLoading(false))
  }, [targetedClusterId, selectedProjectId, activeProjectId])

  useEffect(() => {
    if (Number.isFinite(targetedClusterId)) return
    if (selectedProjectId && activeProjectId && selectedProjectId !== activeProjectId) return
    fetchRoutingSimulation()
      .then(setSimulation)
      .catch(e => setSimulationError(e.message))
  }, [targetedClusterId, selectedProjectId, activeProjectId])

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

  if (loading) return <LoadingTerminal message="loading report" />
  if (error) return <EmptyState message="No report yet. Run: agentshrink analyse" />

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
    <PageShell>
      <ProjectScopeBar selectedProjectId={selectedProjectId} onChange={setSelectedProjectId} />

      <PageHeader
        tag="pipeline"
        title={Number.isFinite(targetedClusterId) ? `CLUSTER ${targetedClusterId} REPORT` : 'REPLACEABILITY REPORT'}
        description={
          selectedProjectId && activeProjectId && selectedProjectId !== activeProjectId
            ? `Viewing saved report scope for ${selectedProjectName}`
            : `Generated at ${report?.generated_at?.slice(0, 10)}`
        }
        right={
          <div style={{ display: 'flex', gap: 8 }}>
            {!Number.isFinite(targetedClusterId) && !(selectedProjectId && activeProjectId && selectedProjectId !== activeProjectId) && (
              <SecondaryButton onClick={handleRollback} disabled={rollingBack || !(simulation?.has_backup)}>
                {rollingBack ? 'ROLLING BACK...' : 'ROLLBACK'}
              </SecondaryButton>
            )}
            <PrimaryButton
              onClick={handleApply}
              disabled={applying || !!(selectedProjectId && activeProjectId && selectedProjectId !== activeProjectId)}
            >
              {applying ? 'APPLYING...' : 'APPLY REPORT'}
            </PrimaryButton>
          </div>
        }
      />

      {(heuristic || applyMsg) && (
        <TerminalCard>
          {Number.isFinite(targetedClusterId) && <div style={{ fontSize: 11, color: 'var(--text-secondary)', marginBottom: 6 }}>Targeted report for cluster {targetedClusterId}.</div>}
          {heuristic && <div style={{ fontSize: 11, color: 'var(--terminal-amber)' }}>[WARN] Heuristic local-only report — full evaluator mode was skipped.</div>}
          {applyMsg && <div style={{ fontSize: 11, color: 'var(--text-secondary)' }}>{applyMsg}</div>}
        </TerminalCard>
      )}

      <MetricRow>
        <Metric label="replaceable now" value={`${summary.pct_calls_replaceable_now ?? 0}%`} color="var(--terminal-green)" />
        <Metric label="with fine-tuning" value={`${summary.pct_calls_replaceable_with_finetune ?? 0}%`} />
        <Metric label="replace clusters" value={`${summary.replace_now_count ?? 0}/${summary.total_clusters ?? 0}`} />
      </MetricRow>

      {!Number.isFinite(targetedClusterId) && (
        <TerminalCard title="ROUTING SIMULATION">
          {simulationError ? (
            <ErrorBlock message={simulationError} />
          ) : simulation ? (
            <>
              <MetricRow>
                <Metric label="changed" value={String(simulation.summary.changed)} />
                <Metric label="added" value={String(simulation.summary.added)} />
                <Metric label="unchanged" value={String(simulation.summary.unchanged)} />
                <Metric label="rollback" value={simulation.has_backup ? 'YES' : 'NO'} />
              </MetricRow>
              <div style={{ fontSize: 11, color: 'var(--text-tertiary)', marginTop: 10 }}>
                Apply to persist proposed routing changes, or rollback to restore previous config.
              </div>
            </>
          ) : (
            <div style={{ fontSize: 11, color: 'var(--text-tertiary)' }}>Loading simulation...</div>
          )}
        </TerminalCard>
      )}

      {/* Cluster analysis table */}
      <TerminalCard title="CLUSTER ANALYSIS" noPadding>
        {/* Search / Filter bar */}
        <div style={{
          display: 'flex', gap: 10, alignItems: 'center', padding: '10px 16px',
          borderBottom: '1px solid var(--border)', flexWrap: 'wrap',
        }}>
          <input
            type="text"
            placeholder="Search clusters..."
            value={searchQuery}
            onChange={e => { setSearchQuery(e.target.value); setVisibleCount(15) }}
            style={{
              flex: 1, minWidth: 180, padding: '6px 12px', fontSize: 12,
              background: '#E0E5EC', border: 'none', borderRadius: 12,
              boxShadow: 'inset 3px 3px 6px rgb(163,177,198,0.4), inset -3px -3px 6px rgba(255,255,255,0.3)',
              color: 'var(--text-primary)', outline: 'none',
            }}
          />
          <select
            value={filterRec}
            onChange={e => { setFilterRec(e.target.value); setVisibleCount(15) }}
            style={{
              padding: '6px 10px', fontSize: 11, fontWeight: 600,
              background: '#E0E5EC', border: 'none', borderRadius: 12,
              boxShadow: 'inset 3px 3px 6px rgb(163,177,198,0.4), inset -3px -3px 6px rgba(255,255,255,0.3)',
              color: 'var(--text-primary)', cursor: 'pointer', outline: 'none',
            }}
          >
            <option value="all">All Recommendations</option>
            <option value="replace_now">Replace Now</option>
            <option value="fine_tune">Fine-Tune</option>
            <option value="keep_llm">Keep on API</option>
          </select>
          <span style={{ fontSize: 10, color: 'var(--text-tertiary)' }}>
            {(() => {
              const filtered = clusters.filter((c: any) => {
                if (filterRec !== 'all' && c.recommendation !== filterRec) return false
                if (searchQuery && !c.cluster_name?.toLowerCase().includes(searchQuery.toLowerCase())) return false
                return true
              })
              return `${Math.min(visibleCount, filtered.length)} of ${filtered.length} shown`
            })()}
          </span>
        </div>

        {/* Scrollable cluster list */}
        <div style={{ maxHeight: 600, overflowY: 'auto' }}>
        {clusters
          .filter((c: any) => {
            if (filterRec !== 'all' && c.recommendation !== filterRec) return false
            if (searchQuery && !c.cluster_name?.toLowerCase().includes(searchQuery.toLowerCase())) return false
            return true
          })
          .slice(0, visibleCount)
          .map((cluster: any, i: number) => {
          const rec = REC_CONFIG[cluster.recommendation] ?? REC_CONFIG.keep_llm
          const isExpanded = expanded === i
          return (
            <div key={cluster.cluster_id}>
              <div
                style={{
                  display: 'grid',
                  gridTemplateColumns: '180px 1fr 100px 70px 110px 30px',
                  gap: 8, padding: '10px 16px',
                  borderBottom: '1px solid var(--border)',
                  alignItems: 'center', cursor: 'pointer',
                }}
                onClick={() => setExpanded(isExpanded ? null : i)}
              >
                <div style={{ fontSize: 11, fontWeight: 700, color: '#3D4852' }}>
                  {cluster.cluster_name}
                </div>
                <div style={{ fontSize: 11, color: 'var(--text-secondary)' }}>
                  {cluster.best_slm_display ?? `Keep ${cluster.incumbent_slm_display ?? 'baseline'}`}
                  {(cluster.best_provider || cluster.incumbent_provider) && (
                    <span style={{ marginLeft: 6, color: 'var(--text-tertiary)' }}>
                      {cluster.best_provider ?? cluster.incumbent_provider}
                    </span>
                  )}
                </div>
                <QualityBar score={cluster.best_score ?? cluster.incumbent_score ?? 0} />
                <div style={{ fontSize: 11, color: 'var(--text-tertiary)' }}>
                  {cluster.cluster_size}
                </div>
                <Badge variant={rec.variant}>{rec.label}</Badge>
                <div style={{ fontSize: 14, color: '#6C63FF', textAlign: 'center', fontWeight: 600 }}>
                  {isExpanded ? '−' : '+'}
                </div>
              </div>

              {isExpanded && (
                <div style={{ padding: '14px 16px', background: 'var(--bg-secondary)', borderBottom: '1px solid var(--border)' }}>
                  {cluster.recommendation_explanation && (
                    <div style={{
                      padding: '8px 10px',
                      fontSize: 11, lineHeight: 1.6,
                      color: 'var(--text-secondary)',
                      borderLeft: `3px solid var(--terminal-${rec.variant === 'amber' ? 'amber' : rec.variant === 'green' ? 'green' : 'red'})`,
                      borderRadius: '0 12px 12px 0',
                      marginBottom: 10,
                    }}>
                      Why: {cluster.recommendation_explanation}
                    </div>
                  )}

                  <div style={{ padding: '8px 10px', border: '1px solid var(--border)', marginBottom: 10 }}>
                    <div style={{ fontSize: 9, fontWeight: 700, color: 'var(--text-tertiary)', textTransform: 'uppercase', letterSpacing: '0.08em', marginBottom: 4 }}>
                      INCUMBENT BASELINE
                    </div>
                    <div style={{ fontSize: 12, color: '#3D4852', fontWeight: 700 }}>
                      {cluster.incumbent_slm_display ?? '-'}
                    </div>
                    <div style={{ fontSize: 10, color: 'var(--text-tertiary)', marginTop: 2 }}>
                      {cluster.incumbent_provider}:{cluster.incumbent_slm}
                    </div>
                    <div style={{ marginTop: 6 }}><QualityBar score={cluster.incumbent_score ?? 0} /></div>
                  </div>

                  <div style={{ fontSize: 9, fontWeight: 700, color: 'var(--text-tertiary)', textTransform: 'uppercase', letterSpacing: '0.08em', marginBottom: 8 }}>
                    MODEL EVALUATION SCORES
                  </div>
                  <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 8 }}>
                    {cluster.evaluations?.map((ev: any) => (
                      <div key={ev.slm_name} style={{ padding: '10px 12px', border: '1px solid var(--border)' }}>
                        <div style={{ fontSize: 11, fontWeight: 700, color: '#3D4852', marginBottom: 4 }}>
                          {ev.slm_display}
                        </div>
                        <div style={{ fontSize: 9, color: 'var(--text-tertiary)', marginBottom: 6 }}>
                          {ev.provider}:{ev.slm_name}
                        </div>
                        {[
                          { label: 'Correctness', val: ev.correctness_score },
                          { label: 'Format', val: ev.format_score },
                          { label: 'Completeness', val: ev.completeness_score },
                          { label: 'Composite', val: ev.composite_score },
                          { label: 'Selection', val: ev.selection_score },
                        ].map(s => (
                          <div key={s.label} style={{ display: 'flex', justifyContent: 'space-between', fontSize: 10, color: 'var(--text-secondary)', marginBottom: 2 }}>
                            <span>{s.label}</span>
                            <span style={{
                              fontWeight: 700,
                              color: s.val >= 0.85 ? 'var(--terminal-green)' : s.val >= 0.6 ? 'var(--terminal-amber)' : 'var(--terminal-red)',
                            }}>
                              {Math.round(s.val * 100)}%
                            </span>
                          </div>
                        ))}
                        <div style={{ marginTop: 6, fontSize: 9, color: 'var(--text-tertiary)' }}>
                          {ev.avg_latency_ms?.toFixed(0)}ms · {ev.n_evaluated} samples · tier {ev.quality_tier}/5
                        </div>
                        <div style={{ marginTop: 2, fontSize: 9, color: 'var(--text-tertiary)' }}>
                          ${Number(ev.cost_in_per_1k ?? 0).toFixed(6)} in · ${Number(ev.cost_out_per_1k ?? 0).toFixed(6)} out
                        </div>
                      </div>
                    ))}
                  </div>

                  {cluster.evaluations?.[0]?.sample_comparisons?.length > 0 && (
                    <Collapsible title={`Sample comparison (${cluster.evaluations[0].sample_comparisons.length})`}>
                      {cluster.evaluations[0].sample_comparisons.slice(0, 1).map((cmp: any, j: number) => (
                        <div key={j} style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8 }}>
                          <div style={{ padding: '8px 10px', border: '1px solid var(--terminal-red)' }}>
                            <div style={{ fontSize: 9, fontWeight: 700, color: 'var(--terminal-red)', textTransform: 'uppercase', marginBottom: 4 }}>Reference</div>
                            <div style={{ fontSize: 10, color: 'var(--text-secondary)', whiteSpace: 'pre-wrap' }}>{cmp.reference}</div>
                          </div>
                          <div style={{ padding: '8px 10px', border: '1px solid var(--terminal-green)' }}>
                            <div style={{ fontSize: 9, fontWeight: 700, color: 'var(--terminal-green)', textTransform: 'uppercase', marginBottom: 4 }}>Local model</div>
                            <div style={{ fontSize: 10, color: 'var(--text-secondary)', whiteSpace: 'pre-wrap' }}>{cmp.candidate}</div>
                          </div>
                        </div>
                      ))}
                    </Collapsible>
                  )}

                  {cluster.needs_fine_tuning && (
                    <div style={{ marginTop: 10, padding: '8px 12px', fontSize: 11, color: '#B7791F', borderLeft: '3px solid #D69E2E', borderRadius: '0 12px 12px 0', background: 'rgba(214,158,46,0.04)' }}>
                      Fine-tuning needed on {cluster.fine_tune_base_model} to reach the target threshold.
                    </div>
                  )}
                </div>
              )}
            </div>
          )
        })}
        </div>

        {/* Show More / Show Less */}
        {(() => {
          const filtered = clusters.filter((c: any) => {
            if (filterRec !== 'all' && c.recommendation !== filterRec) return false
            if (searchQuery && !c.cluster_name?.toLowerCase().includes(searchQuery.toLowerCase())) return false
            return true
          })
          return filtered.length > visibleCount ? (
            <div style={{ padding: '10px 16px', textAlign: 'center', borderTop: '1px solid var(--border)' }}>
              <button
                onClick={() => setVisibleCount(prev => prev + 15)}
                style={{
                  padding: '6px 24px', fontSize: 11, fontWeight: 700,
                  background: '#E0E5EC', border: 'none', borderRadius: 14,
                  boxShadow: '5px 5px 10px rgb(163,177,198,0.6), -5px -5px 10px rgba(255,255,255,0.5)',
                  color: '#6C63FF', cursor: 'pointer', letterSpacing: '0.04em',
                }}
              >
                SHOW MORE ({filtered.length - visibleCount} remaining)
              </button>
            </div>
          ) : null
        })()}
      </TerminalCard>

      {/* Analysis terminal */}
      <TerminalCard title="ANALYSIS TERMINAL" headerRight={
        <span style={{ fontSize: 10, color: analysisRunning ? 'var(--terminal-green)' : 'var(--text-tertiary)' }}>
          {analysisRunning ? '● RUNNING' : '○ IDLE'}
        </span>
      } noPadding>
        <div style={{
          background: 'var(--bg-primary)',
          color: 'var(--text-secondary)',
          fontSize: 11,
          lineHeight: 1.5,
          maxHeight: 240,
          overflowY: 'auto',
          padding: '12px 14px',
        }}>
          {logLines.length === 0 ? (
            <div style={{ color: 'var(--text-tertiary)' }}>
              No analysis logs yet. Start analysis from Overview or evaluate a cluster.
            </div>
          ) : (
            logLines.map((entry, idx) => (
              <div
                key={`${idx}-${entry.timestamp ?? idx}`}
                style={{
                  color:
                    entry.stream === 'stderr' ? 'var(--terminal-red)' :
                    entry.stream === 'meta' ? 'var(--terminal-blue)' :
                    'var(--text-secondary)',
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
      </TerminalCard>
    </PageShell>
  )
}

export default function ReportPage() {
  return (
    <Suspense fallback={<LoadingTerminal message="loading report" />}>
      <ReportPageContent />
    </Suspense>
  )
}

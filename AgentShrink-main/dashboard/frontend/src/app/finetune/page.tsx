'use client'

import type { CSSProperties } from 'react'
import { useEffect, useMemo, useState } from 'react'
import { LineChart, Line, CartesianGrid, XAxis, YAxis, Tooltip, ResponsiveContainer } from 'recharts'
import {
  PageShell, PageHeader, TerminalCard, MetricRow, Metric,
  Badge, PrimaryButton, SecondaryButton, FieldLabel,
  TerminalInput, TerminalSelect, ProgressBar,
  LoadingTerminal, ErrorBlock, EmptyState, Collapsible,
  AnimatedActionButton,
} from '@/components/Terminal'
import {
  deployFineTuneJob,
  fetchFineTuneBackends,
  fetchFineTuneJobs,
  fetchFineTunePreview,
  fetchReport,
  startFineTuneJob,
  stopFineTuneJob,
} from '@/lib/api'

export default function FinetunePage() {
  const [report, setReport] = useState<any>(null)
  const [backends, setBackends] = useState<any[]>([])
  const [jobs, setJobs] = useState<any[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [selectedClusterId, setSelectedClusterId] = useState<number | null>(null)
  const [selectedBackend, setSelectedBackend] = useState<string | null>(null)
  const [preview, setPreview] = useState<any>(null)
  const [previewLoading, setPreviewLoading] = useState(false)
  const [actionMsg, setActionMsg] = useState('')
  const [starting, setStarting] = useState(false)
  const [deploying, setDeploying] = useState(false)
  const [epochs, setEpochs] = useState(2)
  const [learningRate, setLearningRate] = useState('0.0002')
  const [baseModel, setBaseModel] = useState('')
  const [candidateSearch, setCandidateSearch] = useState('')
  const [candidateLimit, setCandidateLimit] = useState(10)

  useEffect(() => {
    Promise.all([fetchReport(), fetchFineTuneBackends(), fetchFineTuneJobs()])
      .then(([reportData, backendData, jobData]) => {
        setReport(reportData)
        setBackends(backendData.backends || [])
        setJobs(jobData.jobs || [])
      })
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false))
  }, [])

  const candidates = useMemo(
    () => (report?.clusters ?? []).filter((c: any) => c.recommendation === 'fine_tune'),
    [report]
  )
  const selectedCluster = candidates.find((c: any) => c.cluster_id === selectedClusterId) || null
  const selectedBackendInfo = backends.find((backend) => backend.id === selectedBackend) || null
  const selectedModelInfo = (selectedBackendInfo?.models || []).find((model: any) => model.id === baseModel) || null
  const clusterJobs = useMemo(() => {
    if (!selectedClusterId) return null
    return jobs.filter((job) => Number(job.cluster_id) === Number(selectedClusterId))
  }, [jobs, selectedClusterId])
  const latestJob = clusterJobs?.[0] || null
  const deployableJob = useMemo(() => {
    return clusterJobs?.find((job) => job.can_register && ['completed', 'stopped', 'deployed'].includes(job.status)) || null
  }, [clusterJobs])

  useEffect(() => {
    if (candidates.length > 0 && selectedClusterId === null) {
      setSelectedClusterId(candidates[0].cluster_id)
    }
  }, [candidates, selectedClusterId])

  useEffect(() => {
    if (!selectedClusterId) return
    setPreviewLoading(true)
    fetchFineTunePreview(selectedClusterId)
      .then(setPreview)
      .catch(() => setPreview(null))
      .finally(() => setPreviewLoading(false))
  }, [selectedClusterId])

  useEffect(() => {
    if (!selectedBackendInfo) return
    const defaultModel = selectedBackendInfo.models?.[0]
    setBaseModel(defaultModel?.id || '')
  }, [selectedBackendInfo])

  useEffect(() => {
    const hasActiveJob = jobs.some((job) => ['queued', 'running', 'deploying'].includes(job.status))
    if (!hasActiveJob) return

    const timer = window.setInterval(() => {
      fetchFineTuneJobs()
        .then((data) => setJobs(data.jobs || []))
        .catch(() => {})
    }, 3000)
    return () => window.clearInterval(timer)
  }, [jobs])

  const backendModelOptions = selectedBackendInfo?.models || []
  const canStart = !!selectedCluster && !!selectedBackend && !latestJobInFlight(latestJob)
  const canStop = latestJobInFlight(latestJob)
  const canDeploy = !!deployableJob && ['completed', 'stopped'].includes(deployableJob.status)
  const deployed = deployableJob?.status === 'deployed'

  const handleStartTraining = async () => {
    if (!selectedCluster || !selectedBackend) return
    setStarting(true)
    setActionMsg('')
    try {
      const chosenModel = backendModelOptions.find((model: any) => model.id === baseModel) || backendModelOptions[0]
      const res = await startFineTuneJob({
        cluster_id: selectedCluster.cluster_id,
        backend: selectedBackend,
        config: {
          base_model: chosenModel?.id,
          deploy_base_model: chosenModel?.deploy_base_model,
          epochs,
          learning_rate: Number(learningRate),
        },
      })
      setJobs((prev) => [res.job, ...prev.filter((job) => job.job_id !== res.job.job_id)])
      setActionMsg(`Started ${selectedBackend} training for ${selectedCluster.cluster_name}.`)
      window.setTimeout(() => {
        fetchFineTuneJobs()
          .then((data) => setJobs(data.jobs || []))
          .catch(() => {})
      }, 700)
    } catch (e: any) {
      setActionMsg(e.message || 'Failed to start fine-tune job.')
    } finally {
      setStarting(false)
    }
  }

  const handleStopTraining = async () => {
    if (!latestJob) return
    setActionMsg('')
    try {
      const res = await stopFineTuneJob(latestJob.job_id)
      setJobs((prev) => [res.job, ...prev.filter((job) => job.job_id !== res.job.job_id)])
      setActionMsg('Stop requested. The training backend will stop at the next safe checkpoint.')
    } catch (e: any) {
      setActionMsg(e.message || 'Failed to stop fine-tune job.')
    }
  }

  const handleDeploy = async () => {
    if (!deployableJob) return
    setDeploying(true)
    setActionMsg('')
    try {
      setJobs((prev) =>
        prev.map((job) =>
          job.job_id === deployableJob.job_id
            ? { ...job, status: 'deploying', phase: 'Preparing local deployment', progress: Math.max(8, job.progress || 0) }
            : job
        )
      )
      const res = await deployFineTuneJob(deployableJob.job_id)
      setJobs((prev) => [res.job, ...prev.filter((job) => job.job_id !== res.job.job_id)])
      setActionMsg('Deployment started. Progress and logs will keep updating below.')
    } catch (e: any) {
      setActionMsg(e.message || 'Failed to deploy fine-tuned model.')
    } finally {
      setDeploying(false)
    }
  }

  if (loading) return <LoadingTerminal message="loading fine-tune data" />
  if (error) return <ErrorBlock message={error} />

  // Workflow step tracker
  const currentStep = !selectedCluster ? 0 : !selectedBackend ? 1 : !latestJob ? 2 : deployed ? 4 : 3

  return (
    <PageShell>
      <PageHeader
        tag="training"
        title="FINE-TUNE"
        description="Select a cluster, choose a backend, train a local SLM, and deploy it to routing."
      />

      {/* ── Workflow Stepper ── */}
      <TerminalCard>
        <div style={{ display: 'flex', gap: 0, alignItems: 'center' }}>
          {['Select Cluster', 'Choose Backend', 'Configure', 'Train', 'Deploy'].map((step, i) => (
            <div key={step} style={{ display: 'flex', alignItems: 'center', flex: 1 }}>
              <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 4, flex: 1 }}>
                <div style={{
                  width: 28, height: 28, borderRadius: 9999,
                  display: 'flex', alignItems: 'center', justifyContent: 'center',
                  fontSize: 12, fontWeight: 700,
                  background: i <= currentStep ? '#6C63FF' : '#E0E5EC',
                  color: i <= currentStep ? '#fff' : '#9CA3AF',
                  boxShadow: i <= currentStep
                    ? '0 0 12px rgba(108,99,255,0.4)'
                    : 'inset 3px 3px 6px rgb(163,177,198,0.6), inset -3px -3px 6px rgba(255,255,255,0.5)',
                  transition: 'all 300ms ease-out',
                }}>
                  {i < currentStep ? '\u2713' : i + 1}
                </div>
                <span style={{ fontSize: 10, fontWeight: 600, color: i <= currentStep ? '#6C63FF' : '#9CA3AF', letterSpacing: '0.02em' }}>
                  {step}
                </span>
              </div>
              {i < 4 && (
                <div style={{
                  height: 2, flex: 1, minWidth: 20,
                  background: i < currentStep ? '#6C63FF' : '#d5dae2',
                  borderRadius: 9999, transition: 'background 300ms',
                }} />
              )}
            </div>
          ))}
        </div>
      </TerminalCard>

      {candidates.length === 0 ? (
        <TerminalCard title="STATUS">
          <EmptyState
            message="No fine-tune candidates right now"
            hint="Run analysis after collecting more calls to produce fine-tune candidates."
          />
        </TerminalCard>
      ) : (
        <>
          {/* ── 2-column layout: Candidates sidebar + Training panel ── */}
          <div style={{ display: 'grid', gridTemplateColumns: '320px 1fr', gap: 16 }}>
          {/* ── Candidate list ── */}
          <TerminalCard title="FINE-TUNE CANDIDATES" noPadding>
            {/* Search + count */}
            <div style={{ padding: '8px 12px', borderBottom: '1px solid var(--border)', display: 'flex', gap: 8, alignItems: 'center' }}>
              <input
                type="text"
                placeholder="Filter candidates..."
                value={candidateSearch}
                onChange={e => { setCandidateSearch(e.target.value); setCandidateLimit(10) }}
                style={{
                  flex: 1, padding: '5px 10px', fontSize: 11,
                  background: '#E0E5EC', border: 'none', borderRadius: 10,
                  boxShadow: 'inset 3px 3px 6px rgb(163,177,198,0.4), inset -3px -3px 6px rgba(255,255,255,0.3)',
                  color: 'var(--text-primary)', outline: 'none',
                }}
              />
              <span style={{ fontSize: 10, color: 'var(--text-tertiary)', whiteSpace: 'nowrap' }}>
                {candidates.filter((c: any) => !candidateSearch || c.cluster_name?.toLowerCase().includes(candidateSearch.toLowerCase())).length} total
              </span>
            </div>
            <div style={{ maxHeight: 480, overflowY: 'auto' }}>
            {candidates
              .filter((c: any) => !candidateSearch || c.cluster_name?.toLowerCase().includes(candidateSearch.toLowerCase()))
              .slice(0, candidateLimit)
              .map((cluster: any) => {
              const clusterJob = jobs.find((job) => Number(job.cluster_id) === Number(cluster.cluster_id))
              return (
                <div
                  key={cluster.cluster_id}
                  onClick={() => setSelectedClusterId(cluster.cluster_id)}
                  style={{
                    padding: '12px 16px',
                    borderBottom: '1px solid var(--border)',
                    cursor: 'pointer',
                    background: selectedClusterId === cluster.cluster_id ? 'rgba(108,99,255,0.06)' : 'transparent',
                    borderLeft: selectedClusterId === cluster.cluster_id ? '3px solid #6C63FF' : '3px solid transparent',
                    borderRadius: '0 12px 12px 0',
                  }}
                >
                  <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12, alignItems: 'center', marginBottom: 4 }}>
                    <span style={{
                      fontSize: 13,
                      fontWeight: 600,
                      color: selectedClusterId === cluster.cluster_id ? '#6C63FF' : '#3D4852',
                    }}>
                      {cluster.cluster_name}
                    </span>
                    {clusterJob && (
                      <Badge variant={jobBadgeVariant(clusterJob.status)}>
                        {prettyJobStatus(clusterJob.status)}
                      </Badge>
                    )}
                  </div>
                  <div style={{ fontSize: 11, color: 'var(--text-secondary)' }}>
                    base: {cluster.fine_tune_base_model} · score: {Math.round((cluster.best_score ?? 0) * 100)}% · size: {cluster.cluster_size}
                  </div>
                </div>
              )
            })}
            </div>
            {(() => {
              const filtered = candidates.filter((c: any) => !candidateSearch || c.cluster_name?.toLowerCase().includes(candidateSearch.toLowerCase()))
              return filtered.length > candidateLimit ? (
                <div style={{ padding: '8px 12px', textAlign: 'center', borderTop: '1px solid var(--border)' }}>
                  <button
                    onClick={() => setCandidateLimit(prev => prev + 10)}
                    style={{
                      padding: '5px 16px', fontSize: 10, fontWeight: 700,
                      background: '#E0E5EC', border: 'none', borderRadius: 12,
                      boxShadow: '4px 4px 8px rgb(163,177,198,0.6), -4px -4px 8px rgba(255,255,255,0.5)',
                      color: '#6C63FF', cursor: 'pointer',
                    }}
                  >
                    SHOW MORE ({filtered.length - candidateLimit})
                  </button>
                </div>
              ) : null
            })()}
          </TerminalCard>

          {selectedCluster ? (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
              {/* ── Training backend ── */}
              <TerminalCard title="TRAINING BACKEND">
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(260px, 1fr))', gap: 12, marginBottom: 16 }}>
                  {backends.map((backend) => (
                    <button
                      key={backend.id}
                      onClick={() => setSelectedBackend(backend.id)}
                      style={{
                        textAlign: 'left',
                        padding: 14,
                        border: 'none',
                        background: selectedBackend === backend.id ? 'rgba(108,99,255,0.06)' : '#E0E5EC',
                        boxShadow: selectedBackend === backend.id ? 'inset 6px 6px 10px rgb(163,177,198,0.6), inset -6px -6px 10px rgba(255,255,255,0.5)' : '5px 5px 10px rgb(163,177,198,0.6), -5px -5px 10px rgba(255,255,255,0.5)',
                        cursor: 'pointer',
                        borderRadius: 20,
                        transition: 'all 300ms ease-out',
                      }}
                    >
                      <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8, marginBottom: 4 }}>
                        <span style={{ fontSize: 12, fontWeight: 600, color: selectedBackend === backend.id ? '#6C63FF' : '#3D4852' }}>
                          {backend.label}
                        </span>
                        {backend.recommended && (
                          <Badge variant="green">REC</Badge>
                        )}
                      </div>
                      <div style={{ fontSize: 11, color: 'var(--text-secondary)', marginBottom: 4 }}>{backend.subtitle}</div>
                      <div style={{ fontSize: 11, color: 'var(--text-tertiary)' }}>
                        {backend.time} · {backend.cost}
                      </div>
                      <div style={{ fontSize: 10, color: backend.configured ? '#38B2AC' : '#D69E2E', marginTop: 4 }}>
                        {backend.configured
                          ? `✓ ${backend.health_detail || 'healthy'}`
                          : `⚠ ${backend.health_detail || backend.setup_note}`}
                      </div>
                    </button>
                  ))}
                </div>

                <div style={{ display: 'grid', gridTemplateColumns: '2fr 1fr 1fr', gap: 12, marginBottom: 14 }}>
                  <FieldLabel label="model">
                    <TerminalSelect value={baseModel} onChange={(e) => setBaseModel(e.target.value)}>
                      {backendModelOptions.map((model: any) => (
                        <option key={model.id} value={model.id}>{model.label}</option>
                      ))}
                    </TerminalSelect>
                  </FieldLabel>
                  <FieldLabel label="epochs">
                    <TerminalInput type="number" min={1} max={8} value={epochs} onChange={(e) => setEpochs(Number(e.target.value || 2))} />
                  </FieldLabel>
                  <FieldLabel label="learning rate">
                    <TerminalInput value={learningRate} onChange={(e) => setLearningRate(e.target.value)} />
                  </FieldLabel>
                </div>

                {selectedModelInfo?.gated && (
                  <div style={{ fontSize: 11, color: 'var(--terminal-amber)', marginBottom: 14, lineHeight: 1.7 }}>
                  [WARN] This model requires HuggingFace gated access.
                  </div>
                )}

                <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap', alignItems: 'center', marginBottom: 14 }}>
                  {starting ? (
                    <AnimatedActionButton onClick={() => {}} label="STARTING..." icon="spinner" disabled active />
                  ) : (
                    <AnimatedActionButton onClick={handleStartTraining} label="START TRAINING" icon="play" disabled={!canStart} />
                  )}
                  <SecondaryButton onClick={handleStopTraining} disabled={!canStop}>
                    STOP
                  </SecondaryButton>
                  {deploying ? (
                    <AnimatedActionButton onClick={() => {}} label="DEPLOYING..." icon="spinner" disabled active />
                  ) : (
                    <AnimatedActionButton
                      onClick={handleDeploy}
                      label="DEPLOY & REGISTER"
                      icon="rocket"
                      disabled={!canDeploy}
                    />
                  )}
                  {deployed && (
                    <Badge variant="green">ACTIVE</Badge>
                  )}
                </div>

                <div style={{ fontSize: 11, color: 'var(--text-tertiary)', lineHeight: 1.7 }}>
                  cluster: <code style={{ color: '#6C63FF' }}>{selectedCluster.cluster_name}</code>
                </div>

                {actionMsg && (
                  <div style={{ marginTop: 10, fontSize: 11, color: 'var(--text-secondary)', lineHeight: 1.7 }}>
                    {actionMsg}
                  </div>
                )}
              </TerminalCard>

              {/* ── Training status ── */}
              <TerminalCard
                title="TRAINING STATUS"
                headerRight={latestJob ? <Badge variant={jobBadgeVariant(latestJob.status)}>{prettyJobStatus(latestJob.status)}</Badge> : undefined}
              >
                {latestJob ? (
                  <>
                    <div style={{ fontSize: 11, color: 'var(--text-secondary)', marginBottom: 8 }}>
                      {latestJob.phase || 'queued'}
                    </div>

                    <ProgressBar
                      value={latestJob.progress || 0}
                      label="progress"
                      color={latestJob.status === 'failed' ? 'var(--terminal-red)' : 'var(--terminal-green)'}
                    />

                    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(160px, 1fr))', gap: 10, margin: '14px 0' }}>
                      <StatBlock label="BACKEND" value={latestJob.backend} />
                      <StatBlock label="SAMPLES" value={String(latestJob.sample_count || 0)} />
                      <StatBlock label="MODEL" value={latestJob.recommended_model_name} />
                      <StatBlock
                        label="ACCURACY"
                        value={deployableJob?.result?.post_train_accuracy ? `${deployableJob.result.post_train_accuracy}%` : 'pending'}
                      />
                    </div>

                    {/* Loss curve */}
                    <div style={{ height: 180, marginBottom: 14 }}>
                      <ResponsiveContainer width="100%" height="100%">
                        <LineChart data={(latestJob.metrics || []).map((m: any, i: number) => ({ ...m, idx: i + 1 }))}>
                          <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
                          <XAxis dataKey="idx" tick={{ fill: '#9CA3AF', fontSize: 10 }} stroke="transparent" />
                          <YAxis tick={{ fill: '#9CA3AF', fontSize: 10 }} width={40} stroke="transparent" />
                          <Tooltip contentStyle={{ background: '#E0E5EC', border: 'none', borderRadius: 16, fontSize: 12, color: '#3D4852', boxShadow: '5px 5px 10px rgb(163,177,198,0.6), -5px -5px 10px rgba(255,255,255,0.5)' }} />
                          <Line type="monotone" dataKey="loss" stroke="#6C63FF" dot={false} strokeWidth={2} />
                        </LineChart>
                      </ResponsiveContainer>
                    </div>

                    {/* Logs */}
                    <div className="code-block" style={{ maxHeight: 180, overflow: 'auto', fontSize: 10, color: 'var(--text-secondary)' }}>
                      {(latestJob.logs || []).length
                        ? latestJob.logs.map((log: any) => `[${log.timestamp}] ${log.message}`).join('\n')
                        : (latestJobInFlight(latestJob)
                          ? '> waiting for first log line...'
                          : '> no logs yet.')}
                    </div>
                  </>
                ) : (
                  <EmptyState message="No training job started for this cluster yet" />
                )}
              </TerminalCard>

              {/* ── Training data preview (collapsed by default) ── */}
              <TerminalCard title="DATA PREVIEW">
                <Collapsible title={`Show training data sample (${preview?.examples?.length || 0} examples)`}>
                  {previewLoading ? (
                    <LoadingTerminal message="loading preview" />
                  ) : preview?.examples?.length ? (
                    <div style={{ display: 'grid', gap: 8, marginTop: 8 }}>
                      {preview.examples.map((ex: any, i: number) => (
                        <div key={i} style={{ background: 'var(--bg-secondary)', border: '1px solid var(--border)', padding: '10px 12px' }}>
                          <div style={{ fontSize: 9, color: 'var(--text-tertiary)', textTransform: 'uppercase', letterSpacing: '0.1em', marginBottom: 6 }}>
                            {ex.node_name || 'node'}
                          </div>
                          <div style={{ fontSize: 10, fontWeight: 600, color: 'var(--terminal-green)', marginBottom: 2 }}>PROMPT</div>
                          <div style={{ fontSize: 11, color: 'var(--text-secondary)', whiteSpace: 'pre-wrap', marginBottom: 8 }}>{ex.prompt}</div>
                          <div style={{ fontSize: 10, fontWeight: 600, color: 'var(--terminal-amber)', marginBottom: 2 }}>RESPONSE</div>
                          <div style={{ fontSize: 11, color: 'var(--text-secondary)', whiteSpace: 'pre-wrap' }}>{ex.response}</div>
                        </div>
                      ))}
                    </div>
                  ) : (
                    <EmptyState message="No preview data available" />
                  )}
                </Collapsible>
              </TerminalCard>
            </div>
          ) : (
            <TerminalCard>
              <EmptyState
                message="Select a cluster from the left panel"
                hint="Click on a fine-tune candidate to configure training"
              />
            </TerminalCard>
          )}
          </div>
        </>
      )}
    </PageShell>
  )
}

function latestJobInFlight(job: any) {
  return job && ['queued', 'running', 'deploying'].includes(job.status)
}

function prettyJobStatus(status: string) {
  return {
    queued: 'QUEUED',
    running: 'TRAINING',
    completed: 'READY',
    deploying: 'DEPLOYING',
    deployed: 'ACTIVE',
    failed: 'FAILED',
    stopped: 'STOPPED',
  }[status] || status.toUpperCase()
}

type BadgeVariant = 'green' | 'amber' | 'red' | 'blue' | 'purple' | 'default'

function jobBadgeVariant(status: string): BadgeVariant {
  return {
    queued: 'amber' as BadgeVariant,
    running: 'green' as BadgeVariant,
    completed: 'purple' as BadgeVariant,
    deploying: 'amber' as BadgeVariant,
    deployed: 'green' as BadgeVariant,
    failed: 'red' as BadgeVariant,
    stopped: 'default' as BadgeVariant,
  }[status] || 'default'
}

function StatBlock({ label, value }: { label: string; value: string }) {
  return (
    <div style={{ background: '#E0E5EC', borderRadius: 16, padding: 12, boxShadow: 'inset 6px 6px 10px rgb(163,177,198,0.6), inset -6px -6px 10px rgba(255,255,255,0.5)' }}>
      <div style={{ fontSize: 10, color: '#9CA3AF', textTransform: 'uppercase', letterSpacing: '0.08em', marginBottom: 4 }}>{label}</div>
      <div style={{ fontSize: 13, color: '#3D4852', fontWeight: 600, wordBreak: 'break-word' }}>{value}</div>
    </div>
  )
}

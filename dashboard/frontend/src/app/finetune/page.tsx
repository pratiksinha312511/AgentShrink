'use client'

import type { CSSProperties } from 'react'
import { useEffect, useMemo, useState } from 'react'
import { LineChart, Line, CartesianGrid, XAxis, YAxis, Tooltip, ResponsiveContainer } from 'recharts'
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
  const latestJob = useMemo(() => {
    if (!selectedClusterId) return null
    return jobs.find((job) => Number(job.cluster_id) === Number(selectedClusterId)) || null
  }, [jobs, selectedClusterId])

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
  const canDeploy = latestJob?.status === 'completed'
  const deployed = latestJob?.status === 'deployed'

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
    if (!latestJob) return
    setDeploying(true)
    setActionMsg('')
    try {
      setJobs((prev) =>
        prev.map((job) =>
          job.job_id === latestJob.job_id
            ? { ...job, status: 'deploying', phase: 'Preparing local deployment', progress: Math.max(8, job.progress || 0) }
            : job
        )
      )
      const res = await deployFineTuneJob(latestJob.job_id)
      setJobs((prev) => [res.job, ...prev.filter((job) => job.job_id !== res.job.job_id)])
      setActionMsg('Deployment started. Progress and logs will keep updating below.')
    } catch (e: any) {
      setActionMsg(e.message || 'Failed to deploy fine-tuned model.')
    } finally {
      setDeploying(false)
    }
  }

  if (loading) return <div style={{ color: 'var(--text-tertiary)', padding: 40, textAlign: 'center' }}>Loading fine-tune data...</div>
  if (error) return <div className="card" style={{ padding: 24, maxWidth: 900 }}>{error}</div>

  return (
    <div style={{ maxWidth: 960 }}>
      <div className="card" style={{ padding: 24, marginBottom: 16 }}>
        <h1 style={{ fontSize: 22, fontWeight: 500, marginBottom: 8 }}>Fine-tune</h1>
        <p style={{ color: 'var(--text-secondary)', lineHeight: 1.7, marginBottom: 12 }}>
          Start remote fine-tuning from inside AgentShrink, keep the job running in the background, and only deploy/register the model after training completes successfully.
        </p>
        <div style={{ fontSize: 12, color: 'var(--text-secondary)', lineHeight: 1.7 }}>
          This machine has no local GPU, so training runs on the backend you choose below. Job status is stored on disk, so you can refresh the page or reopen the browser without losing progress.
        </div>
      </div>

      {candidates.length === 0 ? (
        <div className="card" style={{ padding: 24 }}>
          <div style={{ fontSize: 15, fontWeight: 500, marginBottom: 8 }}>No fine-tune candidates right now</div>
          <div style={{ fontSize: 13, color: 'var(--text-secondary)', lineHeight: 1.7 }}>
            Run analysis again after collecting more calls, or use a fuller evaluator-backed report to produce more meaningful fine-tune candidates.
          </div>
        </div>
      ) : (
        <>
          <div className="card" style={{ overflow: 'hidden', marginBottom: 16 }}>
            <div style={{ padding: '14px 20px', borderBottom: '0.5px solid var(--border)', fontSize: 12, fontWeight: 500, color: 'var(--text-secondary)' }}>
              Fine-tune candidates
            </div>
            {candidates.map((cluster: any) => {
              const clusterJob = jobs.find((job) => Number(job.cluster_id) === Number(cluster.cluster_id))
              return (
                <div
                  key={cluster.cluster_id}
                  onClick={() => setSelectedClusterId(cluster.cluster_id)}
                  style={{
                    padding: '14px 20px',
                    borderBottom: '0.5px solid var(--border)',
                    cursor: 'pointer',
                    background: selectedClusterId === cluster.cluster_id ? 'var(--bg-secondary)' : 'transparent',
                  }}
                >
                  <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12, alignItems: 'center', marginBottom: 6 }}>
                    <div style={{ fontSize: 14, fontWeight: 500, color: 'var(--text-primary)' }}>{cluster.cluster_name}</div>
                    {clusterJob && (
                      <span style={badgeStyle(clusterJob.status)}>
                        {prettyJobStatus(clusterJob.status)}
                      </span>
                    )}
                  </div>
                  <div style={{ fontSize: 12, color: 'var(--text-secondary)', marginBottom: 4 }}>
                    Base suggestion: {cluster.fine_tune_base_model}
                  </div>
                  <div style={{ fontSize: 12, color: 'var(--text-secondary)' }}>
                    Current score: {Math.round((cluster.best_score ?? 0) * 100)}% - cluster size: {cluster.cluster_size}
                  </div>
                </div>
              )
            })}
          </div>

          {selectedCluster && (
            <>
              <div className="card" style={{ padding: 24, marginBottom: 16 }}>
                <div style={{ fontSize: 15, fontWeight: 500, marginBottom: 12 }}>Training backend</div>
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(260px, 1fr))', gap: 12, marginBottom: 18 }}>
                  {backends.map((backend) => (
                    <button
                      key={backend.id}
                      onClick={() => setSelectedBackend(backend.id)}
                      style={{
                        textAlign: 'left',
                        padding: 16,
                        borderRadius: 12,
                        border: selectedBackend === backend.id ? '1px solid #7F77DD' : '0.5px solid var(--border)',
                        background: selectedBackend === backend.id ? 'rgba(127,119,221,0.08)' : 'var(--bg-primary)',
                        cursor: 'pointer',
                      }}
                    >
                      <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8, marginBottom: 6 }}>
                        <div style={{ fontSize: 14, fontWeight: 500, color: 'var(--text-primary)' }}>{backend.label}</div>
                        {backend.recommended && (
                          <span style={{ fontSize: 10, color: '#1D9E75', fontWeight: 600 }}>recommended</span>
                        )}
                      </div>
                      <div style={{ fontSize: 12, color: 'var(--text-secondary)', marginBottom: 6 }}>{backend.subtitle}</div>
                      <div style={{ fontSize: 12, color: 'var(--text-secondary)', marginBottom: 6 }}>
                        {backend.time} - {backend.cost}
                      </div>
                      <div style={{ fontSize: 12, color: backend.configured ? '#1D9E75' : '#D85A30' }}>
                        {backend.configured ? 'Credentials detected' : backend.setup_note}
                      </div>
                    </button>
                  ))}
                </div>

                <div style={{ display: 'grid', gridTemplateColumns: '2fr 1fr 1fr', gap: 12, marginBottom: 14 }}>
                  <label style={fieldLabelStyle}>
                    Model
                    <select value={baseModel} onChange={(e) => setBaseModel(e.target.value)} style={fieldInputStyle}>
                      {backendModelOptions.map((model: any) => (
                        <option key={model.id} value={model.id}>
                          {model.label}
                        </option>
                      ))}
                    </select>
                  </label>
                  <label style={fieldLabelStyle}>
                    Epochs
                    <input type="number" min={1} max={8} value={epochs} onChange={(e) => setEpochs(Number(e.target.value || 2))} style={fieldInputStyle} />
                  </label>
                  <label style={fieldLabelStyle}>
                    Learning rate
                    <input value={learningRate} onChange={(e) => setLearningRate(e.target.value)} style={fieldInputStyle} />
                  </label>
                </div>

                {selectedModelInfo?.gated && (
                  <div style={{ fontSize: 12, color: '#D85A30', marginBottom: 14, lineHeight: 1.7 }}>
                    This model requires Hugging Face gated access. AgentShrink will validate your HF token and repo access before starting training.
                  </div>
                )}

                <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap', alignItems: 'center', marginBottom: 14 }}>
                  <button onClick={handleStartTraining} disabled={!canStart || starting} style={primaryButtonStyle(!canStart || starting)}>
                    {starting ? 'Starting...' : 'Start training'}
                  </button>
                  <button onClick={handleStopTraining} disabled={!canStop} style={secondaryButtonStyle(!canStop)}>
                    Stop training
                  </button>
                  <button onClick={handleDeploy} disabled={!canDeploy || deploying} style={secondaryButtonStyle(!canDeploy || deploying)}>
                    {deploying ? 'Deploying...' : 'Deploy & register model'}
                  </button>
                  {deployed && (
                    <span style={{ fontSize: 12, color: '#1D9E75', fontWeight: 500 }}>
                      Fine-tuned model active
                    </span>
                  )}
                </div>

                <div style={{ fontSize: 12, color: 'var(--text-secondary)', lineHeight: 1.7 }}>
                  Selected cluster: <code>{selectedCluster.cluster_name}</code>
                  <br />
                  Registering stays disabled until training completes. Deployment creates the Ollama model on this same machine and registers it for routing automatically.
                </div>

                {actionMsg && (
                  <div style={{ marginTop: 12, fontSize: 12, color: 'var(--text-secondary)', lineHeight: 1.7 }}>
                    {actionMsg}
                  </div>
                )}
              </div>

              <div className="card" style={{ padding: 24, marginBottom: 16 }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12, alignItems: 'center', marginBottom: 12 }}>
                  <div style={{ fontSize: 15, fontWeight: 500 }}>Training status</div>
                  {latestJob ? <span style={badgeStyle(latestJob.status)}>{prettyJobStatus(latestJob.status)}</span> : null}
                </div>

                {latestJob ? (
                  <>
                    <div style={{ fontSize: 12, color: 'var(--text-secondary)', marginBottom: 8 }}>
                      {latestJob.phase || 'Queued'}
                    </div>
                    <div style={{ width: '100%', height: 10, background: 'var(--bg-secondary)', borderRadius: 999, overflow: 'hidden', marginBottom: 12 }}>
                      <div style={{ width: `${Math.max(0, Math.min(100, latestJob.progress || 0))}%`, height: '100%', background: '#1D9E75' }} />
                    </div>
                    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: 12, marginBottom: 16 }}>
                      <Stat label="Backend" value={latestJob.backend} />
                      <Stat label="Samples" value={String(latestJob.sample_count || 0)} />
                      <Stat label="Recommended model" value={latestJob.recommended_model_name} />
                      <Stat
                        label="Post-train accuracy"
                        value={latestJob.result?.post_train_accuracy ? `${latestJob.result.post_train_accuracy}%` : 'Pending'}
                      />
                    </div>

                    <div style={{ height: 220, marginBottom: 16 }}>
                      <ResponsiveContainer width="100%" height="100%">
                        <LineChart data={(latestJob.metrics || []).map((metric: any, index: number) => ({ ...metric, idx: index + 1 }))}>
                          <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
                          <XAxis dataKey="idx" tick={{ fill: '#8A8177', fontSize: 11 }} />
                          <YAxis tick={{ fill: '#8A8177', fontSize: 11 }} width={40} />
                          <Tooltip />
                          <Line type="monotone" dataKey="loss" stroke="#7F77DD" dot={false} strokeWidth={2} />
                        </LineChart>
                      </ResponsiveContainer>
                    </div>

                    <div style={{ background: 'var(--bg-secondary)', borderRadius: 10, padding: 12, maxHeight: 220, overflow: 'auto', fontFamily: 'monospace', fontSize: 11, color: 'var(--text-secondary)', whiteSpace: 'pre-wrap' }}>
                      {(latestJob.logs || []).length
                        ? latestJob.logs.map((log: any, index: number) => `[${log.timestamp}] ${log.message}`).join('\n')
                        : 'No logs yet.'}
                    </div>
                  </>
                ) : (
                  <div style={{ fontSize: 13, color: 'var(--text-secondary)', lineHeight: 1.7 }}>
                    No training job started for this cluster yet.
                  </div>
                )}
              </div>

              <div className="card" style={{ padding: 24 }}>
                <div style={{ fontSize: 12, fontWeight: 500, color: 'var(--text-secondary)', marginBottom: 10 }}>
                  Training example preview
                </div>
                {previewLoading ? (
                  <div style={{ color: 'var(--text-tertiary)', fontSize: 13 }}>Loading preview...</div>
                ) : preview?.examples?.length ? (
                  <div style={{ display: 'grid', gap: 10 }}>
                    {preview.examples.map((ex: any, i: number) => (
                      <div key={i} style={{ background: 'var(--bg-secondary)', borderRadius: 8, padding: '12px 14px' }}>
                        <div style={{ fontSize: 10, color: 'var(--text-tertiary)', textTransform: 'uppercase', marginBottom: 6 }}>
                          {ex.node_name || 'node'}
                        </div>
                        <div style={{ fontSize: 11, fontWeight: 500, color: 'var(--text-primary)', marginBottom: 4 }}>Prompt</div>
                        <div style={{ fontSize: 11, color: 'var(--text-secondary)', whiteSpace: 'pre-wrap', marginBottom: 10 }}>
                          {ex.prompt}
                        </div>
                        <div style={{ fontSize: 11, fontWeight: 500, color: 'var(--text-primary)', marginBottom: 4 }}>Reference response</div>
                        <div style={{ fontSize: 11, color: 'var(--text-secondary)', whiteSpace: 'pre-wrap' }}>
                          {ex.response}
                        </div>
                      </div>
                    ))}
                  </div>
                ) : (
                  <div style={{ color: 'var(--text-tertiary)', fontSize: 13 }}>No preview data available.</div>
                )}
              </div>
            </>
          )}
        </>
      )}
    </div>
  )
}

function latestJobInFlight(job: any) {
  return job && ['queued', 'running', 'deploying'].includes(job.status)
}

function prettyJobStatus(status: string) {
  return {
    queued: 'queued',
    running: 'training',
    completed: 'ready to deploy',
    deploying: 'deploying',
    deployed: 'active',
    failed: 'failed',
    stopped: 'stopped',
  }[status] || status
}

function badgeStyle(status: string) {
  const palette: Record<string, any> = {
    queued: { background: '#F0EBDC', color: '#8A6C1F' },
    running: { background: '#E5F4EF', color: '#1D9E75' },
    completed: { background: '#EEF0FF', color: '#6258CC' },
    deploying: { background: '#FFF1E2', color: '#D85A30' },
    deployed: { background: '#E5F4EF', color: '#1D9E75' },
    failed: { background: '#FCEAEA', color: '#C44B4B' },
    stopped: { background: '#F4F0EA', color: '#8A8177' },
  }
  return {
    display: 'inline-flex',
    padding: '4px 8px',
    borderRadius: 999,
    fontSize: 11,
    fontWeight: 500,
    ...(palette[status] || palette.stopped),
  }
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div style={{ background: 'var(--bg-secondary)', borderRadius: 10, padding: 12 }}>
      <div style={{ fontSize: 11, color: 'var(--text-tertiary)', textTransform: 'uppercase', marginBottom: 4 }}>{label}</div>
      <div style={{ fontSize: 13, color: 'var(--text-primary)', fontWeight: 500, wordBreak: 'break-word' }}>{value}</div>
    </div>
  )
}

const fieldLabelStyle: CSSProperties = {
  display: 'grid',
  gap: 6,
  fontSize: 12,
  color: 'var(--text-secondary)',
}

const fieldInputStyle: CSSProperties = {
  padding: '10px 12px',
  borderRadius: 8,
  border: '0.5px solid var(--border)',
  background: 'var(--bg-primary)',
}

function primaryButtonStyle(disabled: boolean): CSSProperties {
  return {
    background: disabled ? '#BEB9F0' : '#7F77DD',
    color: 'white',
    border: 'none',
    borderRadius: 8,
    padding: '10px 14px',
    fontSize: 12,
    cursor: disabled ? 'not-allowed' : 'pointer',
  }
}

function secondaryButtonStyle(disabled: boolean): CSSProperties {
  return {
    background: 'transparent',
    color: disabled ? 'var(--text-tertiary)' : 'var(--text-primary)',
    border: '0.5px solid var(--border)',
    borderRadius: 8,
    padding: '10px 14px',
    fontSize: 12,
    cursor: disabled ? 'not-allowed' : 'pointer',
  }
}

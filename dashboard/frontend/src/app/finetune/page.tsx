'use client'
import { useEffect, useState } from 'react'
import {
  exportFineTuneData,
  fetchFineTunePreview,
  fetchOllamaModels,
  fetchReport,
  registerFineTunedModel,
} from '@/lib/api'

export default function FinetunePage() {
  const [report, setReport] = useState<any>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [selected, setSelected] = useState<number | null>(null)
  const [preview, setPreview] = useState<any>(null)
  const [previewLoading, setPreviewLoading] = useState(false)
  const [actionMsg, setActionMsg] = useState('')
  const [registerModel, setRegisterModel] = useState('')
  const [registerDisplay, setRegisterDisplay] = useState('')
  const [ollamaModels, setOllamaModels] = useState<string[]>([])
  const [modelsDir, setModelsDir] = useState('')
  const [exportResult, setExportResult] = useState<any>(null)

  useEffect(() => {
    fetchReport()
      .then(setReport)
      .catch(e => setError(e.message))
      .finally(() => setLoading(false))

    fetchOllamaModels()
      .then((data) => {
        setOllamaModels(data.models || [])
        setModelsDir(data.models_dir || '')
      })
      .catch(() => {})
  }, [])

  const candidates = (report?.clusters ?? []).filter((c: any) => c.recommendation === 'fine_tune')
  const selectedCluster = candidates.find((c: any) => c.cluster_id === selected)
  const recommendedModelName = buildRecommendedModelName(selectedCluster?.cluster_name)
  const recommendedDisplayName = buildRecommendedDisplayName(selectedCluster?.cluster_name)

  useEffect(() => {
    if (candidates.length > 0 && selected === null) {
      setSelected(candidates[0].cluster_id)
    }
  }, [candidates, selected])

  useEffect(() => {
    if (!selectedCluster) return
    setRegisterModel(recommendedModelName)
    setRegisterDisplay(recommendedDisplayName)
    setExportResult(null)
  }, [selectedCluster, recommendedModelName, recommendedDisplayName])

  useEffect(() => {
    if (selected === null) return
    setPreviewLoading(true)
    fetchFineTunePreview(selected)
      .then(setPreview)
      .catch(() => setPreview(null))
      .finally(() => setPreviewLoading(false))
  }, [selected])

  const handleExport = async () => {
    if (selected === null) return
    setActionMsg('')
    try {
      const res = await exportFineTuneData(selected)
      setExportResult(res)
      setActionMsg(`Exported ${res.example_count} examples. Dataset: ${res.dataset_path}. Notebook: ${res.notebook_path}`)
    } catch (e: any) {
      setActionMsg(e.message || 'Failed to export training data.')
    }
  }

  const handleRegister = async () => {
    if (selected === null || !registerModel.trim() || !registerDisplay.trim()) return
    setActionMsg('')
    try {
      const res = await registerFineTunedModel(selected, registerModel.trim(), registerDisplay.trim())
      setActionMsg(res.message)
    } catch (e: any) {
      setActionMsg(e.message || 'Failed to register fine-tuned model.')
    }
  }

  const handleCopyRecommendedName = async () => {
    try {
      await navigator.clipboard.writeText(recommendedModelName)
      setActionMsg(`Copied recommended model name: ${recommendedModelName}`)
    } catch {
      setActionMsg('Could not copy automatically. Please copy the recommended name manually.')
    }
  }

  const handleOpenColab = () => {
    window.open('https://colab.research.google.com/', '_blank', 'noopener,noreferrer')
  }

  if (loading) return <div style={{ color: 'var(--text-tertiary)', padding: 40, textAlign: 'center' }}>Loading fine-tune data...</div>
  if (error) return <div className="card" style={{ padding: 24, maxWidth: 900 }}>{error}</div>

  return (
    <div style={{ maxWidth: 900 }}>
      <div className="card" style={{ padding: 24, marginBottom: 16 }}>
        <h1 style={{ fontSize: 22, fontWeight: 500, marginBottom: 8 }}>Fine-tune</h1>
        <p style={{ color: 'var(--text-secondary)', lineHeight: 1.7 }}>
          Borderline clusters can export supervised training data, generate a Colab notebook, and later be registered as fine-tuned local routing targets.
        </p>
      </div>

      {candidates.length === 0 ? (
        <div className="card" style={{ padding: 24 }}>
          <div style={{ fontSize: 15, fontWeight: 500, color: 'var(--text-primary)', marginBottom: 8 }}>
            No fine-tune candidates right now
          </div>
          <div style={{ fontSize: 13, color: 'var(--text-secondary)', lineHeight: 1.7 }}>
            A full evaluator-backed report would usually produce more meaningful fine-tune candidates than heuristic mode.
          </div>
        </div>
      ) : (
        <>
          <div className="card" style={{ overflow: 'hidden', marginBottom: 16 }}>
            <div style={{ padding: '14px 20px', borderBottom: '0.5px solid var(--border)', fontSize: 12, fontWeight: 500, color: 'var(--text-secondary)' }}>
              Fine-tune candidates
            </div>
            {candidates.map((cluster: any) => (
              <div
                key={cluster.cluster_id}
                onClick={() => setSelected(cluster.cluster_id)}
                style={{
                  padding: '14px 20px',
                  borderBottom: '0.5px solid var(--border)',
                  cursor: 'pointer',
                  background: selected === cluster.cluster_id ? 'var(--bg-secondary)' : 'transparent',
                }}
              >
                <div style={{ fontSize: 14, fontWeight: 500, color: 'var(--text-primary)', marginBottom: 6 }}>
                  {cluster.cluster_name}
                </div>
                <div style={{ fontSize: 12, color: 'var(--text-secondary)', marginBottom: 4 }}>
                  Base model: {cluster.fine_tune_base_model}
                </div>
                <div style={{ fontSize: 12, color: 'var(--text-secondary)' }}>
                  Current score: {Math.round((cluster.best_score ?? 0) * 100)}% - cluster size: {cluster.cluster_size}
                </div>
              </div>
            ))}
          </div>

          {selectedCluster && (
            <div className="card" style={{ padding: 24, marginBottom: 16 }}>
              <div style={{ fontSize: 15, fontWeight: 500, color: 'var(--text-primary)', marginBottom: 12 }}>
                Selected cluster: {selectedCluster.cluster_name}
              </div>

              <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap', marginBottom: 12 }}>
                <button
                  onClick={handleExport}
                  style={{
                    background: '#1D9E75', color: 'white', border: 'none',
                    borderRadius: 8, padding: '8px 14px', fontSize: 12, cursor: 'pointer',
                  }}
                >
                  Export training data
                </button>
                <button
                  onClick={handleCopyRecommendedName}
                  style={{
                    background: 'transparent', color: 'var(--text-primary)', border: '0.5px solid var(--border)',
                    borderRadius: 8, padding: '8px 14px', fontSize: 12, cursor: 'pointer',
                  }}
                >
                  Copy recommended model name
                </button>
                <button
                  onClick={handleOpenColab}
                  style={{
                    background: 'transparent', color: 'var(--text-primary)', border: '0.5px solid var(--border)',
                    borderRadius: 8, padding: '8px 14px', fontSize: 12, cursor: 'pointer',
                  }}
                >
                  Open Colab
                </button>
              </div>

              <div style={{ fontSize: 12, color: 'var(--text-secondary)', lineHeight: 1.7, marginBottom: 12 }}>
                Recommended Ollama model name: <code>{recommendedModelName}</code>
                <br />
                Recommended display name: <code>{recommendedDisplayName}</code>
                <br />
                AgentShrink can open Colab for you, but it cannot sign in to Google or upload the notebook automatically.
              </div>

              {exportResult && (
                <div style={{ background: 'var(--bg-secondary)', borderRadius: 8, padding: '12px 14px', marginBottom: 12 }}>
                  <div style={{ fontSize: 12, fontWeight: 500, color: 'var(--text-primary)', marginBottom: 6 }}>
                    Generated training assets
                  </div>
                  <div style={{ fontSize: 12, color: 'var(--text-secondary)', lineHeight: 1.7 }}>
                    Dataset: <code>{exportResult.dataset_path}</code>
                    <br />
                    Notebook: <code>{exportResult.notebook_path}</code>
                    <br />
                    Next step: click <strong>Open Colab</strong>, then upload or open that notebook in your browser session and run all cells.
                  </div>
                </div>
              )}

              <div style={{ fontSize: 12, fontWeight: 500, color: 'var(--text-secondary)', marginBottom: 8 }}>
                Register fine-tuned model later
              </div>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr auto', gap: 8, alignItems: 'center' }}>
                <input
                  value={registerModel}
                  onChange={e => setRegisterModel(e.target.value)}
                  placeholder="Ollama model name"
                  style={{ padding: '10px 12px', borderRadius: 8, border: '0.5px solid var(--border)', background: 'var(--bg-primary)' }}
                />
                <input
                  value={registerDisplay}
                  onChange={e => setRegisterDisplay(e.target.value)}
                  placeholder="Display name"
                  style={{ padding: '10px 12px', borderRadius: 8, border: '0.5px solid var(--border)', background: 'var(--bg-primary)' }}
                />
                <button
                  onClick={handleRegister}
                  style={{
                    background: '#7F77DD', color: 'white', border: 'none',
                    borderRadius: 8, padding: '10px 14px', fontSize: 12, cursor: 'pointer',
                  }}
                >
                  Register model
                </button>
              </div>

              {actionMsg && (
                <div style={{ marginTop: 12, fontSize: 12, color: 'var(--text-secondary)', lineHeight: 1.7 }}>
                  {actionMsg}
                </div>
              )}

              <div style={{ marginTop: 12, fontSize: 12, color: 'var(--text-secondary)', lineHeight: 1.7 }}>
                Available Ollama models right now: {ollamaModels.length ? ollamaModels.join(', ') : 'none detected'}
                <br />
                Ollama models directory: <code>{modelsDir || 'Unavailable'}</code>
                <br />
                Register only after the fine-tuned model appears in <code>ollama list</code>.
              </div>
            </div>
          )}

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
    </div>
  )
}

function buildRecommendedModelName(clusterName?: string) {
  const rawName = String(clusterName || 'cluster').trim().toLowerCase()
  const slug = rawName.replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '')
  return `agentshrink-${slug || 'cluster'}-ft`
}

function buildRecommendedDisplayName(clusterName?: string) {
  const parts = String(clusterName || 'Cluster')
    .split(/[_\-\s]+/)
    .filter(Boolean)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
  return `${parts.join(' ') || 'Cluster'} FT`
}

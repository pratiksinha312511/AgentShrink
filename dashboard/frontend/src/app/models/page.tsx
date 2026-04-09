'use client'
import { useEffect, useState } from 'react'
import { deleteModel, fetchModels, saveJudgeModel, saveModel } from '@/lib/api'

const EMPTY_FORM = {
  id: undefined,
  provider: 'ollama',
  model_name: '',
  display_name: '',
  enabled: true,
  candidate_enabled: true,
  judge_eligible: true,
  local: true,
  supports: 'general',
  quality_tier: 3,
  cost_in_per_1k: 0,
  cost_out_per_1k: 0,
}

export default function ModelsPage() {
  const [data, setData] = useState<any>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [saving, setSaving] = useState(false)
  const [savingJudgeId, setSavingJudgeId] = useState<string | null>(null)
  const [form, setForm] = useState<any>(EMPTY_FORM)
  const [editingId, setEditingId] = useState<string | null>(null)

  const load = async () => {
    try {
      setData(await fetchModels())
      setError('')
    } catch (e: any) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    load()
  }, [])

  const submit = async () => {
    if (!form.model_name.trim()) {
      setError('Model name is required.')
      return
    }
    setSaving(true)
    try {
      await saveModel({
        ...form,
        local: form.provider === 'ollama' ? true : form.local,
        supports: form.supports.split(',').map((item: string) => item.trim()).filter(Boolean),
      })
      setForm(EMPTY_FORM)
      setEditingId(null)
      await load()
    } catch (e: any) {
      setError(e.message)
    } finally {
      setSaving(false)
    }
  }

  const remove = async (modelId: string) => {
    try {
      await deleteModel(modelId)
      await load()
    } catch (e: any) {
      setError(e.message)
    }
  }

  const startEdit = (model: any) => {
    setError('')
    setEditingId(model.id)
      setForm({
        id: model.id,
        provider: model.provider,
        model_name: model.model_name,
        display_name: model.display_name,
        enabled: model.enabled,
        candidate_enabled: model.candidate_enabled ?? true,
        judge_eligible: model.judge_eligible ?? true,
        local: model.local,
      supports: (model.supports ?? []).join(', '),
      quality_tier: model.quality_tier,
      cost_in_per_1k: model.cost_in_per_1k,
      cost_out_per_1k: model.cost_out_per_1k,
    })
  }

  const cancelEdit = () => {
    setEditingId(null)
    setError('')
    setForm(EMPTY_FORM)
  }

  const toggleEnabled = async (model: any) => {
    try {
      await saveModel({
        ...model,
        enabled: !model.enabled,
      })
      await load()
    } catch (e: any) {
      setError(e.message)
    }
  }

  const selectJudgeModel = async (modelId: string | null) => {
    try {
      setSavingJudgeId(modelId)
      await saveJudgeModel(modelId)
      await load()
    } catch (e: any) {
      setError(e.message)
    } finally {
      setSavingJudgeId(null)
    }
  }

  if (loading) return <div style={{ color: 'var(--text-tertiary)', padding: 40, textAlign: 'center' }}>Loading models...</div>
  if (error && !data) return <div className="card" style={{ padding: 24, maxWidth: 960 }}>{error}</div>

  const Toggle = ({
    checked,
    onClick,
    disabled = false,
    label,
  }: {
    checked: boolean
    onClick: () => void
    disabled?: boolean
    label: string
  }) => (
    <button
      onClick={onClick}
      disabled={disabled}
      aria-label={label}
      title={label}
      style={{
        width: 42,
        height: 24,
        borderRadius: 999,
        border: 'none',
        background: checked ? '#1D9E75' : '#D1D5DB',
        position: 'relative',
        cursor: disabled ? 'default' : 'pointer',
        opacity: disabled ? 0.6 : 1,
        transition: 'background 0.2s ease',
      }}
    >
      <span
        style={{
          position: 'absolute',
          top: 3,
          left: checked ? 21 : 3,
          width: 18,
          height: 18,
          borderRadius: '50%',
          background: '#fff',
          transition: 'left 0.2s ease',
          boxShadow: '0 1px 3px rgba(0,0,0,0.2)',
        }}
      />
    </button>
  )

  const mutedLabelStyle = {
    fontSize: 10,
    color: 'var(--text-tertiary)',
    textTransform: 'uppercase' as const,
    letterSpacing: '0.04em',
  }

  return (
    <div style={{ maxWidth: 980 }}>
      <div className="card" style={{ padding: 24, marginBottom: 16 }}>
        <h1 style={{ fontSize: 22, fontWeight: 500, marginBottom: 8 }}>Models</h1>
        <p style={{ color: 'var(--text-secondary)', lineHeight: 1.7, marginBottom: 16 }}>
          Configure the model catalog that report generation and live routing can choose from. Routing prefers the cheapest enabled model that still matches the task type and minimum quality tier.
        </p>

        <form
          onSubmit={e => {
            e.preventDefault()
            submit()
          }}
        >
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 10 }}>
          <label>
            <div style={{ fontSize: 11, color: 'var(--text-tertiary)', marginBottom: 4 }}>Provider</div>
            <select value={form.provider} onChange={e => { setError(''); setForm({ ...form, provider: e.target.value, local: e.target.value === 'ollama' }) }} style={{ width: '100%', padding: '10px 12px', borderRadius: 8 }}>
              {(data?.available_providers ?? []).map((provider: string) => (
                <option key={provider} value={provider}>{provider}</option>
              ))}
            </select>
          </label>
          <label>
            <div style={{ fontSize: 11, color: 'var(--text-tertiary)', marginBottom: 4 }}>Model name</div>
            <input value={form.model_name} onChange={e => { setError(''); setForm({ ...form, model_name: e.target.value }) }} placeholder="llama3.2:3b or gpt-4o-mini" style={{ width: '100%', padding: '10px 12px', borderRadius: 8 }} />
          </label>
          <label>
            <div style={{ fontSize: 11, color: 'var(--text-tertiary)', marginBottom: 4 }}>Display name</div>
            <input value={form.display_name} onChange={e => { setError(''); setForm({ ...form, display_name: e.target.value }) }} placeholder="Friendly label" style={{ width: '100%', padding: '10px 12px', borderRadius: 8 }} />
          </label>
          <label>
            <div style={{ fontSize: 11, color: 'var(--text-tertiary)', marginBottom: 4 }}>Supports</div>
            <input value={form.supports} onChange={e => { setError(''); setForm({ ...form, supports: e.target.value }) }} placeholder="simple, reasoning, writing, general" style={{ width: '100%', padding: '10px 12px', borderRadius: 8 }} />
          </label>
          <label>
            <div style={{ fontSize: 11, color: 'var(--text-tertiary)', marginBottom: 4 }}>Quality tier</div>
            <input type="number" min={1} max={5} value={form.quality_tier} onChange={e => setForm({ ...form, quality_tier: Number(e.target.value) })} style={{ width: '100%', padding: '10px 12px', borderRadius: 8 }} />
          </label>
          <label>
            <div style={{ fontSize: 11, color: 'var(--text-tertiary)', marginBottom: 4 }}>Input cost / 1K</div>
            <input type="number" min={0} step="0.000001" value={form.cost_in_per_1k} onChange={e => setForm({ ...form, cost_in_per_1k: Number(e.target.value) })} style={{ width: '100%', padding: '10px 12px', borderRadius: 8 }} />
          </label>
          <label>
            <div style={{ fontSize: 11, color: 'var(--text-tertiary)', marginBottom: 4 }}>Output cost / 1K</div>
            <input type="number" min={0} step="0.000001" value={form.cost_out_per_1k} onChange={e => setForm({ ...form, cost_out_per_1k: Number(e.target.value) })} style={{ width: '100%', padding: '10px 12px', borderRadius: 8 }} />
          </label>
          <label style={{ display: 'flex', alignItems: 'center', gap: 8, marginTop: 20 }}>
            <input type="checkbox" checked={form.enabled} onChange={e => setForm({ ...form, enabled: e.target.checked })} />
            <span style={{ fontSize: 13, color: 'var(--text-secondary)' }}>Enabled</span>
          </label>
          <label style={{ display: 'flex', alignItems: 'center', gap: 8, marginTop: 20 }}>
            <input type="checkbox" checked={form.candidate_enabled} onChange={e => setForm({ ...form, candidate_enabled: e.target.checked })} />
            <span style={{ fontSize: 13, color: 'var(--text-secondary)' }}>Candidate model</span>
          </label>
          <label style={{ display: 'flex', alignItems: 'center', gap: 8, marginTop: 20 }}>
            <input type="checkbox" checked={form.judge_eligible} onChange={e => setForm({ ...form, judge_eligible: e.target.checked })} />
            <span style={{ fontSize: 13, color: 'var(--text-secondary)' }}>Allow as judge</span>
          </label>
          {form.provider !== 'ollama' && (
            <label style={{ display: 'flex', alignItems: 'center', gap: 8, marginTop: 20 }}>
              <input type="checkbox" checked={form.local} onChange={e => setForm({ ...form, local: e.target.checked })} />
              <span style={{ fontSize: 13, color: 'var(--text-secondary)' }}>Treat as local/private</span>
            </label>
          )}
          </div>

          {form.provider === 'ollama' && (data?.ollama_models?.length ?? 0) > 0 && (
            <div style={{ marginTop: 14 }}>
              <div style={{ fontSize: 11, color: 'var(--text-tertiary)', marginBottom: 6 }}>Detected Ollama models</div>
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
                {data.ollama_models.map((modelName: string) => (
                  <button
                    key={modelName}
                    type="button"
                    onClick={() => {
                      setError('')
                      setForm({
                        ...form,
                        model_name: modelName,
                        display_name: form.display_name || `Local (${modelName})`,
                      })
                    }}
                    style={{
                      background: '#EEEDFE',
                      color: '#3C3489',
                      border: 'none',
                      borderRadius: 999,
                      padding: '6px 10px',
                      fontSize: 11,
                      cursor: 'pointer',
                    }}
                  >
                    {modelName}
                  </button>
                ))}
              </div>
            </div>
          )}

          <div style={{ display: 'flex', gap: 10, marginTop: 16, alignItems: 'center' }}>
            <button
              type="submit"
              disabled={saving || !form.model_name.trim()}
              style={{
                background: saving || !form.model_name.trim() ? '#9bb5d2' : '#185FA5',
                color: 'white',
                border: 'none',
                borderRadius: 8,
                padding: '10px 16px',
                cursor: saving || !form.model_name.trim() ? 'not-allowed' : 'pointer',
                opacity: saving || !form.model_name.trim() ? 0.7 : 1,
              }}
            >
            {saving ? 'Saving...' : editingId ? 'Save changes' : 'Add model'}
            </button>
            {editingId && (
              <button
                type="button"
                onClick={cancelEdit}
                style={{
                  background: 'transparent',
                  color: 'var(--text-secondary)',
                  border: '0.5px solid var(--border)',
                  borderRadius: 8,
                  padding: '10px 16px',
                  cursor: 'pointer',
                }}
              >
                Cancel
              </button>
            )}
            {!form.model_name.trim() && (
              <span style={{ fontSize: 12, color: 'var(--text-tertiary)' }}>
                Enter or pick a model name to enable the button.
              </span>
            )}
            {error && <span style={{ fontSize: 12, color: '#A32D2D' }}>{error}</span>}
          </div>
        </form>
      </div>

      <div className="card" style={{ padding: 24 }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 12, marginBottom: 14 }}>
          <div style={{ fontSize: 12, fontWeight: 500, color: 'var(--text-secondary)' }}>
          Configured models
          </div>
          {data?.judge_model_id && (
            <div style={{ fontSize: 11, color: 'var(--text-tertiary)' }}>
              Judge model selected from catalog
            </div>
          )}
        </div>
        <div style={{ display: 'grid', gap: 10 }}>
          {(data?.models ?? []).map((model: any) => (
            <div
              key={model.id}
              style={{
                display: 'grid',
                gridTemplateColumns: 'minmax(0, 1.6fr) minmax(180px, 0.8fr) minmax(260px, 1fr)',
                gap: 18,
                alignItems: 'center',
                background: 'var(--bg-secondary)',
                borderRadius: 12,
                padding: '16px 18px',
                border: data?.judge_model_id === model.id ? '1px solid #CFCBFF' : '1px solid transparent',
              }}
            >
              <div style={{ minWidth: 0 }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4, flexWrap: 'wrap' }}>
                  <div style={{ fontSize: 17, color: 'var(--text-primary)', fontWeight: 600 }}>
                    {model.display_name}
                  </div>
                  {data?.judge_model_id === model.id && (
                    <span className="badge" style={{ background: '#EEEDFE', color: '#3C3489' }}>
                      Judge
                    </span>
                  )}
                </div>
                <div style={{ fontSize: 12, color: 'var(--text-tertiary)', fontFamily: 'monospace', marginBottom: 10 }}>
                  {model.provider}:{model.model_name}
                </div>
                <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginBottom: 10 }}>
                  <span className="badge" style={{ background: model.enabled ? '#EAF3DE' : '#FCEBEB', color: model.enabled ? '#27500A' : '#A32D2D' }}>
                    {model.enabled ? 'Enabled' : 'Disabled'}
                  </span>
                  <span className="badge" style={{ background: model.local ? '#EEEDFE' : '#FAEEDA', color: model.local ? '#3C3489' : '#633806' }}>
                    {model.local ? 'Local' : 'Remote'}
                  </span>
                </div>
                <div style={{ fontSize: 12, color: 'var(--text-secondary)' }}>
                  Quality {model.quality_tier}/5
                  {model.supports?.length ? ` · ${model.supports.join(', ')}` : ''}
                </div>
              </div>

              <div style={{ display: 'grid', gap: 10 }}>
                <div>
                  <div style={mutedLabelStyle}>Input cost / 1K</div>
                  <div style={{ fontSize: 16, color: 'var(--text-primary)', marginTop: 2 }}>
                    ${Number(model.cost_in_per_1k).toFixed(6)}
                  </div>
                </div>
                <div>
                  <div style={mutedLabelStyle}>Output cost / 1K</div>
                  <div style={{ fontSize: 16, color: 'var(--text-primary)', marginTop: 2 }}>
                    ${Number(model.cost_out_per_1k).toFixed(6)}
                  </div>
                </div>
              </div>

              <div
                style={{
                  display: 'grid',
                  gridTemplateColumns: '1fr auto auto',
                  gap: 14,
                  alignItems: 'center',
                  justifyItems: 'end',
                  minWidth: 0,
                }}
              >
                <div style={{ display: 'flex', gap: 18, justifySelf: 'stretch', justifyContent: 'flex-end' }}>
                  <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 6 }}>
                    <span style={mutedLabelStyle}>Judge</span>
                    <Toggle
                      checked={data?.judge_model_id === model.id}
                      onClick={() => selectJudgeModel(data?.judge_model_id === model.id ? null : model.id)}
                      disabled={savingJudgeId === model.id || !model.judge_eligible}
                      label={model.judge_eligible ? 'Use as judge' : 'Judge disabled'}
                    />
                  </div>
                  <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 6 }}>
                    <span style={mutedLabelStyle}>Enabled</span>
                    <Toggle
                      checked={Boolean(model.enabled)}
                      onClick={() => toggleEnabled(model)}
                      label={model.enabled ? 'Disable model' : 'Enable model'}
                    />
                  </div>
                </div>

                <button
                  onClick={() => startEdit(model)}
                  style={{
                    background: '#EEEDFE',
                    border: 'none',
                    borderRadius: 999,
                    width: 36,
                    height: 36,
                    cursor: 'pointer',
                    color: '#3C3489',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    fontSize: 16,
                    flexShrink: 0,
                  }}
                  title="Edit model"
                  aria-label="Edit model"
                >
                  ✎
                </button>

                <button
                  onClick={() => remove(model.id)}
                  disabled={model.source === 'default'}
                  style={{
                    background: 'transparent',
                    border: '0.5px solid var(--border)',
                    borderRadius: 10,
                    padding: '9px 14px',
                    cursor: model.source === 'default' ? 'not-allowed' : 'pointer',
                    color: model.source === 'default' ? 'var(--text-tertiary)' : '#A32D2D',
                    fontSize: 13,
                    flexShrink: 0,
                    opacity: model.source === 'default' ? 0.7 : 1,
                  }}
                  title={model.source === 'default' ? 'Default catalog models cannot be removed. Disable or edit them instead.' : 'Remove model'}
                >
                  Remove
                </button>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}

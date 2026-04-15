'use client'
import { useEffect, useState } from 'react'
import { deleteModel, fetchModels, saveJudgeModel, saveModel } from '@/lib/api'
import {
  PageShell, PageHeader, TerminalCard, FieldLabel, TerminalInput,
  TerminalSelect, PrimaryButton, SecondaryButton, DangerButton, Badge,
  LoadingTerminal, ErrorBlock, NeuToggle,
} from '@/components/Terminal'

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

  if (loading) return <LoadingTerminal message="loading models" />
  if (error && !data) return <ErrorBlock message={error} />

  return (
    <PageShell>
      <PageHeader
        tag="system"
        title="MODELS"
        description="Configure the model catalog that report generation and live routing can choose from."
      />

      {error && <ErrorBlock message={error} />}

      {/* Add / edit form */}
      <TerminalCard title={editingId ? 'EDIT MODEL' : 'ADD MODEL'}>
        <form onSubmit={e => { e.preventDefault(); submit() }}>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 10 }}>
            <FieldLabel label="provider">
              <TerminalSelect value={form.provider} onChange={e => { setError(''); setForm({ ...form, provider: e.target.value, local: e.target.value === 'ollama' }) }}>
                {(data?.available_providers ?? []).map((provider: string) => (
                  <option key={provider} value={provider}>{provider}</option>
                ))}
              </TerminalSelect>
            </FieldLabel>
            <FieldLabel label="model_name">
              <TerminalInput value={form.model_name} onChange={e => { setError(''); setForm({ ...form, model_name: e.target.value }) }} placeholder="llama3.2:3b or gpt-4o-mini" />
            </FieldLabel>
            <FieldLabel label="display_name">
              <TerminalInput value={form.display_name} onChange={e => { setError(''); setForm({ ...form, display_name: e.target.value }) }} placeholder="Friendly label" />
            </FieldLabel>
            <FieldLabel label="supports">
              <TerminalInput value={form.supports} onChange={e => { setError(''); setForm({ ...form, supports: e.target.value }) }} placeholder="simple, reasoning, writing" />
            </FieldLabel>
            <FieldLabel label="quality_tier">
              <TerminalInput type="number" min={1} max={5} value={form.quality_tier} onChange={e => setForm({ ...form, quality_tier: Number(e.target.value) })} />
            </FieldLabel>
            <FieldLabel label="cost_in / 1K">
              <TerminalInput type="number" min={0} step="0.000001" value={form.cost_in_per_1k} onChange={e => setForm({ ...form, cost_in_per_1k: Number(e.target.value) })} />
            </FieldLabel>
            <FieldLabel label="cost_out / 1K">
              <TerminalInput type="number" min={0} step="0.000001" value={form.cost_out_per_1k} onChange={e => setForm({ ...form, cost_out_per_1k: Number(e.target.value) })} />
            </FieldLabel>
          </div>
          <div style={{ display: 'flex', gap: 14, marginTop: 12, flexWrap: 'wrap', alignItems: 'center' }}>
            <label style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 11, color: 'var(--text-secondary)', cursor: 'pointer' }}>
              <input type="checkbox" checked={form.enabled} onChange={e => setForm({ ...form, enabled: e.target.checked })} />
              enabled
            </label>
            <label style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 11, color: 'var(--text-secondary)', cursor: 'pointer' }}>
              <input type="checkbox" checked={form.candidate_enabled} onChange={e => setForm({ ...form, candidate_enabled: e.target.checked })} />
              candidate
            </label>
            <label style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 11, color: 'var(--text-secondary)', cursor: 'pointer' }}>
              <input type="checkbox" checked={form.judge_eligible} onChange={e => setForm({ ...form, judge_eligible: e.target.checked })} />
              judge
            </label>
            {form.provider !== 'ollama' && (
              <label style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 11, color: 'var(--text-secondary)', cursor: 'pointer' }}>
                <input type="checkbox" checked={form.local} onChange={e => setForm({ ...form, local: e.target.checked })} />
                local
              </label>
            )}
          </div>

          {form.provider === 'ollama' && (data?.ollama_models?.length ?? 0) > 0 && (
            <div style={{ marginTop: 12 }}>
              <div style={{ fontSize: 10, color: 'var(--text-tertiary)', marginBottom: 6 }}>Detected Ollama models:</div>
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
                {data.ollama_models.map((modelName: string) => (
                  <button
                    key={modelName}
                    type="button"
                    onClick={() => { setError(''); setForm({ ...form, model_name: modelName, display_name: form.display_name || `Local (${modelName})` }) }}
                    className="btn btn-secondary"
                    style={{ padding: '3px 8px', fontSize: 10 }}
                  >
                    {modelName}
                  </button>
                ))}
              </div>
            </div>
          )}

          <div style={{ display: 'flex', gap: 8, marginTop: 14, alignItems: 'center' }}>
            <PrimaryButton type="submit" disabled={saving || !form.model_name.trim()}>
              {saving ? 'SAVING...' : editingId ? 'SAVE CHANGES' : 'ADD MODEL'}
            </PrimaryButton>
            {editingId && (
              <SecondaryButton type="button" onClick={cancelEdit}>CANCEL</SecondaryButton>
            )}
          </div>
        </form>
      </TerminalCard>

      {/* Model list */}
      <TerminalCard title="CONFIGURED MODELS" headerRight={
        data?.judge_model_id ? <Badge variant="purple">JUDGE SELECTED</Badge> : undefined
      } noPadding>
        <table className="terminal-table" style={{ width: '100%' }}>
          <thead>
            <tr>
              <th>Model</th>
              <th>Provider</th>
              <th>Status</th>
              <th>Tier</th>
              <th>Cost in/out</th>
              <th>Judge</th>
              <th>Toggle</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {(data?.models ?? []).map((model: any) => {
              const isJudge = data?.judge_model_id === model.id
              return (
                <tr key={model.id}>
                  <td>
                    <div style={{ fontWeight: 700, color: '#3D4852' }}>{model.display_name}</div>
                    <div style={{ fontSize: 10, color: 'var(--text-tertiary)', marginTop: 2 }}>{model.model_name}</div>
                  </td>
                  <td>
                    <Badge variant={model.local ? 'purple' : 'amber'}>{model.provider}</Badge>
                  </td>
                  <td>
                    <Badge variant={model.enabled ? 'green' : 'red'}>{model.enabled ? 'ON' : 'OFF'}</Badge>
                  </td>
                  <td>{model.quality_tier}/5</td>
                  <td style={{ fontSize: 10 }}>
                    ${Number(model.cost_in_per_1k).toFixed(6)}<br />
                    ${Number(model.cost_out_per_1k).toFixed(6)}
                  </td>
                  <td>
                    <NeuToggle
                      checked={isJudge}
                      onClick={() => selectJudgeModel(isJudge ? null : model.id)}
                      disabled={savingJudgeId === model.id || !model.judge_eligible}
                      label={model.judge_eligible ? 'Use as judge' : 'Judge disabled'}
                      variant="judge"
                    />
                  </td>
                  <td>
                    <NeuToggle
                      checked={Boolean(model.enabled)}
                      onClick={() => toggleEnabled(model)}
                      label={model.enabled ? 'Disable model' : 'Enable model'}
                    />
                  </td>
                  <td>
                    <div style={{ display: 'flex', gap: 6 }}>
                      <SecondaryButton onClick={() => startEdit(model)} style={{ padding: '2px 8px', fontSize: 9 }}>EDIT</SecondaryButton>
                      <DangerButton onClick={() => remove(model.id)} disabled={model.source === 'default'} style={{ padding: '2px 8px', fontSize: 9 }}>DEL</DangerButton>
                    </div>
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </TerminalCard>
    </PageShell>
  )
}

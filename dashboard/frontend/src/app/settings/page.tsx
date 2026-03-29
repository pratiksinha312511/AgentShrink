'use client'
import { useEffect, useState } from 'react'
import { fetchConfig } from '@/lib/api'

export default function SettingsPage() {
  const [config, setConfig] = useState<any>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  useEffect(() => {
    fetchConfig()
      .then(setConfig)
      .catch(e => setError(e.message))
      .finally(() => setLoading(false))
  }, [])

  if (loading) return <div style={{ color: 'var(--text-tertiary)', padding: 40, textAlign: 'center' }}>Loading settings...</div>
  if (error) return <div className="card" style={{ padding: 24, maxWidth: 900 }}>{error}</div>

  const items = [
    ['Target provider', config.target_agent_provider],
    ['Local model', config.target_agent_ollama_model],
    ['Fallback API model', config.target_agent_openai_model],
    ['Ollama host', config.ollama_host],
    ['Eval samples / cluster', config.eval_samples_per_cluster],
    ['Remote min interval (s)', config.remote_min_interval_s],
    ['Judge min interval (s)', config.judge_min_interval_s],
    ['Confidence threshold', config.confidence_threshold],
    ['Quality threshold', config.quality_threshold],
    ['Configured models', config.model_count],
    ['Database', config.db_path],
    ['Output dir', config.output_dir],
  ]

  return (
    <div style={{ maxWidth: 900 }}>
      <div className="card" style={{ padding: 24, marginBottom: 16 }}>
        <h1 style={{ fontSize: 22, fontWeight: 500, marginBottom: 8 }}>Settings</h1>
        <p style={{ color: 'var(--text-secondary)', lineHeight: 1.7, marginBottom: 16 }}>
          This page shows the runtime configuration that AgentShrink is currently using.
        </p>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
          {items.map(([label, value]) => (
            <div key={String(label)} style={{ background: 'var(--bg-secondary)', borderRadius: 8, padding: '12px 14px' }}>
              <div style={{ fontSize: 11, color: 'var(--text-tertiary)', textTransform: 'uppercase', marginBottom: 4 }}>{label}</div>
              <div style={{ fontSize: 13, color: 'var(--text-primary)', wordBreak: 'break-word' }}>{value}</div>
            </div>
          ))}
        </div>
      </div>

      <div className="card" style={{ padding: 24 }}>
        <div style={{ fontSize: 12, fontWeight: 500, color: 'var(--text-secondary)', marginBottom: 12 }}>Current readiness</div>
        <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
          <span className="badge" style={{ background: config.analysis_exists ? '#EAF3DE' : '#FCEBEB', color: config.analysis_exists ? '#27500A' : '#A32D2D' }}>
            Analysis {config.analysis_exists ? 'available' : 'missing'}
          </span>
          <span className="badge" style={{ background: config.heuristic_report ? '#FAEEDA' : '#EEEDFE', color: config.heuristic_report ? '#633806' : '#3C3489' }}>
            {config.heuristic_report ? 'Heuristic report active' : 'Saved report available'}
          </span>
          <span className="badge" style={{ background: '#EEEDFE', color: '#3C3489' }}>
            {config.cluster_count} clusters loaded
          </span>
        </div>
      </div>

      <div className="card" style={{ padding: 24, marginTop: 16 }}>
        <div style={{ fontSize: 12, fontWeight: 500, color: 'var(--text-secondary)', marginBottom: 12 }}>
          Manual adopt, automatic route
        </div>
        <div style={{ fontSize: 13, color: 'var(--text-secondary)', lineHeight: 1.8 }}>
          AgentShrink does not rewrite your whole agent automatically. The expected product flow is:
          <br />
          1. You manually switch your agent to use <code>ShrinkLLM</code>.
          <br />
          2. After that one-time adoption step, every future model call is routed automatically using the saved routing config.
          <br />
          3. Use <code>target_agent/run_shrink_demo.py</code> as the current demo of this workflow.
        </div>
      </div>
    </div>
  )
}

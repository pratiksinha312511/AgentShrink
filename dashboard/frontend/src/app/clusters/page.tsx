'use client'
import { useEffect, useState } from 'react'
import { ScatterChart, Scatter, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell } from 'recharts'
import { fetchClusters } from '@/lib/api'

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

  useEffect(() => {
    fetchClusters()
      .then(setData)
      .catch(e => setError(e.message))
      .finally(() => setLoading(false))
  }, [])

  if (loading) return <div style={{ color: 'var(--text-tertiary)', padding: 40, textAlign: 'center' }}>Loading cluster map...</div>

  if (error) return (
    <div className="card" style={{ padding: 32, textAlign: 'center' }}>
      <div style={{ fontSize: 15, fontWeight: 500, color: 'var(--text-primary)', marginBottom: 8 }}>No cluster data yet</div>
      <div style={{ fontSize: 13, color: 'var(--text-secondary)' }}>Run: <code>agentshrink analyse</code></div>
    </div>
  )

  const clusterIds = Object.keys(data?.cluster_names ?? {})

  // Filter points by selected cluster
  const visiblePoints = selected
    ? data?.points.filter(p => String(p.cluster_id) === selected) ?? []
    : data?.points ?? []

  return (
    <div style={{ maxWidth: 900 }}>
      <div style={{ marginBottom: 24 }}>
        <h1 style={{ fontSize: 22, fontWeight: 500, color: 'var(--text-primary)', marginBottom: 4 }}>Cluster Map</h1>
        <div style={{ fontSize: 13, color: 'var(--text-secondary)' }}>
          {data?.points.length ?? 0} prompts → {data?.n_clusters ?? 0} task clusters
          {(data?.n_noise ?? 0) > 0 && ` (${data?.n_noise} noise points excluded)`}
        </div>
      </div>

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
              <div style={{ display: 'flex', alignItems: 'center', gap: 7, marginBottom: 6 }}>
                <span style={{ width: 8, height: 8, borderRadius: '50%', background: color, flexShrink: 0 }} />
                <div style={{ fontSize: 12, fontWeight: 500, color: 'var(--text-primary)' }}>{name}</div>
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

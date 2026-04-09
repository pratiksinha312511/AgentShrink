'use client'

import { useEffect, useState } from 'react'
import { activatePublicProject, fetchPublicProjects } from '@/lib/api'

type RegistryPayload = {
  active_project_id?: string
  projects?: Array<{ id: string; name: string; environment?: string }>
}

export default function ProjectScopeBar({
  selectedProjectId,
  onChange,
}: {
  selectedProjectId?: string
  onChange: (projectId: string) => void
}) {
  const [data, setData] = useState<RegistryPayload | null>(null)
  const [switching, setSwitching] = useState(false)
  const [message, setMessage] = useState('')

  useEffect(() => {
    fetchPublicProjects().then(setData).catch(() => {})
  }, [])

  const currentId = selectedProjectId || data?.active_project_id || ''
  const activeId = data?.active_project_id || ''

  const activate = async () => {
    if (!currentId || currentId === activeId) return
    setSwitching(true)
    setMessage('')
    try {
      const next = await activatePublicProject(currentId)
      setData(next)
      setMessage('Active project updated. Restart the stack if you want runtime ports and DB wiring to switch too.')
    } catch (e: any) {
      setMessage(e.message || 'Failed to activate project')
    } finally {
      setSwitching(false)
    }
  }

  return (
    <div className="card" style={{ padding: 16, marginBottom: 16 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12, alignItems: 'center', flexWrap: 'wrap' }}>
        <div>
          <div style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-secondary)', marginBottom: 6 }}>Project scope</div>
          <div style={{ fontSize: 13, color: 'var(--text-secondary)' }}>
            These pages can now view routing and report data by project. The active project is the default scope.
          </div>
        </div>
        <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
          <select value={currentId} onChange={(e) => onChange(e.target.value)} style={inputStyle}>
            {(data?.projects || []).map((project) => (
              <option key={project.id} value={project.id}>
                {project.name} ({project.environment || 'local'})
              </option>
            ))}
          </select>
          <button onClick={activate} disabled={switching || !currentId || currentId === activeId} style={{ ...buttonStyle, opacity: switching || !currentId || currentId === activeId ? 0.65 : 1 }}>
            {switching ? 'Switching...' : 'Make active'}
          </button>
        </div>
      </div>
      {message && (
        <div style={{ marginTop: 10, fontSize: 12, color: message.toLowerCase().includes('failed') ? '#A32D2D' : '#27500A' }}>
          {message}
        </div>
      )}
    </div>
  )
}

const inputStyle = {
  borderRadius: 10,
  border: '0.5px solid var(--border)',
  background: 'var(--bg-primary)',
  color: 'var(--text-primary)',
  padding: '10px 12px',
  fontSize: 13,
  minWidth: 240,
} as const

const buttonStyle = {
  border: '0.5px solid var(--border)',
  borderRadius: 8,
  background: 'var(--bg-primary)',
  color: 'var(--text-primary)',
  fontSize: 12,
  fontWeight: 600,
  padding: '8px 10px',
  cursor: 'pointer',
} as const

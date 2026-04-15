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
      setMessage('Active project updated. Restart the stack if you want runtime to switch.')
    } catch (e: any) {
      setMessage(`Error: ${e.message || 'Failed to activate project'}`)
    } finally {
      setSwitching(false)
    }
  }

  return (
    <div className="card" style={{ padding: 16, marginBottom: 16, borderRadius: 20 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12, alignItems: 'center', flexWrap: 'wrap' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <span style={{ fontSize: 12, color: '#6B7280', fontWeight: 600 }}>Project</span>
          <select className="terminal-select" value={currentId} onChange={(e) => onChange(e.target.value)} style={{ minWidth: 240, padding: '10px 36px 10px 14px' }}>
            {(data?.projects || []).map((project) => (
              <option key={project.id} value={project.id}>
                {project.name} ({project.environment || 'local'})
              </option>
            ))}
          </select>
        </div>
        <button
          className="btn btn-secondary"
          onClick={activate}
          disabled={switching || !currentId || currentId === activeId}
          style={{ padding: '8px 16px', fontSize: 12 }}
        >
          {switching ? 'Switching...' : 'Make Active'}
        </button>
      </div>
      {message && (
        <div style={{
          marginTop: 10,
          fontSize: 12,
          fontWeight: 500,
          color: message.startsWith('Error') ? '#C53030' : '#2C9A94',
        }}>
          {message}
        </div>
      )}
    </div>
  )
}

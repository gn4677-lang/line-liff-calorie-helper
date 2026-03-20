import { useState } from 'react'
import { adminApi, setStoredAdminToken } from './adminApi'
import type { AdminSession } from './adminTypes'

type Props = {
  onAuthenticated: (token: string, session: AdminSession) => void
}

export default function AdminAuthGate({ onAuthenticated }: Props) {
  const [passcode, setPasscode] = useState('')
  const [label, setLabel] = useState('observability-admin')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function handleSubmit() {
    setLoading(true)
    setError(null)
    try {
      const response = await adminApi<{ session: AdminSession }>('/api/admin/login', null, {
        method: 'POST',
        body: JSON.stringify({ passcode, label }),
      })
      const session = response.payload.session
      if (!session.token) {
        throw new Error('Missing admin session token.')
      }
      setStoredAdminToken(session.token)
      onAuthenticated(session.token, session)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Admin login failed.')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="admin-login">
      <div className="card admin-login-card">
        <div className="admin-panel-header">
          <div>
            <h1 className="text-title">Observability Admin</h1>
            <p className="text-caption text-secondary">Internal desktop tool for debugging quality, memory, errors, and traces.</p>
          </div>
        </div>
        <div style={{ display: 'grid', gap: 12 }}>
          <div>
            <label className="text-micro text-muted" style={{ display: 'block', marginBottom: 6 }}>Admin label</label>
            <input className="input-field" value={label} onChange={(event) => setLabel(event.target.value)} />
          </div>
          <div>
            <label className="text-micro text-muted" style={{ display: 'block', marginBottom: 6 }}>Passcode</label>
            <input className="input-field" type="password" value={passcode} onChange={(event) => setPasscode(event.target.value)} />
          </div>
          {error ? <p className="text-caption" style={{ color: 'var(--danger)' }}>{error}</p> : null}
          <button className="btn btn-primary" onClick={handleSubmit} disabled={loading || !passcode}>
            {loading ? 'Signing in...' : 'Enter Admin'}
          </button>
        </div>
      </div>
    </div>
  )
}

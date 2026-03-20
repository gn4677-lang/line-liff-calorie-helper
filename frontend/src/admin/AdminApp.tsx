import { useEffect, useState } from 'react'
import './admin.css'
import AdminAuthGate from './AdminAuthGate'
import { adminApi, clearStoredAdminToken, getStoredAdminToken } from './adminApi'
import type { AdminSession } from './adminTypes'
import ObservabilityDashboardPage from './pages/ObservabilityDashboardPage'

export default function AdminApp() {
  const [token, setToken] = useState<string | null>(null)
  const [session, setSession] = useState<AdminSession | null>(null)
  const [booting, setBooting] = useState(true)

  useEffect(() => {
    async function restoreSession() {
      const storedToken = getStoredAdminToken()
      if (!storedToken) {
        setBooting(false)
        return
      }
      try {
        const response = await adminApi<{ session: AdminSession }>('/api/admin/me', storedToken)
        setToken(storedToken)
        setSession(response.payload.session)
      } catch {
        clearStoredAdminToken()
      } finally {
        setBooting(false)
      }
    }
    void restoreSession()
  }, [])

  function handleAuthenticated(nextToken: string, nextSession: AdminSession) {
    setToken(nextToken)
    setSession(nextSession)
  }

  async function handleLogout() {
    if (token) {
      try {
        await adminApi<Record<string, unknown>>('/api/admin/logout', token, { method: 'POST' })
      } catch {
        // Ignore logout failures and clear local session anyway.
      }
    }
    clearStoredAdminToken()
    setToken(null)
    setSession(null)
  }

  if (booting) {
    return <div className="admin-login"><div className="card admin-login-card">Restoring admin session...</div></div>
  }

  if (!token || !session) {
    return <AdminAuthGate onAuthenticated={handleAuthenticated} />
  }

  return (
    <ObservabilityDashboardPage
      token={token}
      session={session}
      onSessionInvalid={() => {
        setToken(null)
        setSession(null)
      }}
      onLogout={() => { void handleLogout() }}
    />
  )
}

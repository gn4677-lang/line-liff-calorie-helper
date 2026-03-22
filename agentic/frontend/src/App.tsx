import { startTransition, useEffect, useState } from 'react'
import liff from '@line/liff'

import { getClientConfig, getHome, getMe } from './api'
import type { AuthHeaders, HomeKey, HomePayload, MeResponse } from './types'
import TodayPage from './pages/TodayPage'
import EatPage from './pages/EatPage'
import ProgressPage from './pages/ProgressPage'
import SettingsPage from './pages/SettingsPage'

const TAB_LABELS: Record<HomeKey, string> = {
  today: 'Today',
  eat: 'Eat',
  progress: 'Progress',
  settings: 'Settings',
}

type AuthState =
  | { status: 'booting'; message: string; headers: AuthHeaders; me: null }
  | { status: 'ready'; message: string; headers: AuthHeaders; me: MeResponse }
  | { status: 'error'; message: string; headers: AuthHeaders; me: null }

export default function App() {
  const [activeTab, setActiveTab] = useState<HomeKey>('today')
  const [homes, setHomes] = useState<Partial<Record<HomeKey, HomePayload>>>({})
  const [status, setStatus] = useState('booting')
  const [auth, setAuth] = useState<AuthState>({
    status: 'booting',
    message: 'Connecting to LINE or app session...',
    headers: {},
    me: null,
  })

  useEffect(() => {
    let cancelled = false
    async function bootstrap() {
      try {
        const me = await getMe()
        if (cancelled) return
        setAuth({ status: 'ready', message: 'Connected via app session.', headers: {}, me })
        return
      } catch {
        // Fall through to LIFF or demo bootstrap.
      }

      try {
        const config = await getClientConfig()
        if (config.liff_id) {
          await liff.init({ liffId: config.liff_id })
          if (!liff.isLoggedIn()) {
            liff.login({ redirectUri: window.location.href })
            return
          }
          const idToken = liff.getIDToken()
          if (!idToken) {
            throw new Error('LIFF did not return a usable ID token.')
          }
          const headers = { 'X-Line-Id-Token': idToken }
          const me = await getMe(headers)
          if (cancelled) return
          setAuth({ status: 'ready', message: 'Connected via LIFF.', headers, me })
          return
        }
        const demoHeaders: AuthHeaders = import.meta.env.DEV
          ? { 'X-Line-User-Id': 'agentic-demo-user', 'X-Display-Name': 'Agentic Demo' }
          : {}
        if (!config.auth_required || Object.keys(demoHeaders).length > 0) {
          const me = await getMe(demoHeaders)
          if (cancelled) return
          setAuth({
            status: 'ready',
            message: Object.keys(demoHeaders).length > 0 ? 'Connected in local demo mode.' : 'Connected.',
            headers: demoHeaders,
            me,
          })
          return
        }
        throw new Error('LINE auth is required and no app session is available.')
      } catch (error) {
        if (cancelled) return
        setAuth({
          status: 'error',
          message: error instanceof Error ? error.message : 'Auth bootstrap failed.',
          headers: {},
          me: null,
        })
      }
    }
    void bootstrap()
    return () => {
      cancelled = true
    }
  }, [])

  useEffect(() => {
    if (auth.status !== 'ready') {
      return
    }
    let cancelled = false
    setStatus('loading')
    void getHome(activeTab, auth.headers)
      .then((payload) => {
        if (cancelled) return
        setHomes((current) => ({ ...current, [activeTab]: payload }))
        setStatus('ready')
      })
      .catch((error) => {
        if (cancelled) return
        setStatus(error instanceof Error ? error.message : 'Failed to load the current home.')
      })
    return () => {
      cancelled = true
    }
  }, [activeTab, auth])

  const current = homes[activeTab]

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div>
          <div className="brand">Agentic Rewrite</div>
          <p className="brand-copy">LINE-first delivery, LIFF-first decision home.</p>
          <p className="brand-copy">{auth.message}</p>
          {auth.status === 'ready' ? (
            <p className="brand-copy">
              {auth.me.display_name} · {auth.me.cohort} · {auth.me.core_version}
            </p>
          ) : null}
        </div>
        <nav className="nav-list">
          {(Object.keys(TAB_LABELS) as HomeKey[]).map((key) => (
            <button
              key={key}
              className={activeTab === key ? 'nav-item active' : 'nav-item'}
              onClick={() =>
                startTransition(() => {
                  setActiveTab(key)
                })
              }
            >
              {TAB_LABELS[key]}
            </button>
          ))}
        </nav>
      </aside>

      <main className="main-panel">
        {auth.status === 'booting' ? <div className="state-card">Booting auth...</div> : null}
        {auth.status === 'error' ? <div className="state-card error">{auth.message}</div> : null}
        {auth.status === 'ready' && status === 'loading' && !current ? (
          <div className="state-card">Loading {TAB_LABELS[activeTab]}...</div>
        ) : null}
        {auth.status === 'ready' && status !== 'ready' && status !== 'loading' ? (
          <div className="state-card error">{status}</div>
        ) : null}
        {auth.status === 'ready' && current ? (
          <PageRenderer tab={activeTab} payload={current} authHeaders={auth.headers} />
        ) : null}
      </main>
    </div>
  )
}

function PageRenderer({
  tab,
  payload,
  authHeaders,
}: {
  tab: HomeKey
  payload: HomePayload
  authHeaders: AuthHeaders
}) {
  if (tab === 'eat') return <EatPage payload={payload} authHeaders={authHeaders} />
  if (tab === 'progress') return <ProgressPage payload={payload} authHeaders={authHeaders} />
  if (tab === 'settings') return <SettingsPage payload={payload} authHeaders={authHeaders} />
  return <TodayPage payload={payload} authHeaders={authHeaders} />
}

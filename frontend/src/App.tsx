import './App.css'
import { AppProvider, useApp } from './AppContext'
import AdminApp from './admin/AdminApp'
import { api } from './api'
import type { Preferences } from './types'
import { HARD_DISLIKE_OPTIONS, TAB_ICONS, TAB_KEYS, TAB_LABELS } from './types'
import EatPage from './pages/EatPage'
import ProgressPage from './pages/ProgressPage'
import TodayPage from './pages/TodayPage'

function OnboardingModal() {
  const {
    auth,
    onboarding,
    setOnboarding,
    onboardingForm,
    setOnboardingForm,
    setMessage,
    setLoading,
    loading,
  } = useApp()

  if (auth.status !== 'ready' || !onboarding?.should_show) return null

  function toggleDislike(item: string) {
    setOnboardingForm((previous: Preferences) => {
      if (item === 'none') {
        return { ...previous, hard_dislikes: ['none'] }
      }
      const active = previous.hard_dislikes.filter((value) => value !== 'none')
      return {
        ...previous,
        hard_dislikes: active.includes(item)
          ? active.filter((value) => value !== item)
          : active.length < 3
            ? [...active, item]
            : active,
      }
    })
  }

  async function handleSubmit() {
    setLoading(true)
    try {
      const data = await api<{
        coach_message: string
        payload: {
          onboarding_state: typeof onboarding
        }
      }>('/api/preferences/onboarding', auth.headers, {
        method: 'POST',
        body: JSON.stringify(onboardingForm),
      })
      setMessage(data.coach_message)
      setOnboarding(data.payload.onboarding_state)
    } catch (error) {
      setMessage(error instanceof Error ? error.message : '儲存偏好時發生問題。')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="modal-backdrop">
      <div className="card animated onboarding-modal">
        <h2 className="text-title font-bold">先校準你的飲食輪廓</h2>
        <p className="text-caption text-secondary onboarding-copy">
          這一步只做一次。讓系統先知道你的早餐習慣、碳水需求，還有明確不吃的東西。
        </p>

        <div className="stack onboarding-stack">
          <div>
            <label className="text-micro font-bold text-muted form-label">早餐習慣</label>
            <select
              className="input-field"
              value={onboardingForm.breakfast_habit}
              onChange={(event) =>
                setOnboardingForm((previous) => ({
                  ...previous,
                  breakfast_habit: event.target.value as Preferences['breakfast_habit'],
                }))
              }
            >
              <option value="regular">幾乎每天吃</option>
              <option value="occasional">偶爾吃</option>
              <option value="rare">很少吃</option>
              <option value="variable">看情況</option>
            </select>
          </div>

          <div>
            <label className="text-micro font-bold text-muted form-label">碳水需求</label>
            <select
              className="input-field"
              value={onboardingForm.carb_need}
              onChange={(event) =>
                setOnboardingForm((previous) => ({
                  ...previous,
                  carb_need: event.target.value as Preferences['carb_need'],
                }))
              }
            >
              <option value="high">需要飽足感</option>
              <option value="flexible">彈性即可</option>
              <option value="low">想吃得清爽一點</option>
            </select>
          </div>

          <div>
            <label className="text-micro font-bold text-muted form-label">明確不想看到</label>
            <div className="chip-row onboarding-chip-row">
              {HARD_DISLIKE_OPTIONS.map((item) => {
                const disabled = onboardingForm.hard_dislikes.length >= 3 && !onboardingForm.hard_dislikes.includes(item) && item !== 'none'
                const active = onboardingForm.hard_dislikes.includes(item)
                return (
                  <button
                    key={item}
                    type="button"
                    className={`chip-button ${active ? 'chip-button--active' : ''}`}
                    disabled={disabled}
                    onClick={() => toggleDislike(item)}
                  >
                    {item === 'none' ? '沒有' : item}
                  </button>
                )
              })}
            </div>
          </div>
        </div>

        <button className="btn btn-primary onboarding-submit" onClick={() => void handleSubmit()} disabled={loading}>
          {loading ? '儲存中...' : '開始使用'}
        </button>
      </div>
    </div>
  )
}

function BottomNav() {
  const { activeTab, setActiveTab } = useApp()

  return (
    <nav className="bottom-nav">
      {TAB_KEYS.map((key) => (
        <button
          key={key}
          type="button"
          className={`nav-item ${activeTab === key ? 'active' : ''}`}
          onClick={() => setActiveTab(key)}
        >
          <span className="nav-icon" dangerouslySetInnerHTML={{ __html: TAB_ICONS[key] }} />
          <span>{TAB_LABELS[key]}</span>
        </button>
      ))}
    </nav>
  )
}

function PageRouter() {
  const { activeTab } = useApp()

  if (activeTab === 'eat') return <EatPage />
  if (activeTab === 'progress') return <ProgressPage />
  return <TodayPage />
}

function AppShell() {
  const { auth } = useApp()

  if (auth.status === 'booting') {
    return (
      <div className="full-screen-state">
        <h1 className="text-title font-bold">LIFF Auth Failed</h1>
        <p className="text-caption text-muted state-copy">{auth.message}</p>
      </div>
    )
  }

  if (auth.status === 'error') {
    return (
      <div className="full-screen-state error">
        <h1 className="text-title font-bold">LIFF 無法啟動</h1>
        <p className="text-body text-secondary state-copy">{auth.message}</p>
        <button className="btn btn-primary" type="button" onClick={() => window.location.reload()}>
          Reload
        </button>
      </div>
    )
  }

  return (
    <div className="app-shell">
      <OnboardingModal />
      <PageRouter />
      <BottomNav />
    </div>
  )
}

export default function App() {
  if (window.location.pathname.startsWith('/admin/observability')) {
    return <AdminApp />
  }

  return (
    <AppProvider>
      <AppShell />
    </AppProvider>
  )
}

import { useEffect, useMemo, useState } from 'react'
import type { FormEvent } from 'react'
import liff from '@line/liff'
import './App.css'

type Draft = {
  id: string
  meal_session_id?: string | null
  date: string
  event_at?: string | null
  meal_type: string
  status: string
  source_mode: string
  mode: string
  parsed_items: Array<{ name: string; kcal?: number }>
  missing_slots: string[]
  followup_question?: string | null
  estimate_kcal: number
  kcal_low: number
  kcal_high: number
  confidence: number
  uncertainty_note: string
  metadata?: Record<string, unknown>
}

type Summary = {
  date: string
  target_kcal: number
  consumed_kcal: number
  remaining_kcal: number
  logs: Array<{
    id: number
    meal_type: string
    description_raw: string
    kcal_estimate: number
    confidence: number
  }>
  seven_day_average_weight?: number | null
  fourteen_day_direction: string
  target_adjustment_hint: string
}

type Recommendation = {
  name: string
  kcal_low: number
  kcal_high: number
  group: string
  reason: string
  reason_factors: string[]
  is_favorite?: boolean
  is_golden?: boolean
}

type DayPlan = {
  allocations: Record<string, number>
  reason_factors: string[]
}

type CompensationOption = {
  label: string
  daily_adjustment: number
  days: number
  note: string
}

type Compensation = {
  options: CompensationOption[]
  reason_factors: string[]
}

type MeResponse = {
  line_user_id: string
  display_name: string
  daily_calorie_target: number
  provider: string
  now: string
}

type ClientConfig = {
  liff_id?: string | null
  auth_required: boolean
}

type Preferences = {
  breakfast_habit: 'regular' | 'occasional' | 'rare' | 'variable' | 'unknown'
  carb_need: 'high' | 'flexible' | 'low' | 'variable'
  dinner_style: 'light' | 'normal' | 'indulgent' | 'high_protein' | 'variable'
  hard_dislikes: string[]
  compensation_style: 'normal_return' | 'gentle_1d' | 'distributed_2_3d' | 'let_system_decide' | 'gentle'
}

type OnboardingState = {
  should_show: boolean
  completed: boolean
  skipped: boolean
  version: string
  preferences: Preferences
}

type AuthState =
  | { status: 'booting'; message: string; headers: Record<string, string> }
  | { status: 'ready'; message: string; headers: Record<string, string>; me: MeResponse }
  | { status: 'error'; message: string; headers: Record<string, string> }

type TabKey = 'today' | 'progress' | 'eat'

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? ''
const TAB_KEYS: TabKey[] = ['today', 'progress', 'eat']
const TAB_LABELS: Record<TabKey, string> = {
  today: '今日紀錄',
  progress: '體重熱量',
  eat: '食物推薦',
}

const MEAL_TYPE_LABELS: Record<string, string> = {
  breakfast: '早餐',
  lunch: '午餐',
  dinner: '晚餐',
  snack: '點心',
}

const PLAN_KEY_LABELS: Record<string, string> = {
  breakfast: '早餐',
  lunch: '午餐',
  dinner: '晚餐',
  flex: '彈性額度',
}

const DEFAULT_ONBOARDING: Preferences = {
  breakfast_habit: 'variable',
  carb_need: 'flexible',
  dinner_style: 'normal',
  hard_dislikes: [],
  compensation_style: 'let_system_decide',
}

const HARD_DISLIKE_OPTIONS = [
  '韓式',
  '炸物',
  '手搖 / 含糖飲料',
  '早餐店',
  '沙拉 / 冷食',
  '便利商店',
  'none',
]

function resolveInitialTab(): TabKey {
  const tab = new URLSearchParams(window.location.search).get('tab')
  return TAB_KEYS.includes(tab as TabKey) ? (tab as TabKey) : 'today'
}

async function api<T>(path: string, authHeaders: Record<string, string>, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    headers: {
      ...(init?.body ? { 'Content-Type': 'application/json' } : {}),
      ...authHeaders,
      ...(init?.headers ?? {}),
    },
    ...init,
  })

  if (!response.ok) {
    const text = await response.text()
    throw new Error(text || `Request failed: ${response.status}`)
  }

  return response.json() as Promise<T>
}

function App() {
  const [auth, setAuth] = useState<AuthState>({
    status: 'booting',
    message: 'Booting LIFF session...',
    headers: {},
  })
  const [activeTab, setActiveTab] = useState<TabKey>(() => resolveInitialTab())
  const [text, setText] = useState('')
  const [mealType, setMealType] = useState('lunch')
  const [mode, setMode] = useState('standard')
  const [clarifyText, setClarifyText] = useState('')
  const [weight, setWeight] = useState('')
  const [extraKcal, setExtraKcal] = useState('600')
  const [draft, setDraft] = useState<Draft | null>(null)
  const [summary, setSummary] = useState<Summary | null>(null)
  const [recommendations, setRecommendations] = useState<Recommendation[]>([])
  const [dayPlan, setDayPlan] = useState<DayPlan | null>(null)
  const [compensation, setCompensation] = useState<Compensation | null>(null)
  const [onboarding, setOnboarding] = useState<OnboardingState | null>(null)
  const [onboardingForm, setOnboardingForm] = useState<Preferences>(DEFAULT_ONBOARDING)
  const [message, setMessage] = useState('準備好了。')
  const [loading, setLoading] = useState(false)

  const groupedRecommendations = useMemo(() => {
    return recommendations.reduce<Record<string, Recommendation[]>>((acc, item) => {
      acc[item.group] ??= []
      acc[item.group].push(item)
      return acc
    }, {})
  }, [recommendations])

  useEffect(() => {
    async function bootstrapAuth() {
      try {
        const config = await api<ClientConfig>('/api/client-config', {})
        const usingLiff = Boolean(config.liff_id)

        if (usingLiff && config.liff_id) {
          await liff.init({ liffId: config.liff_id })

          if (!liff.isLoggedIn()) {
            liff.login({ redirectUri: window.location.href })
            return
          }

          const idToken = liff.getIDToken()
          if (!idToken) {
            throw new Error('LIFF login succeeded but no ID token was returned.')
          }

          const me = await api<MeResponse>('/api/me', { 'X-Line-Id-Token': idToken })
          setAuth({
            status: 'ready',
            message: 'LIFF session ready.',
            headers: { 'X-Line-Id-Token': idToken },
            me,
          })
          return
        }

        if (config.auth_required) {
          throw new Error('LIFF auth is required but no LIFF ID is configured on the backend.')
        }

        const demoHeaders: Record<string, string> = import.meta.env.DEV
          ? { 'X-Line-User-Id': 'demo-user', 'X-Display-Name': 'Demo User' }
          : {}
        const me = await api<MeResponse>('/api/me', demoHeaders)
        setAuth({
          status: 'ready',
          message: 'Using local development auth.',
          headers: demoHeaders,
          me,
        })
      } catch (error) {
        setAuth({
          status: 'error',
          message: error instanceof Error ? error.message : 'Failed to initialize LIFF auth.',
          headers: {},
        })
      }
    }

    void bootstrapAuth()
  }, [])

  useEffect(() => {
    if (auth.status !== 'ready') return

    async function bootstrapData() {
      const [summaryData, recData, onboardingState] = await Promise.all([
        api<{ summary: Summary; coach_message: string }>('/api/day-summary', auth.headers),
        api<{ recommendations: { items: Recommendation[] }; coach_message: string }>('/api/recommendations', auth.headers),
        api<OnboardingState>('/api/onboarding-state', auth.headers),
      ])
      setSummary(summaryData.summary)
      setRecommendations(recData.recommendations.items)
      setOnboarding(onboardingState)
      setOnboardingForm({
        ...DEFAULT_ONBOARDING,
        ...onboardingState.preferences,
        hard_dislikes: onboardingState.preferences.hard_dislikes ?? [],
      })
      setMessage(summaryData.coach_message)
    }

    void bootstrapData()
  }, [auth])

  async function refreshRecommendations() {
    if (auth.status !== 'ready') return
    const data = await api<{ recommendations: { items: Recommendation[] }; coach_message: string }>(
      '/api/recommendations',
      auth.headers,
    )
    setRecommendations(data.recommendations.items)
    setMessage(data.coach_message)
  }

  async function handleOnboardingSubmit(event: FormEvent) {
    event.preventDefault()
    if (auth.status !== 'ready') return
    setLoading(true)
    try {
      const payload = await api<{ payload: { onboarding_state: OnboardingState } }>(
        '/api/preferences/onboarding',
        auth.headers,
        {
          method: 'POST',
          body: JSON.stringify(onboardingForm),
        },
      )
      setOnboarding(payload.payload.onboarding_state)
      setMessage('已完成冷啟動設定，接下來會用這些偏好幫你做推薦。')
      await refreshRecommendations()
    } finally {
      setLoading(false)
    }
  }

  async function handleOnboardingSkip() {
    if (auth.status !== 'ready') return
    setLoading(true)
    try {
      const state = await api<OnboardingState>('/api/onboarding/skip', auth.headers, { method: 'POST' })
      setOnboarding(state)
      setMessage('先跳過也可以，系統會先根據熱量、餐別和可得性運作。')
    } finally {
      setLoading(false)
    }
  }

  async function handleIntake(event: FormEvent) {
    event.preventDefault()
    if (auth.status !== 'ready') return
    setLoading(true)
    try {
      const data = await api<{ draft: Draft; coach_message: string }>(
        '/api/intake',
        auth.headers,
        {
          method: 'POST',
          body: JSON.stringify({
            text,
            meal_type: mealType,
            mode,
            source_mode: 'text',
          }),
        },
      )
      setDraft(data.draft)
      setMessage(data.coach_message)
      setClarifyText('')
    } finally {
      setLoading(false)
    }
  }

  async function handleClarify(event: FormEvent) {
    event.preventDefault()
    if (auth.status !== 'ready' || !draft) return
    setLoading(true)
    try {
      const data = await api<{ draft: Draft; coach_message: string }>(
        `/api/intake/${draft.id}/clarify`,
        auth.headers,
        {
          method: 'POST',
          body: JSON.stringify({ answer: clarifyText }),
        },
      )
      setDraft(data.draft)
      setMessage(data.coach_message)
      setClarifyText('')
    } finally {
      setLoading(false)
    }
  }

  async function handleConfirm(forceConfirm = false) {
    if (auth.status !== 'ready' || !draft) return
    setLoading(true)
    try {
      const data = await api<{ summary: Summary; coach_message: string }>(
        `/api/intake/${draft.id}/confirm`,
        auth.headers,
        {
          method: 'POST',
          body: JSON.stringify({ force_confirm: forceConfirm }),
        },
      )
      setSummary(data.summary)
      setDraft(null)
      setText('')
      setMessage(data.coach_message)
      await refreshRecommendations()
    } finally {
      setLoading(false)
    }
  }

  async function handleWeight(event: FormEvent) {
    event.preventDefault()
    if (auth.status !== 'ready') return
    setLoading(true)
    try {
      const data = await api<{ summary: Summary; coach_message: string }>(
        '/api/weights',
        auth.headers,
        {
          method: 'POST',
          body: JSON.stringify({ weight: Number(weight) }),
        },
      )
      setSummary(data.summary)
      setWeight('')
      setMessage(data.coach_message)
    } finally {
      setLoading(false)
    }
  }

  async function handlePlan() {
    if (auth.status !== 'ready') return
    setLoading(true)
    try {
      const data = await api<{ plan: DayPlan; coach_message: string }>(
        '/api/plans/day',
        auth.headers,
        {
          method: 'POST',
          body: JSON.stringify({}),
        },
      )
      setDayPlan(data.plan)
      setMessage(data.coach_message)
    } finally {
      setLoading(false)
    }
  }

  async function handleCompensation() {
    if (auth.status !== 'ready') return
    setLoading(true)
    try {
      const data = await api<{ compensation: Compensation; coach_message: string }>(
        '/api/plans/compensation',
        auth.headers,
        {
          method: 'POST',
          body: JSON.stringify({ expected_extra_kcal: Number(extraKcal) }),
        },
      )
      setCompensation(data.compensation)
      setMessage(data.coach_message)
    } finally {
      setLoading(false)
    }
  }

  function toggleHardDislike(value: string) {
    setOnboardingForm((current) => {
      const hasValue = current.hard_dislikes.includes(value)
      if (value === 'none') {
        return { ...current, hard_dislikes: hasValue ? [] : ['none'] }
      }

      const next = hasValue
        ? current.hard_dislikes.filter((item) => item !== value)
        : [...current.hard_dislikes.filter((item) => item !== 'none'), value].slice(0, 3)
      return { ...current, hard_dislikes: next }
    })
  }

  if (auth.status === 'booting') {
    return (
      <div className="app-shell">
        <header className="hero">
          <div>
            <p className="eyebrow">AI Fat Loss OS</p>
            <h1>正在啟動 LIFF</h1>
            <p className="subtle">{auth.message}</p>
          </div>
        </header>
      </div>
    )
  }

  if (auth.status === 'error') {
    return (
      <div className="app-shell">
        <header className="hero">
          <div>
            <p className="eyebrow">AI Fat Loss OS</p>
            <h1>LIFF 驗證失敗</h1>
            <p className="subtle">{auth.message}</p>
          </div>
        </header>
      </div>
    )
  }

  return (
    <div className="app-shell">
      {onboarding?.should_show && (
        <div className="modal-backdrop">
          <form className="modal-card stack" onSubmit={handleOnboardingSubmit}>
            <div>
              <p className="eyebrow">Cold Start</p>
              <h2>先用 5 題幫系統對準你的吃法</h2>
              <p className="subtle">這不是長問卷。填完後，推薦、規劃和追問會更像你的真實習慣。</p>
            </div>

            <label className="stack">
              <span>1. 你平常有吃早餐嗎？</span>
              <select
                value={onboardingForm.breakfast_habit}
                onChange={(event) =>
                  setOnboardingForm((current) => ({
                    ...current,
                    breakfast_habit: event.target.value as Preferences['breakfast_habit'],
                  }))
                }
              >
                <option value="regular">幾乎都吃</option>
                <option value="occasional">偶爾吃</option>
                <option value="rare">幾乎不吃</option>
                <option value="variable">看情況</option>
              </select>
            </label>

            <label className="stack">
              <span>2. 你通常需要主食嗎？</span>
              <select
                value={onboardingForm.carb_need}
                onChange={(event) =>
                  setOnboardingForm((current) => ({
                    ...current,
                    carb_need: event.target.value as Preferences['carb_need'],
                  }))
                }
              >
                <option value="high">幾乎每餐都要</option>
                <option value="flexible">可以有但不一定要</option>
                <option value="low">通常不需要</option>
                <option value="variable">看情況</option>
              </select>
            </label>

            <label className="stack">
              <span>3. 晚餐你通常想怎麼吃？</span>
              <select
                value={onboardingForm.dinner_style}
                onChange={(event) =>
                  setOnboardingForm((current) => ({
                    ...current,
                    dinner_style: event.target.value as Preferences['dinner_style'],
                  }))
                }
              >
                <option value="light">輕一點</option>
                <option value="normal">正常吃</option>
                <option value="indulgent">想吃爽一點</option>
                <option value="high_protein">高蛋白優先</option>
                <option value="variable">看情況</option>
              </select>
            </label>

            <div className="stack">
              <span>4. 有沒有你明確不想吃的類型？</span>
              <div className="chips">
                {HARD_DISLIKE_OPTIONS.map((value) => (
                  <button
                    key={value}
                    className={`chip-button ${onboardingForm.hard_dislikes.includes(value) ? 'selected' : ''}`}
                    onClick={(event) => {
                      event.preventDefault()
                      toggleHardDislike(value)
                    }}
                    type="button"
                  >
                    {value === 'none' ? '沒有特別排斥' : value}
                  </button>
                ))}
              </div>
            </div>

            <label className="stack">
              <span>5. 大餐或爆卡後，你比較想怎麼安排？</span>
              <select
                value={onboardingForm.compensation_style}
                onChange={(event) =>
                  setOnboardingForm((current) => ({
                    ...current,
                    compensation_style: event.target.value as Preferences['compensation_style'],
                  }))
                }
              >
                <option value="normal_return">回到正常就好</option>
                <option value="gentle_1d">小幅回收 1 天</option>
                <option value="distributed_2_3d">分 2-3 天攤平</option>
                <option value="let_system_decide">讓系統幫我決定</option>
              </select>
            </label>

            <div className="row">
              <button disabled={loading} type="submit">完成</button>
              <button className="ghost" disabled={loading} onClick={() => void handleOnboardingSkip()} type="button">
                稍後再說
              </button>
            </div>
          </form>
        </div>
      )}

      <header className="hero">
        <div>
          <p className="eyebrow">AI Fat Loss OS v1</p>
          <h1>LINE + LIFF 減脂操作系統</h1>
          <p className="subtle">Signed in as {auth.me.display_name}</p>
        </div>
        <div className="status-card">
          <span>今天還剩</span>
          <strong>{summary?.remaining_kcal ?? '--'} kcal</strong>
          <small>{message}</small>
        </div>
      </header>

      <nav className="tabs">
        <button className={activeTab === 'today' ? 'active' : ''} onClick={() => setActiveTab('today')}>
          {TAB_LABELS.today}
        </button>
        <button className={activeTab === 'progress' ? 'active' : ''} onClick={() => setActiveTab('progress')}>
          {TAB_LABELS.progress}
        </button>
        <button className={activeTab === 'eat' ? 'active' : ''} onClick={() => setActiveTab('eat')}>
          {TAB_LABELS.eat}
        </button>
      </nav>

      {activeTab === 'today' && (
        <section className="page-grid">
          <article className="panel">
            <h2>新增食物紀錄</h2>
            <form onSubmit={handleIntake} className="stack">
              <textarea
                value={text}
                onChange={(event) => setText(event.target.value)}
                placeholder="例如：雞胸便當加半碗飯，青菜有吃完，湯沒喝。"
                rows={5}
              />
              <div className="row">
                <select value={mealType} onChange={(event) => setMealType(event.target.value)}>
                  <option value="breakfast">早餐</option>
                  <option value="lunch">午餐</option>
                  <option value="dinner">晚餐</option>
                  <option value="snack">點心</option>
                </select>
                <select value={mode} onChange={(event) => setMode(event.target.value)}>
                  <option value="quick">快速</option>
                  <option value="standard">標準</option>
                  <option value="fine">精細</option>
                </select>
              </div>
              <button disabled={loading || !text.trim()} type="submit">
                送出估算
              </button>
            </form>
          </article>

          <article className="panel">
            <h2>目前草稿</h2>
            {draft ? (
              <div className="stack">
                <div className="metric">
                  <strong>{draft.estimate_kcal} kcal</strong>
                  <span>
                    {draft.kcal_low} - {draft.kcal_high} kcal
                  </span>
                </div>
                <p>{draft.uncertainty_note}</p>
                <div className="chips">
                  {draft.parsed_items.map((item) => (
                    <span key={item.name} className="chip">
                      {item.name}
                      {item.kcal ? ` ${item.kcal} kcal` : ''}
                    </span>
                  ))}
                </div>
                {draft.followup_question && (
                  <form onSubmit={handleClarify} className="stack">
                    <label>{draft.followup_question}</label>
                    <input
                      value={clarifyText}
                      onChange={(event) => setClarifyText(event.target.value)}
                      placeholder="直接用生活語言補充就好，例如：飯吃一半、炸雞只吃兩塊。"
                    />
                    <button disabled={loading || !clarifyText.trim()} type="submit">
                      送出補充
                    </button>
                  </form>
                )}
                <div className="row">
                  <button disabled={loading} onClick={() => void handleConfirm(false)} type="button">
                    確認紀錄
                  </button>
                  <button className="ghost" disabled={loading} onClick={() => void handleConfirm(true)} type="button">
                    直接存檔
                  </button>
                </div>
              </div>
            ) : (
              <p className="subtle">送出一筆食物後，這裡會顯示估算結果與必要追問。</p>
            )}
          </article>

          <article className="panel wide">
            <h2>今日總覽</h2>
            {summary ? (
              <>
                <div className="summary-grid">
                  <div>
                    <span>目標</span>
                    <strong>{summary.target_kcal}</strong>
                  </div>
                  <div>
                    <span>已吃</span>
                    <strong>{summary.consumed_kcal}</strong>
                  </div>
                  <div>
                    <span>剩餘</span>
                    <strong>{summary.remaining_kcal}</strong>
                  </div>
                </div>
                <ul className="list">
                  {summary.logs.map((log) => (
                    <li key={log.id}>
                      <div>
                        <strong>{MEAL_TYPE_LABELS[log.meal_type] ?? log.meal_type}</strong>
                        <p>{log.description_raw}</p>
                      </div>
                      <span>{log.kcal_estimate} kcal</span>
                    </li>
                  ))}
                </ul>
              </>
            ) : (
              <p className="subtle">Loading summary...</p>
            )}
          </article>
        </section>
      )}

      {activeTab === 'progress' && (
        <section className="page-grid">
          <article className="panel">
            <h2>記錄體重</h2>
            <form onSubmit={handleWeight} className="stack">
              <input type="number" step="0.1" value={weight} onChange={(event) => setWeight(event.target.value)} placeholder="72.4" />
              <button disabled={loading || !weight} type="submit">
                送出體重
              </button>
            </form>
          </article>

          <article className="panel">
            <h2>趨勢</h2>
            <div className="stack">
              <div className="metric">
                <strong>{summary?.seven_day_average_weight ?? '--'}</strong>
                <span>7 日平均體重</span>
              </div>
              <div className="metric">
                <strong>{summary?.fourteen_day_direction ?? '--'}</strong>
                <span>14 日方向</span>
              </div>
              <p>{summary?.target_adjustment_hint}</p>
            </div>
          </article>
        </section>
      )}

      {activeTab === 'eat' && (
        <section className="page-grid">
          <article className="panel">
            <h2>現在可以吃什麼</h2>
            <button onClick={() => void refreshRecommendations()} disabled={loading}>
              重新整理推薦
            </button>
            <div className="group-stack">
              {Object.entries(groupedRecommendations).map(([group, items]) => (
                <div key={group} className="group">
                  <h3>{group}</h3>
                  {items.map((item) => (
                    <div key={`${group}-${item.name}`} className="recommendation">
                      <strong>{item.name}</strong>
                      <span>
                        {item.kcal_low} - {item.kcal_high} kcal
                      </span>
                      <p>{item.reason}</p>
                      {item.reason_factors?.length > 0 && (
                        <ul className="factor-list">
                          {item.reason_factors.map((factor) => (
                            <li key={factor}>{factor}</li>
                          ))}
                        </ul>
                      )}
                    </div>
                  ))}
                </div>
              ))}
            </div>
          </article>

          <article className="panel">
            <h2>今日規劃</h2>
            <button onClick={() => void handlePlan()} disabled={loading}>
              產生今日規劃
            </button>
            {dayPlan && (
              <div className="stack">
                {Object.entries(dayPlan.allocations).map(([key, value]) => (
                  <div className="row muted" key={key}>
                    <span>{PLAN_KEY_LABELS[key] ?? key}</span>
                    <strong>{value} kcal</strong>
                  </div>
                ))}
                {dayPlan.reason_factors.length > 0 && (
                  <ul className="factor-list">
                    {dayPlan.reason_factors.map((factor) => (
                      <li key={factor}>{factor}</li>
                    ))}
                  </ul>
                )}
              </div>
            )}
          </article>

          <article className="panel">
            <h2>預支與補償</h2>
            <div className="stack">
              <input type="number" value={extraKcal} onChange={(event) => setExtraKcal(event.target.value)} />
              <button onClick={() => void handleCompensation()} disabled={loading}>
                產生方案
              </button>
              {compensation?.reason_factors?.length ? (
                <ul className="factor-list">
                  {compensation.reason_factors.map((factor) => (
                    <li key={factor}>{factor}</li>
                  ))}
                </ul>
              ) : null}
              {compensation?.options.map((option) => (
                <div key={option.label} className="recommendation">
                  <strong>{option.label}</strong>
                  <span>
                    {option.daily_adjustment} kcal x {option.days} 天
                  </span>
                  <p>{option.note}</p>
                </div>
              ))}
            </div>
          </article>
        </section>
      )}
    </div>
  )
}

export default App

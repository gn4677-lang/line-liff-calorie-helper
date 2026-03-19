import { useEffect, useMemo, useState } from 'react'
import type { FormEvent } from 'react'
import './App.css'

type Draft = {
  id: string
  date: string
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
  is_favorite?: boolean
  is_golden?: boolean
}

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? ''

async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    headers: {
      'Content-Type': 'application/json',
      'X-Line-User-Id': 'demo-user',
      'X-Display-Name': 'Demo User',
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
  const [activeTab, setActiveTab] = useState<'today' | 'progress' | 'eat'>('today')
  const [text, setText] = useState('')
  const [mealType, setMealType] = useState('lunch')
  const [mode, setMode] = useState('standard')
  const [clarifyText, setClarifyText] = useState('')
  const [weight, setWeight] = useState('')
  const [extraKcal, setExtraKcal] = useState('600')
  const [draft, setDraft] = useState<Draft | null>(null)
  const [summary, setSummary] = useState<Summary | null>(null)
  const [recommendations, setRecommendations] = useState<Recommendation[]>([])
  const [dayPlan, setDayPlan] = useState<Record<string, number> | null>(null)
  const [compensation, setCompensation] = useState<Array<{ label: string; daily_adjustment: number; days: number; note: string }>>([])
  const [message, setMessage] = useState('Ready.')
  const [loading, setLoading] = useState(false)

  const groupedRecommendations = useMemo(() => {
    return recommendations.reduce<Record<string, Recommendation[]>>((acc, item) => {
      acc[item.group] ??= []
      acc[item.group].push(item)
      return acc
    }, {})
  }, [recommendations])

  async function refreshSummary() {
    const data = await api<{ summary: Summary; coach_message: string }>('/api/day-summary')
    setSummary(data.summary)
    setMessage(data.coach_message)
  }

  async function refreshRecommendations() {
    const data = await api<{ recommendations: { items: Recommendation[] }; coach_message: string }>('/api/recommendations')
    setRecommendations(data.recommendations.items)
    setMessage(data.coach_message)
  }

  useEffect(() => {
    void refreshSummary()
    void refreshRecommendations()
  }, [])

  async function handleIntake(event: FormEvent) {
    event.preventDefault()
    setLoading(true)
    try {
      const data = await api<{ draft: Draft; coach_message: string }>('/api/intake', {
        method: 'POST',
        body: JSON.stringify({
          text,
          meal_type: mealType,
          mode,
          source_mode: 'text',
        }),
      })
      setDraft(data.draft)
      setMessage(data.coach_message)
      setClarifyText('')
    } finally {
      setLoading(false)
    }
  }

  async function handleClarify(event: FormEvent) {
    event.preventDefault()
    if (!draft) return
    setLoading(true)
    try {
      const data = await api<{ draft: Draft; coach_message: string }>(`/api/intake/${draft.id}/clarify`, {
        method: 'POST',
        body: JSON.stringify({ answer: clarifyText }),
      })
      setDraft(data.draft)
      setMessage(data.coach_message)
      setClarifyText('')
    } finally {
      setLoading(false)
    }
  }

  async function handleConfirm(forceConfirm = false) {
    if (!draft) return
    setLoading(true)
    try {
      const data = await api<{ summary: Summary; coach_message: string }>(`/api/intake/${draft.id}/confirm`, {
        method: 'POST',
        body: JSON.stringify({ force_confirm: forceConfirm }),
      })
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
    setLoading(true)
    try {
      const data = await api<{ summary: Summary; coach_message: string }>('/api/weights', {
        method: 'POST',
        body: JSON.stringify({ weight: Number(weight) }),
      })
      setSummary(data.summary)
      setWeight('')
      setMessage(data.coach_message)
    } finally {
      setLoading(false)
    }
  }

  async function handlePlan() {
    setLoading(true)
    try {
      const data = await api<{ plan: { allocations: Record<string, number> }; coach_message: string }>('/api/plans/day', {
        method: 'POST',
        body: JSON.stringify({}),
      })
      setDayPlan(data.plan.allocations)
      setMessage(data.coach_message)
    } finally {
      setLoading(false)
    }
  }

  async function handleCompensation() {
    setLoading(true)
    try {
      const data = await api<{ compensation: { options: Array<{ label: string; daily_adjustment: number; days: number; note: string }> }; coach_message: string }>('/api/plans/compensation', {
        method: 'POST',
        body: JSON.stringify({ expected_extra_kcal: Number(extraKcal) }),
      })
      setCompensation(data.compensation.options)
      setMessage(data.coach_message)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="app-shell">
      <header className="hero">
        <div>
          <p className="eyebrow">AI 減脂操作系統 v1</p>
          <h1>LINE + LIFF Calorie Helper</h1>
          <p className="subtle">先把 intake / clarify / confirm / summary / recommend 跑順，再慢慢把記憶與規劃變深。</p>
        </div>
        <div className="status-card">
          <span>Today</span>
          <strong>{summary?.remaining_kcal ?? '--'} kcal left</strong>
          <small>{message}</small>
        </div>
      </header>

      <nav className="tabs">
        <button className={activeTab === 'today' ? 'active' : ''} onClick={() => setActiveTab('today')}>Today</button>
        <button className={activeTab === 'progress' ? 'active' : ''} onClick={() => setActiveTab('progress')}>Progress</button>
        <button className={activeTab === 'eat' ? 'active' : ''} onClick={() => setActiveTab('eat')}>Eat</button>
      </nav>

      {activeTab === 'today' && (
        <section className="page-grid">
          <article className="panel">
            <h2>Log a meal</h2>
            <form onSubmit={handleIntake} className="stack">
              <textarea value={text} onChange={(event) => setText(event.target.value)} placeholder="例如：雞胸便當 半飯 無糖豆漿" rows={5} />
              <div className="row">
                <select value={mealType} onChange={(event) => setMealType(event.target.value)}>
                  <option value="breakfast">Breakfast</option>
                  <option value="lunch">Lunch</option>
                  <option value="dinner">Dinner</option>
                  <option value="snack">Snack</option>
                </select>
                <select value={mode} onChange={(event) => setMode(event.target.value)}>
                  <option value="quick">Quick</option>
                  <option value="standard">Standard</option>
                  <option value="fine">Fine</option>
                </select>
              </div>
              <button disabled={loading || !text.trim()} type="submit">Estimate</button>
            </form>
          </article>

          <article className="panel">
            <h2>Draft</h2>
            {draft ? (
              <div className="stack">
                <div className="metric">
                  <strong>{draft.estimate_kcal} kcal</strong>
                  <span>{draft.kcal_low} - {draft.kcal_high} kcal</span>
                </div>
                <p>{draft.uncertainty_note}</p>
                <div className="chips">
                  {draft.parsed_items.map((item) => (
                    <span key={item.name} className="chip">{item.name}{item.kcal ? ` ${item.kcal}kcal` : ''}</span>
                  ))}
                </div>
                {draft.followup_question && (
                  <form onSubmit={handleClarify} className="stack">
                    <label>{draft.followup_question}</label>
                    <input value={clarifyText} onChange={(event) => setClarifyText(event.target.value)} placeholder="補充：飯半碗、主菜雞腿、有滷蛋" />
                    <button disabled={loading || !clarifyText.trim()} type="submit">Submit clarification</button>
                  </form>
                )}
                <div className="row">
                  <button disabled={loading} onClick={() => void handleConfirm(false)}>Confirm</button>
                  <button className="ghost" disabled={loading} onClick={() => void handleConfirm(true)}>Force confirm</button>
                </div>
              </div>
            ) : (
              <p className="subtle">目前沒有 active draft。</p>
            )}
          </article>

          <article className="panel wide">
            <h2>Today summary</h2>
            {summary ? (
              <>
                <div className="summary-grid">
                  <div><span>Target</span><strong>{summary.target_kcal}</strong></div>
                  <div><span>Consumed</span><strong>{summary.consumed_kcal}</strong></div>
                  <div><span>Remaining</span><strong>{summary.remaining_kcal}</strong></div>
                </div>
                <ul className="list">
                  {summary.logs.map((log) => (
                    <li key={log.id}>
                      <div>
                        <strong>{log.meal_type}</strong>
                        <p>{log.description_raw}</p>
                      </div>
                      <span>{log.kcal_estimate} kcal</span>
                    </li>
                  ))}
                </ul>
              </>
            ) : (
              <p className="subtle">尚未載入 summary。</p>
            )}
          </article>
        </section>
      )}

      {activeTab === 'progress' && (
        <section className="page-grid">
          <article className="panel">
            <h2>Weight log</h2>
            <form onSubmit={handleWeight} className="stack">
              <input type="number" step="0.1" value={weight} onChange={(event) => setWeight(event.target.value)} placeholder="72.4" />
              <button disabled={loading || !weight} type="submit">Log weight</button>
            </form>
          </article>

          <article className="panel">
            <h2>Trend</h2>
            <div className="stack">
              <div className="metric"><strong>{summary?.seven_day_average_weight ?? '--'}</strong><span>7-day avg</span></div>
              <div className="metric"><strong>{summary?.fourteen_day_direction ?? '--'}</strong><span>14-day direction</span></div>
              <p>{summary?.target_adjustment_hint}</p>
            </div>
          </article>
        </section>
      )}

      {activeTab === 'eat' && (
        <section className="page-grid">
          <article className="panel">
            <h2>Recommendations</h2>
            <button onClick={() => void refreshRecommendations()} disabled={loading}>Refresh</button>
            <div className="group-stack">
              {Object.entries(groupedRecommendations).map(([group, items]) => (
                <div key={group} className="group">
                  <h3>{group}</h3>
                  {items.map((item) => (
                    <div key={`${group}-${item.name}`} className="recommendation">
                      <strong>{item.name}</strong>
                      <span>{item.kcal_low} - {item.kcal_high} kcal</span>
                      <p>{item.reason}</p>
                    </div>
                  ))}
                </div>
              ))}
            </div>
          </article>

          <article className="panel">
            <h2>Plan day</h2>
            <button onClick={() => void handlePlan()} disabled={loading}>Generate day plan</button>
            {dayPlan && (
              <div className="stack">
                {Object.entries(dayPlan).map(([key, value]) => (
                  <div className="row muted" key={key}>
                    <span>{key}</span>
                    <strong>{value} kcal</strong>
                  </div>
                ))}
              </div>
            )}
          </article>

          <article className="panel">
            <h2>Compensation</h2>
            <div className="stack">
              <input type="number" value={extraKcal} onChange={(event) => setExtraKcal(event.target.value)} />
              <button onClick={() => void handleCompensation()} disabled={loading}>Generate compensation options</button>
              {compensation.map((option) => (
                <div key={option.label} className="recommendation">
                  <strong>{option.label}</strong>
                  <span>{option.daily_adjustment} kcal x {option.days} day(s)</span>
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

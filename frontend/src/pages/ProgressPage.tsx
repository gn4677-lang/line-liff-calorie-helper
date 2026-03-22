import { useEffect, useMemo, useState } from 'react'
import { useApp } from '../AppContext'
import { api } from '../api'
import { FullScreenSheet } from '../components/Sheets'
import { MEAL_TYPE_LABELS } from '../types'
import type {
  ActivityAdjustment,
  BodyGoal,
  Compensation,
  MealEvent,
  PlanEvent,
  ProgressSeries,
  ProgressSeriesPoint,
  Summary,
} from '../types'

function directionLabel(direction: string): string {
  switch (direction) {
    case 'down':
      return '最近有往目標前進'
    case 'up':
      return '最近有往上走'
    case 'flat':
      return '最近大致持平'
    default:
      return '資料還不夠穩定'
  }
}

function weeklyStatusLabel(status: string): string {
  switch (status) {
    case 'meaningfully_over':
      return '本週明顯超標'
    case 'slightly_over':
      return '本週略高於目標'
    case 'meaningfully_under':
      return '本週低於目標很多'
    default:
      return '本週大致在軌道上'
  }
}

function BodyHero({
  summary,
  bodyGoal,
  onOpenWeight,
}: {
  summary: Summary
  bodyGoal: BodyGoal | null
  onOpenWeight: () => void
}) {
  const delta = summary.delta_to_goal_kg ?? bodyGoal?.delta_to_goal_kg ?? null
  return (
    <section className="body-hero">
      <div className="body-hero__header">
        <span>目前體重</span>
        <strong>{summary.latest_weight != null ? `${summary.latest_weight} kg` : '尚未記錄'}</strong>
      </div>
      <div className="body-hero__meta">
        <span>目標 {bodyGoal?.target_weight_kg != null ? `${bodyGoal.target_weight_kg} kg` : '尚未設定'}</span>
        {delta != null ? <span>差距 {Math.abs(delta).toFixed(1)} kg</span> : null}
      </div>
      <button className="btn btn-primary body-hero__action" type="button" onClick={onOpenWeight}>
        記錄體重
      </button>
    </section>
  )
}

function MetricRow({ label, value, hint }: { label: string; value: string; hint?: string }) {
  return (
    <div className="metric-pill">
      <span>{label}</span>
      <strong>{value}</strong>
      {hint ? <small>{hint}</small> : null}
    </div>
  )
}

function WeeklySnapshot({
  summary,
  compensation,
  onBuildRecovery,
}: {
  summary: Summary
  compensation: Compensation | null
  onBuildRecovery: () => Promise<void>
}) {
  return (
    <section className="summary-card">
      <div className="summary-card__header summary-card__header--static">
        <div>
          <strong>本週回顧</strong>
          <span>{weeklyStatusLabel(summary.weekly_drift_status)}</span>
        </div>
      </div>
      <div className="strategy-grid">
        <div className="strategy-grid__item">
          <span>本週差距</span>
          <strong>{summary.weekly_drift_kcal > 0 ? '+' : ''}{summary.weekly_drift_kcal} kcal</strong>
        </div>
        <div className="strategy-grid__item">
          <span>本週已吃</span>
          <strong>{summary.weekly_consumed_kcal} kcal</strong>
        </div>
      </div>
      <div className="strategy-note">{summary.target_adjustment_hint || directionLabel(summary.fourteen_day_direction)}</div>
      {summary.recovery_overlay?.active ? (
        <div className="support-banner">
          回收模式已啟動，今天目標 {summary.recovery_overlay.adjusted_target_kcal ?? summary.effective_target_kcal} kcal。
        </div>
      ) : null}
      {summary.should_offer_weekly_recovery ? (
        <div className="inline-actions inline-actions--wide">
          <button className="btn btn-outline" type="button" onClick={() => void onBuildRecovery()}>
            生成溫和回收方案
          </button>
        </div>
      ) : null}
      {compensation?.options?.length ? (
        <div className="sheet-list">
          {compensation.options.map((option) => (
            <div key={option.label} className="explore-row">
              <div>
                <strong>{option.label}</strong>
                <span>{option.note}</span>
              </div>
              <span>-{option.daily_adjustment} kcal</span>
            </div>
          ))}
        </div>
      ) : null}
    </section>
  )
}

function ActivitySheet({
  isOpen,
  onClose,
  activities,
  selectedDate,
  onSaved,
}: {
  isOpen: boolean
  onClose: () => void
  activities: ActivityAdjustment[]
  selectedDate: string
  onSaved: (summary: Summary) => Promise<void>
}) {
  const { auth, showToast } = useApp()
  const [form, setForm] = useState({ label: '', estimated_burn_kcal: '', duration_minutes: '' })
  const [saving, setSaving] = useState(false)

  async function createAdjustment() {
    if (auth.status !== 'ready' || !form.label || !form.estimated_burn_kcal) return
    setSaving(true)
    try {
      const data = await api<{ summary: Summary }>(
        '/api/activity-adjustments',
        auth.headers,
        {
          method: 'POST',
          body: JSON.stringify({
            date: selectedDate,
            label: form.label,
            estimated_burn_kcal: Number(form.estimated_burn_kcal),
            duration_minutes: form.duration_minutes ? Number(form.duration_minutes) : undefined,
          }),
        },
      )
      setForm({ label: '', estimated_burn_kcal: '', duration_minutes: '' })
      await onSaved(data.summary)
      showToast(`已記錄活動 ${form.label}`, 'success')
      onClose()
    } catch {
      showToast('儲存失敗，請確認網路連線後重試', 'error')
    } finally {
      setSaving(false)
    }
  }

  return (
    <FullScreenSheet isOpen={isOpen} onClose={onClose} title="活動與消耗">
      <div className="sheet-stack">
        <section className="sheet-card">
          <div className="sheet-card__header">
            <h4>今天的活動</h4>
            <span>{activities.length} 筆</span>
          </div>
          {activities.length ? (
            <div className="sheet-list">
              {activities.map((activity) => (
                <div key={activity.id} className="explore-row">
                  <div>
                    <strong>{activity.label}</strong>
                    <span>{activity.duration_minutes ? `${activity.duration_minutes} 分鐘` : activity.source}</span>
                  </div>
                  <strong>+{activity.estimated_burn_kcal}</strong>
                </div>
              ))}
            </div>
          ) : (
            <div className="empty-row empty-row--sheet">今天還沒有活動記錄。</div>
          )}
        </section>

        <section className="sheet-card">
          <div className="sheet-card__header">
            <h4>補一筆活動</h4>
            <span>用自然語言即可</span>
          </div>
          <div className="inline-grid">
            <input className="input-field" placeholder="例如：跳舞 90 分鐘" value={form.label} onChange={(event) => setForm((current) => ({ ...current, label: event.target.value }))} />
            <input className="input-field" type="number" placeholder="估計消耗 kcal" value={form.estimated_burn_kcal} onChange={(event) => setForm((current) => ({ ...current, estimated_burn_kcal: event.target.value }))} />
            <input className="input-field" type="number" placeholder="分鐘（選填）" value={form.duration_minutes} onChange={(event) => setForm((current) => ({ ...current, duration_minutes: event.target.value }))} />
          </div>
          <button className="btn btn-primary" type="button" disabled={saving || !form.label || !form.estimated_burn_kcal} onClick={() => void createAdjustment()}>
            {saving ? '儲存中...' : '加入活動'}
          </button>
        </section>
      </div>
    </FullScreenSheet>
  )
}

function MealEventSheet({
  isOpen,
  onClose,
  mealEvents,
  planEvents,
  onCreate,
}: {
  isOpen: boolean
  onClose: () => void
  mealEvents: MealEvent[]
  planEvents: PlanEvent[]
  onCreate: (draft: { event_date: string; meal_type: 'breakfast' | 'lunch' | 'dinner' | 'snack'; title: string; expected_kcal?: number; notes?: string }) => Promise<void>
}) {
  const { showToast } = useApp()
  const [form, setForm] = useState({
    event_date: new Date().toISOString().slice(0, 10),
    meal_type: 'dinner' as const,
    title: '',
    expected_kcal: '',
    notes: '',
  })
  const [saving, setSaving] = useState(false)

  async function save() {
    if (!form.title || !form.event_date) return
    setSaving(true)
    try {
      await onCreate({
        event_date: form.event_date,
        meal_type: form.meal_type,
        title: form.title,
        expected_kcal: form.expected_kcal ? Number(form.expected_kcal) : undefined,
        notes: form.notes || undefined,
      })
      setForm({
        event_date: new Date().toISOString().slice(0, 10),
        meal_type: 'dinner',
        title: '',
        expected_kcal: '',
        notes: '',
      })
      showToast('已預記錄大餐', 'success')
      onClose()
    } catch {
      showToast('儲存失敗，請確認網路連線後重試', 'error')
    } finally {
      setSaving(false)
    }
  }

  return (
    <FullScreenSheet isOpen={isOpen} onClose={onClose} title="預記錄大餐">
      <div className="sheet-stack">
        <section className="sheet-card">
          <div className="sheet-card__header">
            <h4>未來餐次</h4>
            <span>{mealEvents.length} 筆</span>
          </div>
          {mealEvents.length ? (
            <div className="sheet-list">
              {mealEvents.map((event) => (
                <div key={event.id} className="explore-row">
                  <div>
                    <strong>{event.title}</strong>
                    <span>{event.event_date} · {MEAL_TYPE_LABELS[event.meal_type]}</span>
                  </div>
                  <span>{event.expected_kcal} kcal</span>
                </div>
              ))}
            </div>
          ) : (
            <div className="empty-row empty-row--sheet">還沒有預記錄的大餐。</div>
          )}
        </section>

        <section className="sheet-card">
          <div className="sheet-card__header">
            <h4>新增一筆</h4>
            <span>未來的大餐會自動進策略</span>
          </div>
          <div className="inline-grid">
            <input className="input-field" type="date" value={form.event_date} onChange={(event) => setForm((current) => ({ ...current, event_date: event.target.value }))} />
            <select className="input-field" value={form.meal_type} onChange={(event) => setForm((current) => ({ ...current, meal_type: event.target.value as typeof form.meal_type }))}>
              <option value="breakfast">早餐</option>
              <option value="lunch">午餐</option>
              <option value="dinner">晚餐</option>
              <option value="snack">點心</option>
            </select>
            <input className="input-field" placeholder="例如：週五晚餐聚餐" value={form.title} onChange={(event) => setForm((current) => ({ ...current, title: event.target.value }))} />
            <input className="input-field" type="number" placeholder="預估 kcal（可空白）" value={form.expected_kcal} onChange={(event) => setForm((current) => ({ ...current, expected_kcal: event.target.value }))} />
            <input className="input-field" placeholder="備註（可選）" value={form.notes} onChange={(event) => setForm((current) => ({ ...current, notes: event.target.value }))} />
          </div>
          <button className="btn btn-primary" type="button" disabled={saving || !form.title || !form.event_date} onClick={() => void save()}>
            {saving ? '儲存中...' : '儲存事件'}
          </button>
        </section>

        {planEvents.length ? (
          <section className="sheet-card">
            <div className="sheet-card__header">
              <h4>策略事件</h4>
              <span>{planEvents.length} 筆</span>
            </div>
            <div className="sheet-list">
              {planEvents.slice(0, 6).map((event) => (
                <div key={event.id} className="explore-row">
                  <div>
                    <strong>{event.title || event.event_type}</strong>
                    <span>{event.date}</span>
                  </div>
                  <span>+{event.expected_extra_kcal} kcal</span>
                </div>
              ))}
            </div>
          </section>
        ) : null}
      </div>
    </FullScreenSheet>
  )
}

function ProgressInsights({
  series,
  range,
  onChangeRange,
}: {
  series: ProgressSeries | null
  range: string
  onChangeRange: (range: string) => void
}) {
  return (
    <div className="sheet-stack">
      <div className="chip-row">
        {['7d', '30d', '90d', '1y'].map((item) => (
          <button
            key={item}
            className={`chip-button ${range === item ? 'chip-button--active' : ''}`}
            type="button"
            onClick={() => onChangeRange(item)}
          >
            {item.toUpperCase()}
          </button>
        ))}
      </div>
      <section className="sheet-card">
        <div className="sheet-card__header">
          <h4>體重趨勢</h4>
          <span>{series?.range ?? range}</span>
        </div>
        <SimpleLine points={series?.weight_points ?? []} unit="kg" />
      </section>
      <section className="sheet-card">
        <div className="sheet-card__header">
          <h4>攝取 vs 目標</h4>
          <span>最近 8 個時間點</span>
        </div>
        <SimpleBars points={series?.calorie_points ?? []} />
      </section>
    </div>
  )
}

function SimpleLine({ points, unit }: { points: ProgressSeriesPoint[]; unit: string }) {
  if (!points.length) return <div className="empty-row empty-row--sheet">還沒有足夠資料畫出趨勢。</div>
  const values = points.map((point) => Number(point.value))
  const min = Math.min(...values)
  const max = Math.max(...values)
  const spread = Math.max(max - min, 1)
  const width = 320
  const height = 140
  const path = points.map((point, index) => {
    const x = (index / Math.max(points.length - 1, 1)) * (width - 24) + 12
    const y = height - 12 - ((Number(point.value) - min) / spread) * (height - 24)
    return `${index === 0 ? 'M' : 'L'}${x},${y}`
  }).join(' ')
  return (
    <>
      <svg viewBox={`0 0 ${width} ${height}`} width="100%" height={height} className="chart-svg">
        <path d={path} fill="none" stroke="var(--accent-primary)" strokeWidth="3" strokeLinecap="round" />
      </svg>
      <div className="detail-line detail-line--muted">最新值 {points[points.length - 1].value} {unit}</div>
    </>
  )
}

function SimpleBars({ points }: { points: ProgressSeriesPoint[] }) {
  if (!points.length) return <div className="empty-row empty-row--sheet">還沒有足夠資料畫出熱量趨勢。</div>
  const max = Math.max(...points.map((point) => Math.max(Number(point.value), Number(point.target ?? 0), 1)))
  return (
    <div className="mini-bars mini-bars--wide">
      {points.slice(-8).map((point) => (
        <div key={point.date} className="mini-bars__item">
          <div className="mini-bars__track mini-bars__track--stacked">
            {point.target != null ? <div className="mini-bars__target" style={{ height: `${Math.max(8, (Number(point.target) / max) * 100)}%` }} /> : null}
            <div className="mini-bars__fill" style={{ height: `${Math.max(8, (Number(point.value) / max) * 100)}%` }} />
          </div>
          <span>{point.date.slice(5)}</span>
        </div>
      ))}
    </div>
  )
}

function GoalSheet({
  isOpen,
  onClose,
  bodyGoal,
  onSaved,
}: {
  isOpen: boolean
  onClose: () => void
  bodyGoal: BodyGoal | null
  onSaved: (bodyGoal: BodyGoal) => Promise<void>
}) {
  const { auth, showToast } = useApp()
  const [showAdvanced, setShowAdvanced] = useState(false)
  const formSeed = useMemo(() => ({
    target_weight_kg: bodyGoal?.target_weight_kg != null ? String(bodyGoal.target_weight_kg) : '',
    estimated_tdee_kcal: bodyGoal?.estimated_tdee_kcal != null ? String(bodyGoal.estimated_tdee_kcal) : '',
    default_daily_deficit_kcal: bodyGoal?.default_daily_deficit_kcal != null ? String(bodyGoal.default_daily_deficit_kcal) : '',
  }), [bodyGoal])
  const [form, setForm] = useState(formSeed)

  async function save() {
    if (auth.status !== 'ready') return
    try {
      const data = await api<{ payload: { body_goal: BodyGoal } }>(
        '/api/body-goal',
        auth.headers,
        {
          method: 'PATCH',
          body: JSON.stringify({
            target_weight_kg: form.target_weight_kg ? Number(form.target_weight_kg) : null,
            estimated_tdee_kcal: showAdvanced && form.estimated_tdee_kcal ? Number(form.estimated_tdee_kcal) : undefined,
            default_daily_deficit_kcal: showAdvanced && form.default_daily_deficit_kcal ? Number(form.default_daily_deficit_kcal) : undefined,
          }),
        },
      )
      await onSaved(data.payload.body_goal)
      showToast('目標已更新', 'success')
      onClose()
    } catch {
      showToast('儲存失敗，請確認網路連線後重試', 'error')
    }
  }

  return (
    <FullScreenSheet isOpen={isOpen} onClose={onClose} title="模型與目標">
      <div className="sheet-stack">
        <section className="sheet-card">
          <div className="sheet-card__header">
            <h4>主要設定</h4>
            <span>平常只需要改目標體重</span>
          </div>
          <div className="sheet-stack">
            <input className="input-field" type="number" step="0.1" placeholder="目標體重 kg" value={form.target_weight_kg} onChange={(event) => setForm((current) => ({ ...current, target_weight_kg: event.target.value }))} />
            <button className="text-link-button text-link-button--left" type="button" onClick={() => setShowAdvanced((current) => !current)}>
              {showAdvanced ? '隱藏進階設定' : '展開進階設定'}
            </button>
            {showAdvanced ? (
              <div className="sheet-stack">
                <input className="input-field" type="number" placeholder="估計 TDEE" value={form.estimated_tdee_kcal} onChange={(event) => setForm((current) => ({ ...current, estimated_tdee_kcal: event.target.value }))} />
                <input className="input-field" type="number" placeholder="每日赤字" value={form.default_daily_deficit_kcal} onChange={(event) => setForm((current) => ({ ...current, default_daily_deficit_kcal: event.target.value }))} />
              </div>
            ) : null}
          </div>
        </section>
        <button className="btn btn-primary" type="button" onClick={() => void save()}>儲存設定</button>
      </div>
    </FullScreenSheet>
  )
}

function WeightSheet({
  isOpen,
  onClose,
  latestWeight,
  onSaved,
}: {
  isOpen: boolean
  onClose: () => void
  latestWeight: number | null
  onSaved: () => Promise<void>
}) {
  const { auth, selectedDate, showToast } = useApp()
  const [weight, setWeight] = useState(latestWeight != null ? String(latestWeight) : '')
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    if (isOpen) {
      setWeight(latestWeight != null ? String(latestWeight) : '')
    }
  }, [isOpen, latestWeight])

  async function save() {
    if (auth.status !== 'ready' || !weight) return
    setSaving(true)
    try {
      await api('/api/weights', auth.headers, { method: 'POST', body: JSON.stringify({ date: selectedDate, weight: Number(weight) }) })
      await onSaved()
      showToast(`體重已記錄 ${weight} kg`, 'success')
      onClose()
    } catch {
      showToast('儲存失敗，請確認網路連線後重試', 'error')
    } finally {
      setSaving(false)
    }
  }

  return (
    <FullScreenSheet isOpen={isOpen} onClose={onClose} title="記錄體重">
      <div className="sheet-stack">
        <section className="sheet-card">
          <div className="sheet-card__header">
            <h4>今天的體重</h4>
            <span>輸入後會更新 TDEE 校正</span>
          </div>
          <input className="input-field" type="number" step="0.1" placeholder="kg" value={weight} onChange={(event) => setWeight(event.target.value)} />
        </section>
        <button className="btn btn-primary" type="button" disabled={saving || !weight} onClick={() => void save()}>
          {saving ? '儲存中...' : '更新體重'}
        </button>
      </div>
    </FullScreenSheet>
  )
}

export default function ProgressPage() {
  const {
    auth,
    bodyGoal,
    summary,
    activities,
    progressSeries,
    progressRange,
    selectedDate,
    refreshActivities,
    refreshBodyGoal,
    refreshProgressSeries,
    refreshSummary,
    compensation,
    setCompensation,
    mealEvents,
    planEvents,
    createMealEvent,
  } = useApp()
  const [goalOpen, setGoalOpen] = useState(false)
  const [insightsOpen, setInsightsOpen] = useState(false)
  const [activityOpen, setActivityOpen] = useState(false)
  const [mealEventOpen, setMealEventOpen] = useState(false)
  const [weightOpen, setWeightOpen] = useState(false)

  if (auth.status !== 'ready' || !summary) {
    return <div className="page-container"><div className="page-skeleton" /></div>
  }

  async function syncSummary(summaryData: Summary) {
    await Promise.all([
      refreshSummary(summaryData.date),
      refreshActivities(summaryData.date),
      refreshBodyGoal(),
      refreshProgressSeries(),
    ])
  }

  async function saveGoal() {
    await Promise.all([refreshBodyGoal(), refreshSummary(selectedDate), refreshProgressSeries()])
  }

  const currentSummary = summary

  async function buildRecovery() {
    if (auth.status !== 'ready') return
    const data = await api<{ compensation: Compensation }>(
      '/api/plans/compensation',
      auth.headers,
      { method: 'POST', body: JSON.stringify({ expected_extra_kcal: Math.max(currentSummary.weekly_drift_kcal, 0) }) },
    )
    setCompensation(data.compensation)
  }

  async function refreshAfterWeight() {
    await Promise.all([refreshSummary(selectedDate), refreshBodyGoal(), refreshProgressSeries()])
  }

  return (
    <div className="page-container" id="page-progress">
      <BodyHero summary={currentSummary} bodyGoal={bodyGoal} onOpenWeight={() => setWeightOpen(true)} />

      <section className="metric-pill-row">
        <MetricRow label="估計 TDEE" value={`${bodyGoal?.estimated_tdee_kcal ?? currentSummary.base_target_kcal} kcal`} />
        <MetricRow label="今天多消耗" value={`+${currentSummary.today_activity_burn_kcal} kcal`} />
        <MetricRow label="今天可吃" value={`${currentSummary.effective_target_kcal} kcal`} hint="已含活動加回" />
      </section>

      <WeeklySnapshot summary={currentSummary} compensation={compensation} onBuildRecovery={buildRecovery} />

      <section className="summary-card">
        <button className="summary-card__header" type="button" onClick={() => setActivityOpen(true)}>
          <div>
            <strong>今天的活動</strong>
            <span>{activities.length ? `${activities.length} 筆已記錄` : '尚未補充今天的活動'}</span>
          </div>
          <span>開啟</span>
        </button>
      </section>

      <section className="summary-card">
        <button className="summary-card__header" type="button" onClick={() => setMealEventOpen(true)}>
          <div>
            <strong>預記錄大餐</strong>
            <span>{mealEvents.length ? `${mealEvents.length} 個未來餐次` : '先把聚餐或大餐記下來'}</span>
          </div>
          <span>開啟</span>
        </button>
      </section>

      <section className="summary-card">
        <button className="summary-card__header" type="button" onClick={() => setInsightsOpen(true)}>
          <div>
            <strong>趨勢與分析</strong>
            <span>查看體重、熱量與活動變化</span>
          </div>
          <span>開啟</span>
        </button>
      </section>

      <section className="summary-card">
        <button className="summary-card__header" type="button" onClick={() => setGoalOpen(true)}>
          <div>
            <strong>模型與目標</strong>
            <span>調整目標體重與進階能量參數</span>
          </div>
          <span>編輯</span>
        </button>
      </section>

      <GoalSheet
        key={`${goalOpen}-${bodyGoal?.target_weight_kg ?? 'none'}-${bodyGoal?.estimated_tdee_kcal ?? 'none'}-${bodyGoal?.default_daily_deficit_kcal ?? 'none'}`}
        isOpen={goalOpen}
        onClose={() => setGoalOpen(false)}
        bodyGoal={bodyGoal}
        onSaved={saveGoal}
      />
      <FullScreenSheet isOpen={insightsOpen} onClose={() => setInsightsOpen(false)} title="趨勢與分析">
        <ProgressInsights series={progressSeries} range={progressRange} onChangeRange={(range) => void refreshProgressSeries(range)} />
      </FullScreenSheet>
      <ActivitySheet isOpen={activityOpen} onClose={() => setActivityOpen(false)} activities={activities} selectedDate={selectedDate} onSaved={syncSummary} />
      <MealEventSheet isOpen={mealEventOpen} onClose={() => setMealEventOpen(false)} mealEvents={mealEvents} planEvents={planEvents} onCreate={createMealEvent} />
      <WeightSheet isOpen={weightOpen} onClose={() => setWeightOpen(false)} latestWeight={currentSummary.latest_weight} onSaved={refreshAfterWeight} />
    </div>
  )
}

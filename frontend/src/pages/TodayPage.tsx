import { useEffect, useMemo, useState } from 'react'
import { useApp } from '../AppContext'
import { api } from '../api'
import { FullScreenSheet } from '../components/Sheets'
import { MEAL_TYPE_LABELS } from '../types'
import type { Draft, JournalAddSuggestion, LogbookRangeDay, MealLogEntry, Notification, ProgressSeries, Summary } from '../types'

const MEAL_TYPES = ['breakfast', 'lunch', 'dinner', 'snack'] as const
type MealType = typeof MEAL_TYPES[number]

type JournalFormState = {
  description_raw: string
  kcal_estimate: string
  event_time: string
  meal_type: MealType
}

type TrendPoint = {
  date: string
  value: number
  target?: number | null
}

function formatDateLabel(value: string): string {
  return new Date(`${value}T00:00:00`).toLocaleDateString('zh-TW', { month: 'numeric', day: 'numeric', weekday: 'short' })
}

function formatShortDate(value: string): string {
  return new Date(`${value}T00:00:00`).toLocaleDateString('zh-TW', { month: 'numeric', day: 'numeric' })
}

function formatTimeLabel(value: string | null): string {
  if (!value) return ''
  return new Date(value).toLocaleTimeString('zh-TW', { hour: '2-digit', minute: '2-digit' })
}

function toTimeValue(value: string | null): string {
  if (!value) return ''
  const date = new Date(value)
  const hours = String(date.getHours()).padStart(2, '0')
  const minutes = String(date.getMinutes()).padStart(2, '0')
  return `${hours}:${minutes}`
}

function toIsoDateTime(date: string, time: string): string | undefined {
  if (!time) return undefined
  return new Date(`${date}T${time}:00`).toISOString()
}

function addDays(dateString: string, diff: number): string {
  const next = new Date(`${dateString}T00:00:00`)
  next.setDate(next.getDate() + diff)
  return next.toISOString().slice(0, 10)
}

function inferMealTypeFromClock(): MealType {
  const hour = new Date().getHours()
  if (hour >= 5 && hour < 10) return 'breakfast'
  if (hour >= 10 && hour < 15) return 'lunch'
  if (hour >= 15 && hour < 18) return 'snack'
  return 'dinner'
}

function extractNotificationJobId(notification: Notification): string | null {
  const payload = notification.payload as { job_id?: unknown }
  return typeof payload.job_id === 'string' ? payload.job_id : null
}

function hasSuggestedUpdate(notification: Notification): boolean {
  const payload = notification.payload as { suggested_update?: unknown }
  return Boolean(payload.suggested_update && typeof payload.suggested_update === 'object' && Object.keys(payload.suggested_update as object).length)
}

function DailyHeader({
  date,
  remainingKcal,
  pendingCount,
  onMoveDate,
  onOpenInsights,
}: {
  date: string
  remainingKcal: number
  pendingCount: number
  onMoveDate: (diff: number) => void
  onOpenInsights: () => void
}) {
  return (
    <header className="thin-header">
      <div className="thin-header__main">
        <button className="icon-button" type="button" onClick={() => onMoveDate(-1)} aria-label="前一天">‹</button>
        <div className="thin-header__title">
          <span className="thin-header__eyebrow">今天還剩</span>
          <strong>{remainingKcal} kcal</strong>
        </div>
        <button className="icon-button" type="button" onClick={() => onMoveDate(1)} aria-label="後一天">›</button>
      </div>
      <div className="thin-header__meta">
        <span>{formatDateLabel(date)}</span>
        <div className="thin-header__actions">
          {pendingCount > 0 ? <span className="pill-indicator">{pendingCount} 待處理</span> : null}
          <button className="text-link-button" type="button" onClick={onOpenInsights}>回顧</button>
        </div>
      </div>
    </header>
  )
}

function DraftInbox({ draft, onSynced }: { draft: Draft; onSynced: (summary: Summary) => Promise<void> }) {
  const { auth, setDraft, setMessage } = useApp()
  const [loading, setLoading] = useState(false)

  async function handleClarify(answer: string) {
    if (auth.status !== 'ready') return
    setLoading(true)
    try {
      const data = await api<{ coach_message: string; draft: Draft; summary: Summary }>(
        `/api/intake/${draft.id}/clarify`,
        auth.headers,
        { method: 'POST', body: JSON.stringify({ answer }) },
      )
      setDraft(data.draft)
      setMessage(data.coach_message)
      if (data.summary) {
        await onSynced(data.summary)
      }
    } finally {
      setLoading(false)
    }
  }

  async function handleConfirm() {
    if (auth.status !== 'ready') return
    setLoading(true)
    try {
      const data = await api<{ coach_message: string; summary: Summary }>(
        `/api/intake/${draft.id}/confirm`,
        auth.headers,
        { method: 'POST', body: JSON.stringify({ force_confirm: true }) },
      )
      setDraft(null)
      setMessage(data.coach_message)
      await onSynced(data.summary)
    } finally {
      setLoading(false)
    }
  }

  const supportText = draft.followup_question
    || draft.parsed_items.map((item) => item.name).join(' / ')
    || draft.uncertainty_note

  return (
    <section className="inbox-banner">
      <div className="inbox-banner__header">
        <div>
          <strong>待確認的一餐</strong>
          <span>{draft.estimate_kcal} kcal</span>
        </div>
        <span className="pill-indicator">草稿</span>
      </div>
      <p className="support-copy">{supportText}</p>
      {draft.followup_question ? (
        <div className="chip-row">
          {(draft.answer_options ?? []).map((option) => (
            <button key={option} className="chip-button" type="button" disabled={loading} onClick={() => void handleClarify(option)}>
              {option}
            </button>
          ))}
        </div>
      ) : (
        <button className="btn btn-primary journal-inline-action" type="button" disabled={loading} onClick={() => void handleConfirm()}>
          確認記錄
        </button>
      )}
    </section>
  )
}

function AsyncInbox({ onRefresh }: { onRefresh: (date: string) => Promise<void> }) {
  const {
    auth,
    notifications,
    refreshEatFeed,
    refreshNotifications,
    selectedDate,
    setActiveTab,
  } = useApp()
  const [pendingId, setPendingId] = useState<string | null>(null)

  const unread = notifications.filter((item) => item.status === 'unread')
  if (auth.status !== 'ready' || !unread.length) return null

  async function markRead(notificationId: string) {
    setPendingId(notificationId)
    try {
      await api(`/api/notifications/${notificationId}/read`, auth.headers, { method: 'POST' })
      await refreshNotifications()
      await onRefresh(selectedDate)
    } finally {
      setPendingId(null)
    }
  }

  async function applyJob(notification: Notification) {
    const jobId = extractNotificationJobId(notification)
    if (!jobId) return
    setPendingId(notification.id)
    try {
      await api(`/api/search-jobs/${jobId}/apply`, auth.headers, { method: 'POST' })
      await api(`/api/notifications/${notification.id}/read`, auth.headers, { method: 'POST' })
      await Promise.all([
        refreshNotifications(),
        onRefresh(selectedDate),
        refreshEatFeed({ meal_type: inferMealTypeFromClock() }),
      ])
    } finally {
      setPendingId(null)
    }
  }

  async function dismissJob(notification: Notification) {
    const jobId = extractNotificationJobId(notification)
    if (!jobId) return
    setPendingId(notification.id)
    try {
      await api(`/api/search-jobs/${jobId}/dismiss`, auth.headers, { method: 'POST' })
      await api(`/api/notifications/${notification.id}/read`, auth.headers, { method: 'POST' })
      await Promise.all([
        refreshNotifications(),
        onRefresh(selectedDate),
      ])
    } finally {
      setPendingId(null)
    }
  }

  return (
    <section className="inbox-banner inbox-banner--stacked">
      <div className="summary-card__header summary-card__header--static">
        <div>
          <strong>背景更新</strong>
          <span>{unread.length} 筆可以處理</span>
        </div>
      </div>
      <div className="sheet-list">
        {unread.slice(0, 3).map((notification) => {
          const actionable = hasSuggestedUpdate(notification)
          return (
            <div key={notification.id} className="notification-row">
              <div className="notification-row__content">
                <div className="notification-row__meta">
                  <strong>{notification.title}</strong>
                  <span>{new Date(notification.created_at).toLocaleString('zh-TW', { month: 'numeric', day: 'numeric', hour: '2-digit', minute: '2-digit' })}</span>
                </div>
                <p>{notification.body}</p>
              </div>
              <div className="notification-row__actions">
                {notification.type === 'nearby_update' ? (
                  <button
                    className="btn btn-outline"
                    type="button"
                    disabled={pendingId === notification.id}
                    onClick={() => {
                      setActiveTab('eat')
                      void markRead(notification.id)
                    }}
                  >
                    看推薦
                  </button>
                ) : null}
                {actionable ? (
                  <>
                    <button className="btn btn-outline" type="button" disabled={pendingId === notification.id} onClick={() => void dismissJob(notification)}>
                      稍後
                    </button>
                    <button className="btn btn-primary" type="button" disabled={pendingId === notification.id} onClick={() => void applyJob(notification)}>
                      套用
                    </button>
                  </>
                ) : (
                  <button className="btn btn-outline" type="button" disabled={pendingId === notification.id} onClick={() => void markRead(notification.id)}>
                    已讀
                  </button>
                )}
              </div>
            </div>
          )
        })}
      </div>
    </section>
  )
}

function RecoveryBanner({ summary }: { summary: Summary }) {
  const overlay = summary.recovery_overlay
  if (!overlay?.active) return null

  return (
    <section className="summary-card summary-card--accent">
      <div className="summary-card__header summary-card__header--static">
        <div>
          <strong>回收模式進行中</strong>
          <span>
            今天目標 {overlay.adjusted_target_kcal ?? summary.effective_target_kcal} kcal
            {overlay.active_until ? `，到 ${overlay.active_until}` : ''}
          </span>
        </div>
      </div>
    </section>
  )
}

function QuickPickList({
  mealType,
  date,
  onSelect,
}: {
  mealType: MealType
  date: string
  onSelect: (description: string, kcal: number) => Promise<void>
}) {
  const { auth } = useApp()
  const [items, setItems] = useState<JournalAddSuggestion[]>([])

  useEffect(() => {
    let alive = true
    if (auth.status !== 'ready') return undefined
    void api<{ payload: { recent_items: JournalAddSuggestion[] } }>(
      `/api/journal-add-suggestions?meal_type=${mealType}&date=${date}`,
      auth.headers,
    ).then((data) => {
      if (alive) setItems(data.payload.recent_items ?? [])
    }).catch(() => {
      if (alive) setItems([])
    })
    return () => {
      alive = false
    }
  }, [auth, date, mealType])

  if (!items.length) return null

  return (
    <div className="quick-pick-list">
      {items.map((item) => (
        <button
          key={`${item.description_raw}-${item.kcal_estimate}`}
          type="button"
          className="quick-pick-row"
          onClick={() => void onSelect(item.description_raw, item.kcal_estimate)}
        >
          <span>{item.description_raw}</span>
          <strong>{item.kcal_estimate} kcal</strong>
        </button>
      ))}
    </div>
  )
}

function InlineEditor({
  mealType,
  date,
  initialLog,
  onDone,
  onSynced,
}: {
  mealType: MealType
  date: string
  initialLog?: MealLogEntry
  onDone: () => void
  onSynced: (summary: Summary) => Promise<void>
}) {
  const { auth } = useApp()
  const isEdit = Boolean(initialLog)
  const [form, setForm] = useState<JournalFormState>({
    description_raw: initialLog?.description_raw ?? '',
    kcal_estimate: initialLog ? String(initialLog.kcal_estimate) : '',
    event_time: toTimeValue(initialLog?.event_at ?? null),
    meal_type: (initialLog?.meal_type ?? mealType) as MealType,
  })
  const [loading, setLoading] = useState(false)

  async function save() {
    if (auth.status !== 'ready') return
    setLoading(true)
    try {
      if (isEdit && initialLog) {
        const data = await api<{ summary: Summary }>(
          `/api/meal-logs/${initialLog.id}`,
          auth.headers,
          {
            method: 'PATCH',
            body: JSON.stringify({
              date,
              meal_type: form.meal_type,
              description_raw: form.description_raw,
              kcal_estimate: Number(form.kcal_estimate),
              event_at: toIsoDateTime(date, form.event_time),
            }),
          },
        )
        await onSynced(data.summary)
      } else {
        const data = await api<{ summary: Summary }>(
          '/api/meal-logs/manual',
          auth.headers,
          {
            method: 'POST',
            body: JSON.stringify({
              date,
              meal_type: form.meal_type,
              description_raw: form.description_raw,
              kcal_estimate: Number(form.kcal_estimate),
              event_at: toIsoDateTime(date, form.event_time),
            }),
          },
        )
        await onSynced(data.summary)
      }
      onDone()
    } finally {
      setLoading(false)
    }
  }

  async function saveQuickPick(description: string, kcal: number) {
    if (auth.status !== 'ready') return
    setLoading(true)
    try {
      const data = await api<{ summary: Summary }>(
        '/api/meal-logs/manual',
        auth.headers,
        {
          method: 'POST',
          body: JSON.stringify({
            date,
            meal_type: form.meal_type,
            description_raw: description,
            kcal_estimate: kcal,
            event_at: toIsoDateTime(date, form.event_time),
          }),
        },
      )
      await onSynced(data.summary)
      onDone()
    } finally {
      setLoading(false)
    }
  }

  async function remove() {
    if (auth.status !== 'ready' || !initialLog) return
    setLoading(true)
    try {
      const data = await api<{ summary: Summary }>(
        `/api/meal-logs/${initialLog.id}`,
        auth.headers,
        { method: 'DELETE' },
      )
      await onSynced(data.summary)
      onDone()
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="inline-editor">
      {!isEdit ? <QuickPickList mealType={mealType} date={date} onSelect={saveQuickPick} /> : null}
      <div className="inline-grid">
        <select
          className="input-field"
          value={form.meal_type}
          onChange={(event) => setForm((current) => ({ ...current, meal_type: event.target.value as MealType }))}
        >
          {MEAL_TYPES.map((type) => (
            <option key={type} value={type}>{MEAL_TYPE_LABELS[type]}</option>
          ))}
        </select>
        <input
          className="input-field"
          placeholder="例如：雞胸飯、拿鐵、蛋餅"
          value={form.description_raw}
          onChange={(event) => setForm((current) => ({ ...current, description_raw: event.target.value }))}
        />
        <input
          className="input-field"
          type="number"
          placeholder="熱量"
          value={form.kcal_estimate}
          onChange={(event) => setForm((current) => ({ ...current, kcal_estimate: event.target.value }))}
        />
        <input
          className="input-field"
          type="time"
          value={form.event_time}
          onChange={(event) => setForm((current) => ({ ...current, event_time: event.target.value }))}
        />
      </div>
      <div className="inline-actions">
        <button className="btn btn-outline" type="button" onClick={onDone}>取消</button>
        {isEdit ? (
          <button className="btn btn-outline" type="button" disabled={loading} onClick={() => void remove()}>
            刪除
          </button>
        ) : null}
        <button
          className="btn btn-primary"
          type="button"
          disabled={loading || !form.description_raw || !form.kcal_estimate}
          onClick={() => void save()}
        >
          {isEdit ? '更新' : '新增'}
        </button>
      </div>
    </div>
  )
}

function MealSection({
  mealType,
  logs,
  subtotal,
  count,
  activeEditor,
  onOpenEditor,
  onEditLog,
  onCloseEditor,
  onSynced,
  date,
}: {
  mealType: MealType
  logs: MealLogEntry[]
  subtotal: number
  count: number
  activeEditor: { mealType: MealType; log?: MealLogEntry } | null
  onOpenEditor: (mealType: MealType) => void
  onEditLog: (mealType: MealType, log: MealLogEntry) => void
  onCloseEditor: () => void
  onSynced: (summary: Summary) => Promise<void>
  date: string
}) {
  const isActive = activeEditor?.mealType === mealType
  const activeLog = isActive ? activeEditor?.log : undefined

  return (
    <section className={`journal-section ${isActive ? 'journal-section--active' : ''}`}>
      <button className="journal-section__header" type="button" onClick={() => onOpenEditor(mealType)}>
        <div>
          <strong>{MEAL_TYPE_LABELS[mealType]}</strong>
          <span>{count ? `${count} 筆` : '尚未記錄'}</span>
        </div>
        <div className="journal-section__kcal">
          <strong>{subtotal} kcal</strong>
          <span className="journal-section__plus">＋</span>
        </div>
      </button>
      {logs.length ? (
        <div className="journal-entry-list">
          {logs.map((log) => (
            <button key={log.id} className="journal-entry-row" type="button" onClick={() => onEditLog(mealType, log)}>
              <div>
                <strong>{log.description_raw}</strong>
                <span>{formatTimeLabel(log.event_at)}{formatTimeLabel(log.event_at) ? ' · ' : ''}{log.kcal_estimate} kcal</span>
              </div>
              <strong>{log.kcal_estimate}</strong>
            </button>
          ))}
        </div>
      ) : (
        <div className="empty-row">還沒有記錄，點上方即可新增。</div>
      )}
      {isActive ? (
        <InlineEditor
          mealType={mealType}
          date={date}
          initialLog={activeLog}
          onDone={onCloseEditor}
          onSynced={onSynced}
        />
      ) : null}
    </section>
  )
}

function TrendBars({ points }: { points: TrendPoint[] }) {
  if (!points.length) return <div className="empty-row empty-row--sheet">還沒有足夠資料畫出趨勢。</div>
  const max = Math.max(...points.map((point) => Math.max(Number(point.value), Number(point.target ?? 0), 1)))
  return (
    <div className="trend-bars">
      {points.slice(-10).map((point) => (
        <div key={point.date} className="trend-bars__item">
          <div className="trend-bars__track">
            {point.target != null ? (
              <div className="trend-bars__target" style={{ height: `${Math.max(8, (Number(point.target) / max) * 100)}%` }} />
            ) : null}
            <div className="trend-bars__fill" style={{ height: `${Math.max(8, (Number(point.value) / max) * 100)}%` }} />
          </div>
          <span>{formatShortDate(point.date)}</span>
        </div>
      ))}
    </div>
  )
}

function buildTrendPoints(
  range: '7d' | '30d' | '90d',
  logbookRange: LogbookRangeDay[],
  progressSeries: ProgressSeries | null,
): TrendPoint[] {
  if (range === '7d') {
    return logbookRange.map((day) => ({
      date: day.date,
      value: day.consumed_kcal,
      target: day.target_kcal,
    }))
  }
  return (progressSeries?.calorie_points ?? []).map((point) => ({
    date: point.date,
    value: Number(point.value),
    target: point.target,
  }))
}

export default function TodayPage() {
  const {
    auth,
    summary,
    selectedDate,
    draft,
    notifications,
    logbookRange,
    progressSeries,
    refreshSummary,
    refreshLogbookRange,
    refreshNotifications,
    refreshActivities,
    refreshBodyGoal,
    refreshProgressSeries,
    refreshEatFeed,
    setSummary,
  } = useApp()
  const [activeEditor, setActiveEditor] = useState<{ mealType: MealType; log?: MealLogEntry } | null>(null)
  const [insightsOpen, setInsightsOpen] = useState(false)
  const [trendRange, setTrendRange] = useState<'7d' | '30d' | '90d'>('7d')

  useEffect(() => {
    if (auth.status !== 'ready') return
    void refreshSummary()
    void refreshLogbookRange()
    void refreshNotifications()
  }, [auth.status, refreshLogbookRange, refreshNotifications, refreshSummary])

  useEffect(() => {
    if (auth.status !== 'ready' || !insightsOpen || trendRange === '7d') return
    void refreshProgressSeries(trendRange)
  }, [auth.status, insightsOpen, refreshProgressSeries, trendRange])

  const groupedLogs = useMemo(() => {
    const grouped: Record<MealType, MealLogEntry[]> = {
      breakfast: [],
      lunch: [],
      dinner: [],
      snack: [],
    }
    if (!summary) return grouped
    summary.logs.forEach((log) => {
      const key = log.meal_type as MealType
      if (grouped[key]) grouped[key].push(log)
    })
    MEAL_TYPES.forEach((type) => {
      grouped[type].sort((a, b) => String(a.event_at ?? '').localeCompare(String(b.event_at ?? '')))
    })
    return grouped
  }, [summary])

  const pendingCount = (draft ? 1 : 0) + (summary?.pending_async_updates_count ?? 0)

  const trendPoints = useMemo(
    () => buildTrendPoints(trendRange, logbookRange, progressSeries),
    [logbookRange, progressSeries, trendRange],
  )

  if (auth.status !== 'ready' || !summary) {
    return <div className="page-container"><div className="page-skeleton" /></div>
  }

  async function syncAfterSummary(summaryData: Summary) {
    setSummary(summaryData)
    await Promise.all([
      refreshLogbookRange(summaryData.date),
      refreshActivities(summaryData.date),
      refreshProgressSeries(),
      refreshBodyGoal(),
      refreshEatFeed({ meal_type: inferMealTypeFromClock() }),
    ])
  }

  async function refreshForDate(dateValue: string) {
    await Promise.all([
      refreshSummary(dateValue),
      refreshLogbookRange(dateValue),
      refreshNotifications(),
      refreshActivities(dateValue),
    ])
  }

  function handleMoveDate(diff: number) {
    const next = addDays(selectedDate, diff)
    void refreshForDate(next)
  }

  return (
    <div className="page-container" id="page-today">
      <DailyHeader
        date={summary.date}
        remainingKcal={summary.remaining_kcal}
        pendingCount={pendingCount}
        onMoveDate={handleMoveDate}
        onOpenInsights={() => setInsightsOpen(true)}
      />

      {draft ? <DraftInbox draft={draft} onSynced={syncAfterSummary} /> : null}
      {notifications.length ? <AsyncInbox onRefresh={refreshSummary} /> : null}
      <RecoveryBanner summary={summary} />

      <div className="journal-stack">
        {MEAL_TYPES.map((mealType) => (
          <MealSection
            key={mealType}
            mealType={mealType}
            logs={groupedLogs[mealType]}
            subtotal={summary.meal_subtotals?.[mealType] ?? 0}
            count={summary.meal_counts?.[mealType] ?? groupedLogs[mealType].length}
            activeEditor={activeEditor}
            onOpenEditor={(type) => setActiveEditor({ mealType: type })}
            onEditLog={(type, log) => setActiveEditor({ mealType: type, log })}
            onCloseEditor={() => setActiveEditor(null)}
            onSynced={syncAfterSummary}
            date={summary.date}
          />
        ))}
      </div>

      <FullScreenSheet isOpen={insightsOpen} onClose={() => setInsightsOpen(false)} title="趨勢回顧">
        <div className="sheet-stack">
          <div className="chip-row">
            {['7d', '30d', '90d'].map((range) => (
              <button
                key={range}
                className={`chip-button ${trendRange === range ? 'chip-button--active' : ''}`}
                type="button"
                onClick={() => setTrendRange(range as '7d' | '30d' | '90d')}
              >
                {range.toUpperCase()}
              </button>
            ))}
          </div>
          <section className="sheet-card">
            <div className="sheet-card__header">
              <h4>攝取趨勢</h4>
              <span>{trendRange.toUpperCase()}</span>
            </div>
            <TrendBars points={trendPoints} />
          </section>
        </div>
      </FullScreenSheet>
    </div>
  )
}

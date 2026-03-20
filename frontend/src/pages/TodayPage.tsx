import { useEffect, useMemo, useState } from 'react'
import { useApp } from '../AppContext'
import { api } from '../api'
import { FullScreenSheet } from '../components/Sheets'
import { MEAL_TYPE_LABELS } from '../types'
import type { Draft, JournalAddSuggestion, LogbookRangeDay, MealLogEntry, Notification, Summary } from '../types'

type JournalFormState = {
  description_raw: string
  kcal_estimate: string
  event_time: string
}

function formatDateLabel(value: string): string {
  return new Date(`${value}T00:00:00`).toLocaleDateString('zh-TW', { month: 'numeric', day: 'numeric', weekday: 'short' })
}

function formatNotificationTime(value: string): string {
  return new Date(value).toLocaleString('zh-TW', {
    month: 'numeric',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  })
}

function toTimeValue(value?: string | null): string {
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

function inferMealTypeFromClock(): string {
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
          <span className="thin-header__eyebrow">今天還有</span>
          <strong>{remainingKcal} kcal</strong>
        </div>
        <button className="icon-button" type="button" onClick={() => onMoveDate(1)} aria-label="後一天">›</button>
      </div>
      <div className="thin-header__meta">
        <span>{formatDateLabel(date)}</span>
        <div className="thin-header__actions">
          {pendingCount > 0 ? <span className="pill-indicator">{pendingCount} 個待處理</span> : null}
          <button className="text-link-button" type="button" onClick={onOpenInsights}>趨勢</button>
        </div>
      </div>
    </header>
  )
}

function DraftInbox() {
  const {
    auth,
    draft,
    selectedDate,
    setDraft,
    setMessage,
    setSummary,
    refreshActivities,
    refreshBodyGoal,
    refreshEatFeed,
    refreshLogbookRange,
    refreshProgressSeries,
  } = useApp()
  const [loading, setLoading] = useState(false)

  if (auth.status !== 'ready' || !draft) return null

  async function syncAfterDraft(summary: Summary) {
    setSummary(summary)
    await Promise.all([
      refreshLogbookRange(selectedDate),
      refreshActivities(selectedDate),
      refreshProgressSeries(),
      refreshBodyGoal(),
      refreshEatFeed({ meal_type: inferMealTypeFromClock() }),
    ])
  }

  async function handleClarify(answer: string) {
    const currentDraft = draft
    if (!currentDraft) return
    setLoading(true)
    try {
      const data = await api<{ coach_message: string; draft: Draft; summary?: Summary }>(
        `/api/intake/${currentDraft.id}/clarify`,
        auth.headers,
        { method: 'POST', body: JSON.stringify({ answer }) },
      )
      setDraft(data.draft)
      setMessage(data.coach_message)
      if (data.summary) {
        await syncAfterDraft(data.summary)
      }
    } finally {
      setLoading(false)
    }
  }

  async function handleConfirm() {
    const currentDraft = draft
    if (!currentDraft) return
    setLoading(true)
    try {
      const data = await api<{ coach_message: string; summary: Summary }>(
        `/api/intake/${currentDraft.id}/confirm`,
        auth.headers,
        { method: 'POST', body: JSON.stringify({ force_confirm: true }) },
      )
      setDraft(null)
      setMessage(data.coach_message)
      await syncAfterDraft(data.summary)
    } finally {
      setLoading(false)
    }
  }

  return (
    <section className="inbox-banner">
      <div className="inbox-banner__header">
        <div>
          <strong>還有一筆待確認</strong>
          <span>{draft.estimate_kcal} kcal</span>
        </div>
        <span className="pill-indicator">草稿</span>
      </div>
      <p className="support-copy">{draft.followup_question || draft.parsed_items.map((item) => item.name).join(' / ') || draft.uncertainty_note}</p>
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
          直接記錄
        </button>
      )}
    </section>
  )
}

function AsyncInbox() {
  const {
    auth,
    notifications,
    refreshEatFeed,
    refreshNotifications,
    refreshSummary,
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
      await refreshSummary(selectedDate)
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
        refreshSummary(selectedDate),
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
        refreshSummary(selectedDate),
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
          <span>{unread.length} 個可以立即處理</span>
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
                  <span>{formatNotificationTime(notification.created_at)}</span>
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
                    去看推薦
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
  mealType: string
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

function InlineComposer({ mealType, date, onDone }: { mealType: string; date: string; onDone: () => void }) {
  const { auth, setSummary, refreshActivities, refreshBodyGoal, refreshEatFeed, refreshLogbookRange, refreshProgressSeries } = useApp()
  const [form, setForm] = useState<JournalFormState>({ description_raw: '', kcal_estimate: '', event_time: '' })
  const [loading, setLoading] = useState(false)

  async function syncSummary(summary: Summary) {
    setSummary(summary)
    await Promise.all([
      refreshLogbookRange(date),
      refreshActivities(date),
      refreshProgressSeries(),
      refreshBodyGoal(),
      refreshEatFeed({ meal_type: inferMealTypeFromClock() }),
    ])
  }

  async function createManual(description: string, kcal: number) {
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
            meal_type: mealType,
            description_raw: description,
            kcal_estimate: kcal,
            event_at: toIsoDateTime(date, form.event_time),
          }),
        },
      )
      await syncSummary(data.summary)
      onDone()
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="inline-editor">
      <QuickPickList mealType={mealType} date={date} onSelect={createManual} />
      <div className="inline-grid">
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
        <button
          className="btn btn-primary"
          type="button"
          disabled={loading || !form.description_raw || !form.kcal_estimate}
          onClick={() => void createManual(form.description_raw, Number(form.kcal_estimate))}
        >
          新增
        </button>
      </div>
    </div>
  )
}

function InlineEditor({ log, date, onDone }: { log: MealLogEntry; date: string; onDone: () => void }) {
  const { auth, setSummary, refreshActivities, refreshBodyGoal, refreshEatFeed, refreshLogbookRange, refreshProgressSeries } = useApp()
  const [form, setForm] = useState({
    meal_type: log.meal_type,
    description_raw: log.description_raw,
    kcal_estimate: String(log.kcal_estimate),
    event_time: toTimeValue(log.event_at),
  })
  const [loading, setLoading] = useState(false)

  async function syncSummary(summary: Summary) {
    setSummary(summary)
    await Promise.all([
      refreshLogbookRange(date),
      refreshActivities(date),
      refreshProgressSeries(),
      refreshBodyGoal(),
      refreshEatFeed({ meal_type: inferMealTypeFromClock() }),
    ])
  }

  async function save() {
    if (auth.status !== 'ready') return
    setLoading(true)
    try {
      const data = await api<{ summary: Summary }>(
        `/api/meal-logs/${log.id}`,
        auth.headers,
        {
          method: 'PATCH',
          body: JSON.stringify({
            meal_type: form.meal_type,
            description_raw: form.description_raw,
            kcal_estimate: Number(form.kcal_estimate),
            event_at: toIsoDateTime(date, form.event_time),
          }),
        },
      )
      await syncSummary(data.summary)
      onDone()
    } finally {
      setLoading(false)
    }
  }

  async function remove() {
    if (auth.status !== 'ready') return
    setLoading(true)
    try {
      const data = await api<{ summary: Summary }>(`/api/meal-logs/${log.id}`, auth.headers, { method: 'DELETE' })
      await syncSummary(data.summary)
      onDone()
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="inline-editor">
      <div className="inline-grid">
        <select
          className="input-field"
          value={form.meal_type}
          onChange={(event) => setForm((current) => ({ ...current, meal_type: event.target.value }))}
        >
          {Object.entries(MEAL_TYPE_LABELS).map(([key, label]) => (
            <option key={key} value={key}>{label}</option>
          ))}
        </select>
        <input
          className="input-field"
          value={form.description_raw}
          onChange={(event) => setForm((current) => ({ ...current, description_raw: event.target.value }))}
        />
        <input
          className="input-field"
          type="number"
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
        <button className="btn btn-secondary" type="button" disabled={loading} onClick={() => void remove()}>刪除</button>
        <button className="btn btn-primary" type="button" disabled={loading} onClick={() => void save()}>儲存</button>
      </div>
    </div>
  )
}

function MealSection({
  mealType,
  logs,
  subtotal,
  date,
  addingMealType,
  editingLogId,
  onStartAdd,
  onStopAdd,
  onStartEdit,
  onStopEdit,
}: {
  mealType: string
  logs: MealLogEntry[]
  subtotal: number
  date: string
  addingMealType: string | null
  editingLogId: number | null
  onStartAdd: (mealType: string) => void
  onStopAdd: () => void
  onStartEdit: (id: number) => void
  onStopEdit: () => void
}) {
  return (
    <section className="journal-section">
      <button className="journal-section__header" type="button" onClick={() => onStartAdd(mealType)}>
        <div>
          <strong>{MEAL_TYPE_LABELS[mealType]}</strong>
          <span>{logs.length ? `${logs.length} 筆紀錄` : '還沒有記錄，點一下直接新增'}</span>
        </div>
        <div className="journal-section__kcal">
          <strong>{subtotal} kcal</strong>
          <span>+</span>
        </div>
      </button>

      {addingMealType === mealType ? <InlineComposer mealType={mealType} date={date} onDone={onStopAdd} /> : null}

      <div className="journal-entry-list">
        {logs.length === 0 && addingMealType !== mealType ? (
          <div className="empty-row">這餐還沒有東西，點上面直接新增。</div>
        ) : null}
        {logs.map((log) => (
          <div key={log.id} className="journal-entry-card">
            <button className="journal-entry-row" type="button" onClick={() => onStartEdit(log.id)}>
              <div>
                <strong>{log.description_raw}</strong>
                <span>{log.event_at ? toTimeValue(log.event_at) : '未指定時間'}</span>
              </div>
              <strong>{log.kcal_estimate} kcal</strong>
            </button>
            {editingLogId === log.id ? <InlineEditor log={log} date={date} onDone={onStopEdit} /> : null}
          </div>
        ))}
      </div>
    </section>
  )
}

function InsightsContent({ summary, days }: { summary: Summary; days: LogbookRangeDay[] }) {
  const maxKcal = Math.max(...days.map((day) => day.consumed_kcal || 0), summary.target_kcal || 1)

  return (
    <div className="sheet-stack">
      <section className="sheet-card">
        <div className="sheet-card__header">
          <h4>今天摘要</h4>
          <span>{summary.consumed_kcal} / {summary.target_kcal} kcal</span>
        </div>
        <div className="metric-pill-row">
          <div className="metric-pill">
            <span>剩餘</span>
            <strong>{summary.remaining_kcal}</strong>
          </div>
          <div className="metric-pill">
            <span>活動加回</span>
            <strong>+{summary.today_activity_burn_kcal}</strong>
          </div>
          <div className="metric-pill">
            <span>已記錄餐數</span>
            <strong>{summary.logs.length}</strong>
          </div>
        </div>
      </section>
      <section className="sheet-card">
        <div className="sheet-card__header">
          <h4>最近 7 天</h4>
          <span>已吃 vs 目標</span>
        </div>
        <div className="mini-bars">
          {days.map((day) => (
            <div key={day.date} className="mini-bars__item">
              <div className="mini-bars__track">
                <div className="mini-bars__fill" style={{ height: `${Math.max(8, (day.consumed_kcal / maxKcal) * 100)}%` }} />
              </div>
              <span>{day.date.slice(5)}</span>
            </div>
          ))}
        </div>
      </section>
    </div>
  )
}

export default function TodayPage() {
  const { auth, summary, selectedDate, refreshActivities, refreshLogbookRange, refreshSummary, logbookRange } = useApp()
  const [addingMealType, setAddingMealType] = useState<string | null>(null)
  const [editingLogId, setEditingLogId] = useState<number | null>(null)
  const [insightsOpen, setInsightsOpen] = useState(false)

  useEffect(() => {
    if (auth.status !== 'ready') return
    void refreshSummary(selectedDate)
  }, [auth.status, refreshSummary, selectedDate])

  const groupedLogs = useMemo(() => {
    const source = summary?.logs ?? []
    return {
      breakfast: source.filter((log) => log.meal_type === 'breakfast'),
      lunch: source.filter((log) => log.meal_type === 'lunch'),
      dinner: source.filter((log) => log.meal_type === 'dinner'),
      snack: source.filter((log) => log.meal_type === 'snack'),
    }
  }, [summary])

  if (auth.status !== 'ready' || !summary) {
    return <div className="page-container"><div className="page-skeleton" /></div>
  }

  async function moveDate(diff: number) {
    const target = new Date(`${selectedDate}T00:00:00`)
    target.setDate(target.getDate() + diff)
    const nextDate = target.toISOString().slice(0, 10)
    setAddingMealType(null)
    setEditingLogId(null)
    await Promise.all([refreshSummary(nextDate), refreshLogbookRange(nextDate), refreshActivities(nextDate)])
  }

  function openAdd(mealType: string) {
    setEditingLogId(null)
    setAddingMealType((current) => current === mealType ? null : mealType)
  }

  function openEdit(logId: number) {
    setAddingMealType(null)
    setEditingLogId((current) => current === logId ? null : logId)
  }

  return (
    <div className="page-container" id="page-today">
      <DailyHeader
        date={selectedDate}
        remainingKcal={summary.remaining_kcal}
        pendingCount={summary.pending_async_updates_count}
        onMoveDate={moveDate}
        onOpenInsights={() => setInsightsOpen(true)}
      />

      <DraftInbox />
      <AsyncInbox />
      <RecoveryBanner summary={summary} />

      <div className="journal-stack">
        {(['breakfast', 'lunch', 'dinner', 'snack'] as const).map((mealType) => (
          <MealSection
            key={mealType}
            mealType={mealType}
            logs={groupedLogs[mealType]}
            subtotal={summary.meal_subtotals?.[mealType] ?? 0}
            date={selectedDate}
            addingMealType={addingMealType}
            editingLogId={editingLogId}
            onStartAdd={openAdd}
            onStopAdd={() => setAddingMealType(null)}
            onStartEdit={openEdit}
            onStopEdit={() => setEditingLogId(null)}
          />
        ))}
      </div>

      <FullScreenSheet isOpen={insightsOpen} onClose={() => setInsightsOpen(false)} title="日誌趨勢">
        <InsightsContent summary={summary} days={logbookRange} />
      </FullScreenSheet>
    </div>
  )
}

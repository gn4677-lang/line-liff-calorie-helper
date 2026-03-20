import { useEffect, useMemo, useState } from 'react'
import { adminApi, clearStoredAdminToken } from '../adminApi'
import type {
  AdminSession,
  AlertItem,
  ObservabilityDashboard,
  ReviewQueueItem,
  TraceDetailResponse,
  TraceListItem,
} from '../adminTypes'
import SummaryCards from '../components/SummaryCards'
import QualityTrendCharts from '../components/QualityTrendCharts'
import TaskHealthTable from '../components/TaskHealthTable'
import RecommendationHealthPanel from '../components/RecommendationHealthPanel'
import UsagePanel from '../components/UsagePanel'
import MemoryDigestPanel from '../components/MemoryDigestPanel'
import OperationalErrorsPanel from '../components/OperationalErrorsPanel'
import AlertsPanel from '../components/AlertsPanel'
import ReviewQueuePanel from '../components/ReviewQueuePanel'
import TraceListPanel from '../components/TraceListPanel'
import TraceDetailDrawer from '../components/TraceDetailDrawer'

type Props = {
  token: string
  session: AdminSession
  onSessionInvalid: () => void
  onLogout: () => void
}

type TraceFilterKey =
  | 'task_family'
  | 'surface'
  | 'source_mode'
  | 'status'
  | 'provider_name'
  | 'model_name'
  | 'route_policy'
  | 'llm_cache'
  | 'has_error'
  | 'has_feedback'
  | 'has_unknown_case'

type TraceFilters = Record<TraceFilterKey, string>

const DEFAULT_FILTERS: TraceFilters = {
  task_family: '',
  surface: '',
  source_mode: '',
  status: '',
  provider_name: '',
  model_name: '',
  route_policy: '',
  llm_cache: '',
  has_error: '',
  has_feedback: '',
  has_unknown_case: '',
}

function buildTraceQuery(filters: TraceFilters, limit: number, offset: number): string {
  const params = new URLSearchParams()
  Object.entries(filters).forEach(([key, value]) => {
    if (value !== '') params.set(key, value)
  })
  params.set('limit', String(limit))
  params.set('offset', String(offset))
  return `/api/observability/traces?${params.toString()}`
}

export default function ObservabilityDashboardPage({ token, session, onSessionInvalid, onLogout }: Props) {
  const [windowHours, setWindowHours] = useState(168)
  const [trendDays, setTrendDays] = useState(7)
  const [dashboard, setDashboard] = useState<ObservabilityDashboard | null>(null)
  const [alerts, setAlerts] = useState<AlertItem[]>([])
  const [reviewQueue, setReviewQueue] = useState<ReviewQueueItem[]>([])
  const [traces, setTraces] = useState<TraceListItem[]>([])
  const [traceTotal, setTraceTotal] = useState(0)
  const [traceOffset, setTraceOffset] = useState(0)
  const [traceFilters, setTraceFilters] = useState<TraceFilters>(DEFAULT_FILTERS)
  const [selectedTrace, setSelectedTrace] = useState<TraceDetailResponse | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function withAuth<T>(fn: () => Promise<T>): Promise<T | null> {
    try {
      return await fn()
    } catch (err) {
      if (err instanceof Error && err.message.includes('401')) {
        clearStoredAdminToken()
        onSessionInvalid()
        return null
      }
      throw err
    }
  }

  async function refreshDashboard() {
    setLoading(true)
    setError(null)
    try {
      const [dashboardResponse, alertsResponse, reviewResponse] = await Promise.all([
        withAuth(() =>
          adminApi<{ dashboard: ObservabilityDashboard }>(
            `/api/observability/dashboard?window_hours=${windowHours}&trend_days=${trendDays}`,
            token,
          ),
        ),
        withAuth(() => adminApi<{ alerts: AlertItem[] }>('/api/observability/alerts?status=open&limit=50', token)),
        withAuth(() => adminApi<{ review_queue: ReviewQueueItem[] }>('/api/observability/review-queue?limit=50', token)),
      ])
      if (!dashboardResponse || !alertsResponse || !reviewResponse) return
      setDashboard(dashboardResponse.payload.dashboard)
      setAlerts(alertsResponse.payload.alerts)
      setReviewQueue(reviewResponse.payload.review_queue)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load dashboard.')
    } finally {
      setLoading(false)
    }
  }

  async function refreshTraces(offset = traceOffset, filters = traceFilters) {
    try {
      const response = await withAuth(() =>
        adminApi<{ items: TraceListItem[]; total: number; limit: number; offset: number }>(
          buildTraceQuery(filters, 25, offset),
          token,
        ),
      )
      if (!response) return
      setTraces(response.payload.items)
      setTraceTotal(response.payload.total)
      setTraceOffset(response.payload.offset)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load traces.')
    }
  }

  useEffect(() => {
    void refreshDashboard()
  }, [windowHours, trendDays])

  useEffect(() => {
    void refreshTraces(0, traceFilters)
  }, [traceFilters])

  async function openTrace(traceId: string) {
    try {
      const response = await withAuth(() =>
        adminApi<{ trace_detail: TraceDetailResponse }>(`/api/observability/traces/${traceId}`, token),
      )
      if (!response) return
      setSelectedTrace(response.payload.trace_detail)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load trace detail.')
    }
  }

  async function evaluateAlerts() {
    await withAuth(() =>
      adminApi<{ alerts: AlertItem[]; triggered_count: number }>(
        '/api/observability/alerts/evaluate',
        token,
        { method: 'POST' },
      ),
    )
    await refreshDashboard()
  }

  async function refreshKnowledgeLayer() {
    await withAuth(() =>
      adminApi<{ knowledge: Record<string, unknown> }>(
        '/api/observability/knowledge/refresh',
        token,
        { method: 'POST' },
      ),
    )
    await refreshDashboard()
  }

  async function updateAlertStatus(id: string, status: 'acknowledged' | 'resolved') {
    await withAuth(() =>
      adminApi<{ alert: AlertItem }>(`/api/observability/alerts/${id}/status`, token, {
        method: 'POST',
        body: JSON.stringify({ status }),
      }),
    )
    await refreshDashboard()
  }

  async function updateReviewStatus(id: number, status: 'triaged' | 'in_progress' | 'resolved' | 'ignored') {
    await withAuth(() =>
      adminApi<{ review_item: ReviewQueueItem }>(`/api/observability/review-queue/${id}/status`, token, {
        method: 'POST',
        body: JSON.stringify({ status }),
      }),
    )
    await refreshDashboard()
  }

  const filters = useMemo(
    () =>
      [
        { key: 'task_family', label: 'Task Family' },
        { key: 'surface', label: 'Surface' },
        { key: 'source_mode', label: 'Source Mode' },
        { key: 'status', label: 'Status' },
        { key: 'provider_name', label: 'Provider' },
        { key: 'model_name', label: 'Model' },
        { key: 'route_policy', label: 'Route Policy' },
        { key: 'llm_cache', label: 'LLM Cache' },
        { key: 'has_error', label: 'Has Error' },
        { key: 'has_feedback', label: 'Has Feedback' },
        { key: 'has_unknown_case', label: 'Has Unknown' },
      ] as const,
    [],
  )

  return (
    <div className="admin-shell">
      <header className="admin-topbar">
        <div>
          <h1 className="text-title">Observability</h1>
          <p className="text-caption text-secondary">
            Session {session.label} / expires {session.expires_at}
          </p>
        </div>
        <div className="admin-topbar-actions">
          <select className="input-field" value={windowHours} onChange={(event) => setWindowHours(Number(event.target.value))}>
            <option value={24}>24h</option>
            <option value={72}>72h</option>
            <option value={168}>7d</option>
            <option value={336}>14d</option>
            <option value={720}>30d</option>
          </select>
          <select className="input-field" value={trendDays} onChange={(event) => setTrendDays(Number(event.target.value))}>
            <option value={7}>7d trend</option>
            <option value={14}>14d trend</option>
            <option value={30}>30d trend</option>
          </select>
          <button className="btn btn-outline" onClick={() => void refreshDashboard()}>Refresh</button>
          <button className="btn btn-outline" onClick={() => void refreshKnowledgeLayer()}>Refresh Knowledge</button>
          <button className="btn btn-primary" onClick={() => void evaluateAlerts()}>Evaluate Alerts</button>
          <button className="btn btn-secondary" onClick={onLogout}>Logout</button>
        </div>
      </header>

      <main className="admin-page">
        {error ? <div className="card admin-status-warning">{error}</div> : null}
        {loading && !dashboard ? <div className="card">Loading dashboard...</div> : null}
        {dashboard ? (
          <>
            <SummaryCards cards={dashboard.summary_cards} />
            <QualityTrendCharts trends={dashboard.quality_trends} />
            <TaskHealthTable rows={dashboard.task_health} />
            <UsagePanel usage={dashboard.usage_panels} />
            <RecommendationHealthPanel product={dashboard.product_panels} />
            <MemoryDigestPanel memory={dashboard.memory_panels} />
            <OperationalErrorsPanel operational={dashboard.operational_panels} />
            <AlertsPanel alerts={alerts} onStatus={(id, status) => void updateAlertStatus(id, status)} />
            <ReviewQueuePanel
              items={reviewQueue}
              onStatus={(id, status) => void updateReviewStatus(id, status)}
              onOpenTrace={(traceId) => (traceId ? void openTrace(traceId) : undefined)}
            />
            <section className="card">
              <div className="admin-panel-header">
                <h2 className="text-heading">Trace Filters</h2>
              </div>
              <div className="admin-trace-filters">
                {filters.map((filter) => (
                  <input
                    key={filter.key}
                    className="input-field"
                    placeholder={filter.label}
                    value={traceFilters[filter.key]}
                    onChange={(event) =>
                      setTraceFilters((previous) => ({ ...previous, [filter.key]: event.target.value }))
                    }
                  />
                ))}
              </div>
            </section>
            <TraceListPanel
              traces={traces}
              total={traceTotal}
              offset={traceOffset}
              limit={25}
              onOffsetChange={(nextOffset) => void refreshTraces(nextOffset)}
              onOpenTrace={(traceId) => void openTrace(traceId)}
            />
          </>
        ) : null}
      </main>

      <TraceDetailDrawer detail={selectedTrace} onClose={() => setSelectedTrace(null)} />
    </div>
  )
}

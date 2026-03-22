/* eslint-disable react-refresh/only-export-components */
import { createContext, useCallback, useContext, useEffect, useState } from 'react'
import type { ReactNode } from 'react'
import liff from '@line/liff'
import { api } from './api'
import { useToast, ToastContainer, type ToastType } from './components/Toast'
import type {
  ActivityAdjustment,
  AuthState,
  BodyGoal,
  ClientConfig,
  Compensation,
  DayPlan,
  Draft,
  EatFeed,
  FavoriteStore,
  GoldenOrder,
  LogbookRangeDay,
  MealEvent,
  MeResponse,
  Notification,
  OnboardingState,
  PlanEvent,
  Preferences,
  ProgressSeries,
  SavedPlace,
  Summary,
  TabKey,
} from './types'
import { DEFAULT_PREFERENCES } from './types'

export type EatFeedRequest = {
  meal_type: string
  time_context: 'now' | 'later'
  style_context: string
  location_mode: 'none' | 'geolocation' | 'manual' | 'saved_place'
  saved_place_id?: number
  lat?: number
  lng?: number
  query?: string
  selected_chip_id?: string | null
  explore_mode?: boolean
}

type SavedPlaceDraft = {
  label: string
  address: string
  is_default?: boolean
}

type FavoriteStoreDraft = {
  name: string
  label?: string
  address?: string
  external_link?: string
}

type MealEventDraft = {
  event_date: string
  meal_type: 'breakfast' | 'lunch' | 'dinner' | 'snack'
  title: string
  expected_kcal?: number
  notes?: string
}

type AppContextValue = {
  auth: AuthState
  activeTab: TabKey
  setActiveTab: (tab: TabKey) => void
  summary: Summary | null
  setSummary: (summary: Summary | null) => void
  selectedDate: string
  setSelectedDate: (date: string) => void
  draft: Draft | null
  setDraft: (draft: Draft | null) => void
  logbookRange: LogbookRangeDay[]
  bodyGoal: BodyGoal | null
  activities: ActivityAdjustment[]
  progressSeries: ProgressSeries | null
  progressRange: string
  setProgressRange: (range: string) => void
  eatFeed: EatFeed | null
  savedPlaces: SavedPlace[]
  favoriteStores: FavoriteStore[]
  goldenOrders: GoldenOrder[]
  planEvents: PlanEvent[]
  mealEvents: MealEvent[]
  notifications: Notification[]
  onboarding: OnboardingState | null
  setOnboarding: (state: OnboardingState | null) => void
  onboardingForm: Preferences
  setOnboardingForm: (fn: (prev: Preferences) => Preferences) => void
  dayPlan: DayPlan | null
  setDayPlan: (plan: DayPlan | null) => void
  compensation: Compensation | null
  setCompensation: (plan: Compensation | null) => void
  message: string
  setMessage: (message: string) => void
  loading: boolean
  setLoading: (loading: boolean) => void
  refreshSummary: (targetDate?: string) => Promise<void>
  refreshLogbookRange: (targetDate?: string) => Promise<void>
  refreshBodyGoal: () => Promise<void>
  refreshActivities: (targetDate?: string) => Promise<void>
  refreshProgressSeries: (range?: string, resolution?: string) => Promise<void>
  refreshEatFeed: (request?: Partial<EatFeedRequest>) => Promise<void>
  refreshPlanEvents: () => Promise<void>
  refreshMealEvents: () => Promise<void>
  refreshNotifications: () => Promise<void>
  refreshSavedPlaces: () => Promise<void>
  refreshFavoriteStores: () => Promise<void>
  markNotificationRead: (notificationId: string) => Promise<void>
  createSavedPlace: (draft: SavedPlaceDraft) => Promise<void>
  createFavoriteStore: (draft: FavoriteStoreDraft) => Promise<void>
  createMealEvent: (draft: MealEventDraft) => Promise<void>
  showToast: (message: string, type?: ToastType) => void
}

const AppContext = createContext<AppContextValue | null>(null)

function todayIso(): string {
  return new Date().toISOString().slice(0, 10)
}

function addDays(dateString: string, diff: number): string {
  const next = new Date(`${dateString}T00:00:00`)
  next.setDate(next.getDate() + diff)
  return next.toISOString().slice(0, 10)
}

function resolveInitialTab(): TabKey {
  const tab = new URLSearchParams(window.location.search).get('tab')
  const valid: TabKey[] = ['today', 'eat', 'progress']
  return valid.includes(tab as TabKey) ? (tab as TabKey) : 'today'
}

function inferMealTypeFromClock(): string {
  const hour = new Date().getHours()
  if (hour >= 5 && hour < 10) return 'breakfast'
  if (hour >= 10 && hour < 15) return 'lunch'
  if (hour >= 15 && hour < 18) return 'snack'
  return 'dinner'
}

export function useApp(): AppContextValue {
  const ctx = useContext(AppContext)
  if (!ctx) throw new Error('useApp must be used within AppProvider')
  return ctx
}

export function AppProvider({ children }: { children: ReactNode }) {
  const [auth, setAuth] = useState<AuthState>({
    status: 'booting',
    message: 'Connecting...',
    headers: {},
  })
  const [activeTab, setActiveTab] = useState<TabKey>(() => resolveInitialTab())
  const [summary, setSummary] = useState<Summary | null>(null)
  const [selectedDate, setSelectedDate] = useState(todayIso())
  const [draft, setDraft] = useState<Draft | null>(null)
  const [logbookRange, setLogbookRange] = useState<LogbookRangeDay[]>([])
  const [bodyGoal, setBodyGoal] = useState<BodyGoal | null>(null)
  const [activities, setActivities] = useState<ActivityAdjustment[]>([])
  const [progressSeries, setProgressSeries] = useState<ProgressSeries | null>(null)
  const [progressRange, setProgressRange] = useState('30d')
  const [eatFeed, setEatFeed] = useState<EatFeed | null>(null)
  const [savedPlaces, setSavedPlaces] = useState<SavedPlace[]>([])
  const [favoriteStores, setFavoriteStores] = useState<FavoriteStore[]>([])
  const [goldenOrders, setGoldenOrders] = useState<GoldenOrder[]>([])
  const [planEvents, setPlanEvents] = useState<PlanEvent[]>([])
  const [mealEvents, setMealEvents] = useState<MealEvent[]>([])
  const [notifications, setNotifications] = useState<Notification[]>([])
  const [onboarding, setOnboarding] = useState<OnboardingState | null>(null)
  const [onboardingForm, setOnboardingForm] = useState<Preferences>(DEFAULT_PREFERENCES)
  const [dayPlan, setDayPlan] = useState<DayPlan | null>(null)
  const [compensation, setCompensation] = useState<Compensation | null>(null)
  const [message, setMessage] = useState('Preparing your day...')
  const [loading, setLoading] = useState(false)
  const { toasts, showToast, dismissToast } = useToast()

  useEffect(() => {
    async function bootstrapAuth() {
      try {
        const config = await api<ClientConfig>('/api/client-config', {})
        try {
          const me = await api<MeResponse>('/api/me', {})
          setAuth({ status: 'ready', message: 'Connected.', headers: {}, me })
          return
        } catch {
          // Fall through to LIFF bootstrap when no app session cookie exists yet.
        }

        if (config.liff_id) {
          await liff.init({ liffId: config.liff_id })
          if (!liff.isLoggedIn()) {
            liff.login({ redirectUri: window.location.href })
            return
          }
          const idToken = liff.getIDToken()
          if (!idToken) throw new Error('LIFF did not return a usable ID token.')
          const me = await api<MeResponse>('/api/me', { 'X-Line-Id-Token': idToken })
          setAuth({ status: 'ready', message: 'LIFF connected.', headers: { 'X-Line-Id-Token': idToken }, me })
          return
        }

        if (config.auth_required) {
          throw new Error('LIFF auth is required, but no LIFF ID is configured.')
        }

        const demoHeaders: Record<string, string> = import.meta.env.DEV
          ? { 'X-Line-User-Id': 'demo-user', 'X-Display-Name': 'Demo User' }
          : {}
        const me = await api<MeResponse>('/api/me', demoHeaders)
        setAuth({ status: 'ready', message: 'Demo mode.', headers: demoHeaders, me })
      } catch (error) {
        setAuth({
          status: 'error',
          message: error instanceof Error ? error.message : 'LIFF auth failed.',
          headers: {},
        })
      }
    }
    void bootstrapAuth()
  }, [])

  const refreshSummary = useCallback(async (targetDate?: string) => {
    if (auth.status !== 'ready') return
    const dateToLoad = targetDate ?? selectedDate
    const data = await api<{ summary: Summary; coach_message: string }>(
      `/api/day-summary?date=${dateToLoad}`,
      auth.headers,
    )
    setSummary(data.summary)
    setMessage(data.coach_message)
    if (dateToLoad !== selectedDate) {
      setSelectedDate(dateToLoad)
    }
  }, [auth, selectedDate])

  const refreshLogbookRange = useCallback(async (targetDate?: string) => {
    if (auth.status !== 'ready') return
    const center = targetDate ?? selectedDate
    const start = addDays(center, -6)
    const data = await api<{ payload: { days: LogbookRangeDay[] } }>(
      `/api/logbook-range?start=${start}&end=${center}`,
      auth.headers,
    )
    setLogbookRange(data.payload.days)
  }, [auth, selectedDate])

  const refreshBodyGoal = useCallback(async () => {
    if (auth.status !== 'ready') return
    const data = await api<{ payload: { body_goal: BodyGoal } }>(
      '/api/body-goal',
      auth.headers,
    )
    setBodyGoal(data.payload.body_goal)
  }, [auth])

  const refreshActivities = useCallback(async (targetDate?: string) => {
    if (auth.status !== 'ready') return
    const dateToLoad = targetDate ?? selectedDate
    const data = await api<{ payload: { activity_adjustments: ActivityAdjustment[] } }>(
      `/api/activity-adjustments?date=${dateToLoad}`,
      auth.headers,
    )
    setActivities(data.payload.activity_adjustments)
  }, [auth, selectedDate])

  const refreshProgressSeries = useCallback(async (range?: string, resolution?: string) => {
    if (auth.status !== 'ready') return
    const nextRange = range ?? progressRange
    const nextResolution = resolution ?? 'day'
    const data = await api<{ payload: { series: ProgressSeries } }>(
      `/api/progress-series?range=${nextRange}&resolution=${nextResolution}`,
      auth.headers,
    )
    setProgressSeries(data.payload.series)
    if (nextRange !== progressRange) {
      setProgressRange(nextRange)
    }
  }, [auth, progressRange])

  const refreshEatFeed = useCallback(async (request?: Partial<EatFeedRequest>) => {
    if (auth.status !== 'ready') return
    const payload: EatFeedRequest = {
      meal_type: request?.meal_type ?? inferMealTypeFromClock(),
      time_context: request?.time_context ?? 'now',
      style_context: request?.style_context ?? '',
      location_mode: request?.location_mode ?? 'none',
      saved_place_id: request?.saved_place_id,
      lat: request?.lat,
      lng: request?.lng,
      query: request?.query,
      selected_chip_id: request?.selected_chip_id,
      explore_mode: request?.explore_mode ?? false,
    }
    const data = await api<{ payload: { eat_feed: EatFeed } }>(
      '/api/eat-feed',
      auth.headers,
      {
        method: 'POST',
        body: JSON.stringify(payload),
      },
    )
    setEatFeed(data.payload.eat_feed)
  }, [auth])

  const refreshPlanEvents = useCallback(async () => {
    if (auth.status !== 'ready') return
    const data = await api<{ payload: { plan_events: PlanEvent[] } }>(
      '/api/plan-events',
      auth.headers,
    )
    setPlanEvents(data.payload.plan_events)
  }, [auth])

  const refreshMealEvents = useCallback(async () => {
    if (auth.status !== 'ready') return
    const data = await api<{ payload: { meal_events: MealEvent[] } }>(
      '/api/meal-events',
      auth.headers,
    )
    setMealEvents(data.payload.meal_events ?? [])
  }, [auth])

  const refreshNotifications = useCallback(async () => {
    if (auth.status !== 'ready') return
    const data = await api<{ payload: { notifications: Notification[] } }>(
      '/api/notifications',
      auth.headers,
    )
    setNotifications(data.payload.notifications ?? [])
  }, [auth])

  const refreshSavedPlaces = useCallback(async () => {
    if (auth.status !== 'ready') return
    const data = await api<{ payload: { saved_places: SavedPlace[] } }>(
      '/api/saved-places',
      auth.headers,
    )
    setSavedPlaces(data.payload.saved_places ?? [])
  }, [auth])

  const refreshFavoriteStores = useCallback(async () => {
    if (auth.status !== 'ready') return
    const data = await api<{ payload: { favorite_stores: FavoriteStore[]; golden_orders: GoldenOrder[] } }>(
      '/api/favorite-stores',
      auth.headers,
    )
    setFavoriteStores(data.payload.favorite_stores ?? [])
    setGoldenOrders(data.payload.golden_orders ?? [])
  }, [auth])

  const markNotificationRead = useCallback(async (notificationId: string) => {
    if (auth.status !== 'ready') return
    await api(`/api/notifications/${notificationId}/read`, auth.headers, { method: 'POST' })
    await refreshNotifications()
  }, [auth, refreshNotifications])

  const createSavedPlace = useCallback(async (draftValue: SavedPlaceDraft) => {
    if (auth.status !== 'ready') return
    await api('/api/saved-places', auth.headers, {
      method: 'POST',
      body: JSON.stringify({
        label: draftValue.label,
        address: draftValue.address,
        provider: 'manual',
        is_default: Boolean(draftValue.is_default),
      }),
    })
    await refreshSavedPlaces()
  }, [auth, refreshSavedPlaces])

  const createFavoriteStore = useCallback(async (draftValue: FavoriteStoreDraft) => {
    if (auth.status !== 'ready') return
    await api('/api/favorite-stores', auth.headers, {
      method: 'POST',
      body: JSON.stringify({
        name: draftValue.name,
        label: draftValue.label || draftValue.name,
        address: draftValue.address || '',
        external_link: draftValue.external_link || '',
      }),
    })
    await refreshFavoriteStores()
    await refreshEatFeed()
  }, [auth, refreshEatFeed, refreshFavoriteStores])

  const createMealEvent = useCallback(async (draftValue: MealEventDraft) => {
    if (auth.status !== 'ready') return
    await api('/api/meal-events', auth.headers, {
      method: 'POST',
      body: JSON.stringify(draftValue),
    })
    await Promise.all([refreshMealEvents(), refreshPlanEvents()])
  }, [auth, refreshMealEvents, refreshPlanEvents])

  useEffect(() => {
    if (auth.status !== 'ready') return
    async function bootstrapData() {
      const [summaryData, onboardingData, notificationsData, bodyGoalData, planEventData, mealEventData, seriesData, savedPlaceData, favoriteStoreData] = await Promise.all([
        api<{ summary: Summary; coach_message: string }>(`/api/day-summary?date=${selectedDate}`, auth.headers),
        api<OnboardingState>('/api/onboarding-state', auth.headers),
        api<{ payload: { notifications: Notification[] } }>('/api/notifications', auth.headers),
        api<{ payload: { body_goal: BodyGoal } }>('/api/body-goal', auth.headers),
        api<{ payload: { plan_events: PlanEvent[] } }>('/api/plan-events', auth.headers),
        api<{ payload: { meal_events: MealEvent[] } }>('/api/meal-events', auth.headers),
        api<{ payload: { series: ProgressSeries } }>(`/api/progress-series?range=${progressRange}`, auth.headers),
        api<{ payload: { saved_places: SavedPlace[] } }>('/api/saved-places', auth.headers),
        api<{ payload: { favorite_stores: FavoriteStore[]; golden_orders: GoldenOrder[] } }>('/api/favorite-stores', auth.headers),
      ])
      setSummary(summaryData.summary)
      setMessage(summaryData.coach_message)
      setOnboarding(onboardingData)
      setOnboardingForm({ ...DEFAULT_PREFERENCES, ...onboardingData.preferences, hard_dislikes: onboardingData.preferences.hard_dislikes ?? [] })
      setNotifications(notificationsData.payload.notifications ?? [])
      setBodyGoal(bodyGoalData.payload.body_goal)
      setPlanEvents(planEventData.payload.plan_events ?? [])
      setMealEvents(mealEventData.payload.meal_events ?? [])
      setProgressSeries(seriesData.payload.series)
      setSavedPlaces(savedPlaceData.payload.saved_places ?? [])
      setFavoriteStores(favoriteStoreData.payload.favorite_stores ?? [])
      setGoldenOrders(favoriteStoreData.payload.golden_orders ?? [])
      await Promise.all([
        refreshLogbookRange(selectedDate),
        refreshActivities(selectedDate),
        refreshEatFeed({ meal_type: inferMealTypeFromClock() }),
      ])
    }
    void bootstrapData()
  }, [auth, progressRange, refreshActivities, refreshEatFeed, refreshLogbookRange, selectedDate])

  const value: AppContextValue = {
    auth,
    activeTab,
    setActiveTab,
    summary,
    setSummary,
    selectedDate,
    setSelectedDate,
    draft,
    setDraft,
    logbookRange,
    bodyGoal,
    activities,
    progressSeries,
    progressRange,
    setProgressRange,
    eatFeed,
    savedPlaces,
    favoriteStores,
    goldenOrders,
    planEvents,
    mealEvents,
    notifications,
    onboarding,
    setOnboarding,
    onboardingForm,
    setOnboardingForm,
    dayPlan,
    setDayPlan,
    compensation,
    setCompensation,
    message,
    setMessage,
    loading,
    setLoading,
    refreshSummary,
    refreshLogbookRange,
    refreshBodyGoal,
    refreshActivities,
    refreshProgressSeries,
    refreshEatFeed,
    refreshPlanEvents,
    refreshMealEvents,
    refreshNotifications,
    refreshSavedPlaces,
    refreshFavoriteStores,
    markNotificationRead,
    createSavedPlace,
    createFavoriteStore,
    createMealEvent,
    showToast,
  }

  return (
    <AppContext.Provider value={value}>
      {children}
      <ToastContainer toasts={toasts} onDismiss={dismissToast} />
    </AppContext.Provider>
  )
}

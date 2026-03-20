export type Draft = {
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
  confirmation_mode?: string
  estimation_confidence?: number
  confirmation_calibration?: number
  primary_uncertainties?: string[]
  clarification_kind?: string | null
  answer_mode?: string | null
  answer_options?: string[]
}

export type MealLogEntry = {
  id: number
  meal_session_id?: string | null
  date: string
  event_at?: string | null
  meal_type: string
  description_raw: string
  kcal_estimate: number
  kcal_low: number
  kcal_high: number
  confidence: number
  source_mode: string
  parsed_items: Array<{ name: string; kcal?: number }>
  uncertainty_note: string
  metadata?: Record<string, unknown>
}

export type RecoveryOverlay = {
  active?: boolean
  adjusted_target_kcal?: number
  active_until?: string
  reason?: string
  overlay_allocations?: {
    today_target?: number
    by_date?: Record<string, number>
  }
  overlay_reason?: string
}

export type Summary = {
  date: string
  target_kcal: number
  base_target_kcal: number
  effective_target_kcal: number
  consumed_kcal: number
  remaining_kcal: number
  today_activity_burn_kcal: number
  meal_subtotals: Record<string, number>
  meal_counts: Record<string, number>
  logs: MealLogEntry[]
  latest_weight?: number | null
  has_today_weight: boolean
  target_weight_kg?: number | null
  delta_to_goal_kg?: number | null
  seven_day_average_weight?: number | null
  fourteen_day_direction: string
  target_adjustment_hint: string
  weekly_target_kcal: number
  weekly_consumed_kcal: number
  weekly_remaining_kcal: number
  weekly_drift_kcal: number
  weekly_drift_status: string
  should_offer_weekly_recovery: boolean
  recovery_overlay?: RecoveryOverlay | null
  pending_async_updates_count: number
}

export type LogbookRangeDay = {
  date: string
  consumed_kcal: number
  target_kcal: number
  meal_count: number
}

export type BodyGoal = {
  target_weight_kg?: number | null
  estimated_tdee_kcal: number
  default_daily_deficit_kcal: number
  base_target_kcal: number
  calibration_confidence: number
  latest_weight?: number | null
  delta_to_goal_kg?: number | null
  last_calibrated_at?: string | null
}

export type ActivityAdjustment = {
  id: number
  date: string
  label: string
  estimated_burn_kcal: number
  duration_minutes?: number | null
  source: string
  raw_input_text: string
  notes: string
}

export type ProgressSeriesPoint = {
  date: string
  value: number
  target?: number | null
}

export type ProgressSeries = {
  range: string
  weight_points: ProgressSeriesPoint[]
  calorie_points: ProgressSeriesPoint[]
  activity_points: ProgressSeriesPoint[]
}

export type FavoriteStore = {
  id: number
  name: string
  label: string
  place_id?: string | null
  address: string
  external_link: string
  usage_count: number
  golden_order_id?: number | null
}

export type GoldenOrder = {
  id: number
  title: string
  store_name: string
  place_id?: string | null
  kcal_low: number
  kcal_high: number
  meal_types: string[]
}

export type SavedPlace = {
  id: number
  label: string
  provider: string
  place_id?: string | null
  lat?: number | null
  lng?: number | null
  address: string
  is_default: boolean
}

export type EatFeedCandidate = {
  candidate_id: string
  title: string
  store_name: string
  meal_types: string[]
  kcal_low: number
  kcal_high: number
  distance_meters?: number | null
  travel_minutes?: number | null
  open_now?: boolean | null
  source_type: string
  reason_factors: string[]
  external_link: string
}

export type EatFeedSection = {
  key: string
  title: string
  items: EatFeedCandidate[]
}

export type SmartChip = {
  id: string
  label: string
  intent_kind: string
  supported_candidate_count: number
}

export type EatFeed = {
  session_id: string
  remaining_kcal: number
  top_pick?: EatFeedCandidate | null
  backup_picks: EatFeedCandidate[]
  exploration_sections: EatFeedSection[]
  location_context_used?: string | null
  smart_chips: SmartChip[]
  hero_reason: string
  more_results_available: boolean
}

export type PlanEvent = {
  id: number
  date: string
  event_type: string
  title: string
  expected_extra_kcal: number
  planning_status: string
  notes_summary: string
}

export type MealEvent = {
  id: number
  plan_event_id?: number | null
  event_date: string
  meal_type: 'breakfast' | 'lunch' | 'dinner' | 'snack'
  title: string
  expected_kcal: number
  status: string
  source: string
  notes: string
}

export type DayPlan = {
  allocations: Record<string, number>
  reason_factors: string[]
}

export type CompensationOption = {
  label: string
  daily_adjustment: number
  days: number
  note: string
}

export type Compensation = {
  options: CompensationOption[]
  reason_factors: string[]
}

export type MeResponse = {
  line_user_id: string
  display_name: string
  daily_calorie_target: number
  provider: string
  now: string
  app_session_token?: string | null
  app_session_expires_at?: string | null
  auth_mode?: string
}

export type ClientConfig = {
  liff_id?: string | null
  auth_required: boolean
}

export type Preferences = {
  breakfast_habit: 'regular' | 'occasional' | 'rare' | 'variable' | 'unknown'
  carb_need: 'high' | 'flexible' | 'low' | 'variable'
  dinner_style: 'light' | 'normal' | 'indulgent' | 'high_protein' | 'variable'
  hard_dislikes: string[]
  compensation_style: 'normal_return' | 'gentle_1d' | 'distributed_2_3d' | 'let_system_decide' | 'gentle'
}

export type OnboardingState = {
  should_show: boolean
  completed: boolean
  skipped: boolean
  version: string
  preferences: Preferences
}

export type Notification = {
  id: string
  type: string
  title: string
  body: string
  status: string
  payload: Record<string, unknown>
  created_at: string
}

export type JournalAddSuggestion = {
  description_raw: string
  kcal_estimate: number
  meal_type: string
}

export type AuthState =
  | { status: 'booting'; message: string; headers: Record<string, string> }
  | { status: 'ready'; message: string; headers: Record<string, string>; me: MeResponse }
  | { status: 'error'; message: string; headers: Record<string, string> }

export type TabKey = 'today' | 'eat' | 'progress'

export const TAB_KEYS: TabKey[] = ['today', 'eat', 'progress']

export const TAB_LABELS: Record<TabKey, string> = {
  today: '日誌',
  eat: '吃什麼',
  progress: '身體與策略',
}

export const TAB_ICONS: Record<TabKey, string> = {
  today: `<svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="4" width="18" height="18" rx="2" ry="2"></rect><line x1="16" y1="2" x2="16" y2="6"></line><line x1="8" y1="2" x2="8" y2="6"></line><line x1="3" y1="10" x2="21" y2="10"></line><path d="M9 16l2 2 4-4"></path></svg>`,
  eat: `<svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M18 8V6a2 2 0 0 0-2-2H4a2 2 0 0 0-2 2v7a3 3 0 0 0 3 3h11a2 2 0 0 0 2-2v-2"></path><path d="M18 10h4v4h-4z"></path><path d="M14 4v16"></path><path d="M10 8h.01"></path></svg>`,
  progress: `<svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 3v18h18"></path><path d="M18 9l-5 5-2-2-4 4"></path></svg>`,
}

export const MEAL_TYPE_LABELS: Record<string, string> = {
  breakfast: '早餐',
  lunch: '午餐',
  dinner: '晚餐',
  snack: '點心',
}

export const DEFAULT_PREFERENCES: Preferences = {
  breakfast_habit: 'variable',
  carb_need: 'flexible',
  dinner_style: 'normal',
  hard_dislikes: [],
  compensation_style: 'let_system_decide',
}

export const HARD_DISLIKE_OPTIONS = ['韓式', '油炸', '含糖飲', '早餐店', '便利商店', '甜點', 'none']

import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import ProgressPage from './ProgressPage'
import type { BodyGoal, ProgressSeries, Summary } from '../types'

const summary: Summary = {
  date: '2026-03-21',
  target_kcal: 1800,
  base_target_kcal: 1800,
  effective_target_kcal: 1800,
  consumed_kcal: 500,
  remaining_kcal: 1300,
  today_activity_burn_kcal: 200,
  meal_subtotals: { breakfast: 300, lunch: 200, dinner: 0, snack: 0 },
  meal_counts: { breakfast: 1, lunch: 1, dinner: 0, snack: 0 },
  logs: [],
  latest_weight: 70,
  has_today_weight: false,
  target_weight_kg: 65,
  delta_to_goal_kg: -5,
  seven_day_average_weight: 70,
  fourteen_day_direction: 'down',
  target_adjustment_hint: '',
  weekly_target_kcal: 12600,
  weekly_consumed_kcal: 2000,
  weekly_remaining_kcal: 10600,
  weekly_drift_kcal: 0,
  weekly_drift_status: 'on_track',
  should_offer_weekly_recovery: false,
  recovery_overlay: null,
  pending_async_updates_count: 0,
}

const bodyGoal: BodyGoal = {
  target_weight_kg: 65,
  estimated_tdee_kcal: 2100,
  default_daily_deficit_kcal: 500,
  base_target_kcal: 1600,
  calibration_confidence: 0.7,
  latest_weight: 70,
  delta_to_goal_kg: -5,
  last_calibrated_at: null,
}

const progressSeries: ProgressSeries = {
  range: '30d',
  weight_points: [],
  calorie_points: [],
  activity_points: [],
}

vi.mock('../AppContext', () => ({
  useApp: () => ({
    auth: {
      status: 'ready',
      message: '',
      headers: {},
      me: {
        line_user_id: 'demo',
        display_name: 'Demo',
        daily_calorie_target: 1800,
        provider: 'demo',
        now: new Date().toISOString(),
        app_session_token: null,
        app_session_expires_at: null,
        auth_mode: 'demo',
      },
    },
    summary,
    bodyGoal,
    activities: [],
    progressSeries,
    progressRange: '30d',
    selectedDate: summary.date,
    refreshActivities: vi.fn().mockResolvedValue(undefined),
    refreshBodyGoal: vi.fn().mockResolvedValue(undefined),
    refreshProgressSeries: vi.fn().mockResolvedValue(undefined),
    refreshSummary: vi.fn().mockResolvedValue(undefined),
    compensation: null,
    setCompensation: vi.fn(),
    mealEvents: [],
    planEvents: [],
    createMealEvent: vi.fn().mockResolvedValue(undefined),
  }),
}))

describe('ProgressPage', () => {
  it('renders body hero and metrics', () => {
    render(<ProgressPage />)

    expect(screen.getByText('目前體重')).toBeInTheDocument()
    expect(screen.getByText('估計 TDEE')).toBeInTheDocument()
    expect(screen.getByText('今天可吃')).toBeInTheDocument()
  })
})

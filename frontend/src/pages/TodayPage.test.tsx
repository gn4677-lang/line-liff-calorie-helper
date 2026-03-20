import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import TodayPage from './TodayPage'
import type { Summary } from '../types'

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
  logs: [
    {
      id: 1,
      meal_session_id: null,
      date: '2026-03-21',
      event_at: '2026-03-21T08:00:00Z',
      meal_type: 'breakfast',
      description_raw: '蛋餅',
      kcal_estimate: 300,
      kcal_low: 280,
      kcal_high: 320,
      confidence: 0.82,
      source_mode: 'manual',
      parsed_items: [],
      uncertainty_note: '',
      metadata: {},
    },
  ],
  latest_weight: 70,
  has_today_weight: false,
  target_weight_kg: 65,
  delta_to_goal_kg: -5,
  seven_day_average_weight: 70,
  fourteen_day_direction: 'down',
  target_adjustment_hint: '保持現況',
  weekly_target_kcal: 12600,
  weekly_consumed_kcal: 2000,
  weekly_remaining_kcal: 10600,
  weekly_drift_kcal: 0,
  weekly_drift_status: 'on_track',
  should_offer_weekly_recovery: false,
  recovery_overlay: null,
  pending_async_updates_count: 0,
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
    selectedDate: summary.date,
    draft: null,
    notifications: [],
    logbookRange: [],
    progressSeries: null,
    refreshSummary: vi.fn().mockResolvedValue(undefined),
    refreshLogbookRange: vi.fn().mockResolvedValue(undefined),
    refreshNotifications: vi.fn().mockResolvedValue(undefined),
    refreshActivities: vi.fn().mockResolvedValue(undefined),
    refreshBodyGoal: vi.fn().mockResolvedValue(undefined),
    refreshProgressSeries: vi.fn().mockResolvedValue(undefined),
    refreshEatFeed: vi.fn().mockResolvedValue(undefined),
    setSummary: vi.fn(),
  }),
}))

describe('TodayPage', () => {
  it('shows meal sections and remaining kcal', () => {
    render(<TodayPage />)

    expect(screen.getByText('今天還剩')).toBeInTheDocument()
    expect(screen.getByText('早餐')).toBeInTheDocument()
    expect(screen.getByText('午餐')).toBeInTheDocument()
    expect(screen.getByText('晚餐')).toBeInTheDocument()
    expect(screen.getByText('點心')).toBeInTheDocument()
    expect(screen.getByText('蛋餅')).toBeInTheDocument()
  })
})

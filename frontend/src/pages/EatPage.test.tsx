import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import EatPage from './EatPage'
import type { EatFeed, Summary } from '../types'

const summary: Summary = {
  date: '2026-03-21',
  target_kcal: 1800,
  base_target_kcal: 1800,
  effective_target_kcal: 1800,
  consumed_kcal: 500,
  remaining_kcal: 1300,
  today_activity_burn_kcal: 0,
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

const eatFeed: EatFeed = {
  session_id: 'session',
  remaining_kcal: 1300,
  top_pick: {
    candidate_id: 'c1',
    title: '雞胸飯',
    store_name: '健康餐',
    meal_types: ['lunch'],
    kcal_low: 420,
    kcal_high: 520,
    distance_meters: 300,
    travel_minutes: 6,
    open_now: true,
    source_type: 'favorite_food',
    reason_factors: ['你最近常接受這個品項'],
    external_link: '',
  },
  backup_picks: [],
  exploration_sections: [],
  location_context_used: null,
  smart_chips: [
    { id: 'high_protein', label: '高蛋白', intent_kind: 'nutrition', supported_candidate_count: 5 },
  ],
  hero_reason: '你最近常接受這個品項',
  more_results_available: false,
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
    eatFeed,
    favoriteStores: [],
    goldenOrders: [],
    savedPlaces: [],
    refreshEatFeed: vi.fn().mockResolvedValue(undefined),
    setMessage: vi.fn(),
  }),
}))

describe('EatPage', () => {
  it('renders top pick and chips', () => {
    render(<EatPage />)

    expect(screen.getByText('今天還剩')).toBeInTheDocument()
    expect(screen.getByText('雞胸飯')).toBeInTheDocument()
    expect(screen.getByText('高蛋白')).toBeInTheDocument()
  })
})

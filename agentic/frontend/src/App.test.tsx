import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import App from './App'

const homePayload = (title: string) => ({
  persona: 'calm_coach_partner',
  title,
  cohort: 'canary',
  core_version: 'agentic',
  highlights: ['highlight a', 'highlight b'],
  opportunities: [],
  metadata: {},
  delivery_preview: {
    importance: 0.72,
    urgency: 0.61,
    why_now: 'Now is a good time.',
    should_send: true,
    delivery_surface: 'line',
    decision_home: title.toLowerCase(),
    delivery_action: 'line_message',
  },
  state: {
    goal_state: {
      primary_goal: 'weight_loss',
      constraints: ['avoid_coriander'],
      strategic_context: ['weekly_drift_watch'],
      priority_signals: ['goal_impact'],
    },
    today_state: {
      remaining_kcal: 1180,
      consumed_kcal: 620,
      open_drafts: 1,
      pending_updates: 1,
      activity_notes: [],
    },
    weekly_state: {
      drift_pct: 0.12,
      overlay_kcal: 180,
      future_events: [{ title: 'Friday team dinner', event_date: '2026-03-27' }],
    },
    recommendation_state: {
      shortlist: [{ key: 'hero', title: 'Light Bowl', reason: 'Fits the goal.', kcal: 520, distance_m: 300 }],
      nearby_items: [{ key: 'nearby', title: 'Nearby Bowl', reason: 'Close and light.', kcal: 540, distance_m: 180 }],
      favorites: ['salad-stop'],
      golden_orders: ['grilled chicken salad'],
      saved_places: ['office'],
    },
    memory_state: {
      facts: [{ key: 'dislike', value: 'coriander', source: 'user_corrected', status: 'stable' }],
    },
    conversation_state: {
      rolling_summary: 'Continuity summary.',
      last_unresolved_topic: 'open today',
      open_threads: [],
    },
    onboarding_state: {
      completed: false,
      skipped: false,
      missing_fields: ['primary_goal'],
      version: 'legacy_bootstrap_v1',
    },
  },
})

describe('Agentic frontend shell', () => {
  const fetchMock = vi.fn<typeof fetch>()

  beforeEach(() => {
    vi.stubGlobal('fetch', fetchMock)
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    fetchMock.mockReset()
  })

  it('boots auth, loads Today by default, and can switch to Eat', async () => {
    fetchMock
      .mockResolvedValueOnce(new Response('unauthorized', { status: 401 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ liff_id: null, auth_required: false, agentic_enabled: true })))
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            user_id: 1,
            line_user_id: 'agentic-demo-user',
            display_name: 'Agentic Demo',
            cohort: 'canary',
            core_version: 'agentic',
            auth_mode: 'header_demo',
          }),
        ),
      )
      .mockResolvedValueOnce(new Response(JSON.stringify(homePayload('Today'))))
      .mockResolvedValueOnce(new Response(JSON.stringify(homePayload('Eat'))))

    render(<App />)

    expect(await screen.findByText('Today Truth')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Eat' }))
    expect(await screen.findByText('Light Bowl')).toBeInTheDocument()
  })

  it('submits a turn from Today page', async () => {
    fetchMock
      .mockResolvedValueOnce(new Response('unauthorized', { status: 401 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ liff_id: null, auth_required: false, agentic_enabled: true })))
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            user_id: 1,
            line_user_id: 'agentic-demo-user',
            display_name: 'Agentic Demo',
            cohort: 'canary',
            core_version: 'agentic',
            auth_mode: 'header_demo',
          }),
        ),
      )
      .mockResolvedValueOnce(new Response(JSON.stringify(homePayload('Today'))))
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            telemetry: { provider_fallback_chain: ['builderspace', 'heuristic'] },
            turn: {
              understanding: { primary_intent: 'recommend_food', subtext: ['guilt'] },
              plan: { decision_home: 'eat', requires_confirmation: false },
              executed_actions: [{ status: 'executed', summary: 'Recommendation generated.', guardrail_policy: 'allow_without_confirmation' }],
              response: {
                message_text: 'Stay conservative tonight.',
                followup_question: 'Open Eat for more options?',
                quick_replies: [],
              },
            },
          }),
        ),
      )

    render(<App />)
    expect(await screen.findByText('Today Truth')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Send To Agent' }))
    expect(await screen.findByText('Stay conservative tonight.')).toBeInTheDocument()
  })

  it('saves structured settings mutations', async () => {
    fetchMock
      .mockResolvedValueOnce(new Response('unauthorized', { status: 401 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ liff_id: null, auth_required: false, agentic_enabled: true })))
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            user_id: 1,
            line_user_id: 'agentic-demo-user',
            display_name: 'Agentic Demo',
            cohort: 'canary',
            core_version: 'agentic',
            auth_mode: 'header_demo',
          }),
        ),
      )
      .mockResolvedValueOnce(new Response(JSON.stringify(homePayload('Today'))))
      .mockResolvedValueOnce(new Response(JSON.stringify(homePayload('Settings'))))
      .mockResolvedValueOnce(new Response(JSON.stringify({ status: 'accepted', guardrail_policy: 'require_confirmation', turn: {} })))

    render(<App />)
    expect(await screen.findByText('Today Truth')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Settings' }))
    expect(await screen.findByText('Settings / Onboarding')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Save Preferences' }))
    await waitFor(() => expect(screen.getByText('preferences saved via structured mutation')).toBeInTheDocument())
  })
})

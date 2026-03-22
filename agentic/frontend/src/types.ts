export type AuthHeaders = Record<string, string>

export type HomeKey = 'today' | 'eat' | 'progress' | 'settings'
export type PrimaryGoal =
  | 'weight_loss'
  | 'maintenance'
  | 'muscle_gain'
  | 'consistency'
  | 'event_preparation'
  | 'symptom_management'

export type ClientConfig = {
  liff_id: string | null
  auth_required: boolean
  agentic_enabled: boolean
}

export type MeResponse = {
  user_id: number
  line_user_id: string | null
  display_name: string
  cohort: string
  core_version: string
  auth_mode: string
}

export type DeliveryPreview = {
  importance: number
  urgency: number
  why_now: string
  should_send: boolean
  suppress_reason?: string | null
  delivery_surface: string
  decision_home: string
  delivery_action: string
}

export type Opportunity = {
  opportunity_type: string
  state_snapshot_ref: string
  importance_factors: Array<{ factor: string; weight: number; reason: string }>
}

export type RecommendationItem = {
  key: string
  title: string
  reason: string
  kcal: number
  distance_m?: number | null
  metadata?: Record<string, unknown>
}

export type HomePayload = {
  persona: string
  title: string
  highlights: string[]
  opportunities: Opportunity[]
  delivery_preview?: DeliveryPreview | null
  cohort: string
  core_version: string
  metadata: Record<string, unknown>
  state: {
    goal_state: {
      primary_goal: PrimaryGoal | null
      constraints: string[]
      strategic_context: string[]
      priority_signals: string[]
    }
    today_state: {
      remaining_kcal: number
      consumed_kcal: number
      open_drafts: number
      pending_updates: number
      activity_notes: string[]
    }
    weekly_state: {
      drift_pct: number
      overlay_kcal: number
      future_events: Array<{ title: string; when?: string; event_date?: string; meal_type?: string }>
    }
    recommendation_state: {
      shortlist: RecommendationItem[]
      nearby_items: RecommendationItem[]
      favorites: string[]
      golden_orders: string[]
      saved_places: string[]
    }
    memory_state: {
      facts: Array<{ key: string; value: string; source: string; status: string }>
    }
    conversation_state: {
      rolling_summary: string
      last_unresolved_topic?: string | null
      open_threads: string[]
    }
    onboarding_state: {
      completed: boolean
      skipped: boolean
      missing_fields: string[]
      version: string
    }
  }
}

export type AgentTurnResult = {
  telemetry: {
    trace_id?: string
    provider_name?: string
    provider_fallback_chain?: string[]
    fallback_reason?: string | null
    deterministic_safe_mode_used?: boolean
  }
  delivery?: DeliveryPreview | null
  turn: {
    response: {
      message_text: string
      followup_question?: string | null
      deep_link?: string | null
      quick_replies: string[]
      tone_profile?: string
    }
    understanding: {
      primary_intent: string
      subtext: string[]
      confidence?: number
    }
    plan: {
      decision_home: string
      requires_confirmation: boolean
    }
    executed_actions: Array<{
      status: string
      summary: string
      guardrail_policy: string
    }>
  }
}

export type MutationResponse = {
  status: string
  guardrail_policy: string
  turn: AgentTurnResult['turn']
}

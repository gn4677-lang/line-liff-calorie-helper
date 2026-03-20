export type AdminSession = {
  token?: string
  label: string
  status: string
  expires_at: string
  last_seen_at?: string
}

export type SummaryCard = {
  key: string
  title: string
  value: number | string
  status: 'healthy' | 'warning' | 'critical' | 'neutral'
  subtitle: string
}

export type TrendPoint = {
  date: string
  value: number
}

export type TaskHealthRow = {
  task_family: string
  sample_size: number
  success_rate: number
  fallback_rate: number
  unknown_case_rate: number
  dissatisfaction_rate: number
}

export type AlertItem = {
  id: string
  severity: string
  status: string
  title: string
  summary: string
  metric_key: string
  task_family?: string | null
  last_seen_at: string
  occurrence_count: number
}

export type ReviewQueueItem = {
  id: number
  queue_type: string
  status: string
  priority: number
  task_family?: string | null
  trace_id?: string | null
  source_table: string
  source_id: string
  title: string
  summary: string
  normalized_label?: string | null
  payload: Record<string, unknown>
  assigned_to: string
  notes: string
  created_at: string
  updated_at: string
  reviewed_at?: string | null
}

export type TraceListItem = {
  trace_id: string
  created_at: string
  task_family: string
  surface: string
  source_mode?: string | null
  input_preview: string
  route_status: string
  provider_name?: string | null
  model_name?: string | null
  route_policy?: string | null
  route_target?: string | null
  llm_cache?: string | null
  latency_ms?: number | null
  has_error: boolean
  has_feedback: boolean
  has_unknown_case: boolean
  outcome_summary: string
}

export type TraceDetailResponse = {
  trace: Record<string, unknown>
  task_runs: Array<Record<string, unknown>>
  uncertainty_events: Array<Record<string, unknown>>
  knowledge_events: Array<Record<string, unknown>>
  error_events: Array<Record<string, unknown>>
  feedback_events: Array<Record<string, unknown>>
  unknown_case_events: Array<Record<string, unknown>>
  outcome_events: Array<Record<string, unknown>>
  related_review_items: ReviewQueueItem[]
  related_alerts: AlertItem[]
}

export type ObservabilityDashboard = {
  refreshed_at: string
  window_hours: number
  trend_days: number
  summary_cards: SummaryCard[]
  task_health: TaskHealthRow[]
  quality_trends: Record<string, TrendPoint[]>
  usage_panels: {
    token_usage_available: boolean
    note: string
    provider_request_counts: Array<{ label: string; count: number }>
    model_request_breakdown: Array<{
      provider_name: string
      model_name: string
      request_count: number
      avg_latency_ms: number
    }>
    route_policy_breakdown: Array<{ label: string; count: number; avg_latency_ms: number }>
    llm_cache_breakdown: Array<{ label: string; count: number; avg_latency_ms: number }>
    route_target_breakdown: Array<{ label: string; count: number; avg_latency_ms: number }>
    llm_path_summary: {
      saved_local_requests: number
      remote_llm_requests: number
      cache_hits: number
    }
  }
  product_panels: {
    recommendation_summary: {
      sessions: number
      accepted_top_pick: number
      accepted_backup_pick: number
      accepted_nearby: number
      corrected_after_acceptance: number
      top_pick_accept_rate: number
      backup_pick_accept_rate: number
      nearby_accept_rate: number
      correction_rate: number
    }
    body_goal_summary: {
      body_goal_users: number
      target_weight_users: number
      target_weight_coverage: number
      activity_adjustment_events: number
      recommendation_profiles: number
      avg_profile_sample_size: number
    }
    proactive_summary: {
      daily_nudges: number
      meal_event_reminders: number
      dinner_picks: number
      meal_events_created: number
    }
    knowledge_summary: {
      version: string
      pack_count: number
      doc_count: number
      structured_item_count: number
      latest_source_mtime: number
      pack_ids: string[]
    }
    recommendation_status_breakdown: Array<{ label: string; count: number }>
    recommendation_source_breakdown: Array<{ label: string; count: number }>
    latest_recommendation_sessions: Array<{
      id: string
      created_at: string
      status: string
      top_pick_title: string
      top_pick_source: string
      accepted_event_type: string
    }>
  }
  memory_panels: {
    scope: string
    summary: {
      total_signals: number
      stable_signals: number
      active_hypotheses: number
      tentative_hypotheses: number
    }
    top_signal_dimensions: Array<{ label: string; count: number }>
    top_signals: Array<Record<string, unknown>>
    top_hypotheses: Array<Record<string, unknown>>
    reporting_bias: Record<string, number>
  }
  operational_panels: {
    error_by_component: Array<Record<string, unknown>>
    top_error_codes: Array<{ label: string; count: number }>
  }
  eval_panels: {
    top_unknown_labels: Array<{ label: string; count: number }>
    top_feedback_labels: Array<{ label: string; count: number }>
  }
  attention_panels: {
    open_alerts: AlertItem[]
    review_queue: Array<Record<string, unknown>>
    critical_errors: Array<Record<string, unknown>>
  }
}

export type AdminApiResponse<T> = {
  coach_message: string
  payload: T
}

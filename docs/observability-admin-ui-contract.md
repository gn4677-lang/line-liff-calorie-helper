# Observability Admin UI Contract

Frontend contract for the internal observability surface. This page is for operators and builders, not end users.

## Purpose

The page should let a human quickly answer:

- what is failing technically
- what is answering badly
- what the memory system is currently learning
- where the next review or research action should go

Do not collapse this into a single generic dashboard. Keep product quality, operational errors, usage, memory, alerts, and review queue as distinct panels.

## Data Source

Primary endpoint:

- `GET /api/observability/dashboard`

Supporting endpoints:

- `GET /api/observability/metrics`
- `GET /api/observability/alerts`
- `POST /api/observability/alerts/evaluate`
- `POST /api/observability/alerts/{alert_id}/status`
- `GET /api/observability/review-queue`
- `POST /api/observability/review-queue/{item_id}/status`
- `GET /api/memory/profile`

## Page Layout

Use a desktop-first admin layout. Mobile support is optional, but the page should still be readable on narrow widths.

Suggested vertical order:

1. top bar
2. summary cards
3. quality trends
4. task health
5. usage
6. memory digest
7. operational errors
8. alerts
9. review queue

## Top Bar

Show:

- page title: `Observability`
- last refresh timestamp
- selected window
- selected trend range
- manual refresh action
- `Evaluate Alerts` action

Recommended filters:

- `window_hours`
  - `24h`
  - `72h`
  - `7d`
  - `14d`
  - `30d`
- `trend_days`
  - `7`
  - `14`
  - `30`

Do not hide the active window from the user.

## Summary Cards

Source:

- `dashboard.summary_cards`

Render as 5 cards:

- `Open Alerts`
- `New Review Items`
- `Nutrition Unknown Rate`
- `Dissatisfaction Rate`
- `Retry Exhausted`

Card requirements:

- show value prominently
- show subtitle
- use color/status styling from:
  - `healthy`
  - `warning`
  - `critical`
  - `neutral`

Cards are informational, but clicking a card may scroll to the matching section.

## Quality Trends

Source:

- `dashboard.quality_trends`

Render as small line or bar charts for:

- `unknown_cases`
- `explicit_negative_feedback`
- `degraded_errors`
- `review_queue_new`

Chart rules:

- same x-axis date scale across all charts
- do not smooth lines
- show exact values on hover
- keep charts visually compact but readable

If a series is empty, still show the chart with zero values rather than hiding the panel.

## Task Health

Source:

- `dashboard.task_health`

Render as a sortable table.

Columns:

- `task_family`
- `sample_size`
- `success_rate`
- `fallback_rate`
- `unknown_case_rate`
- `dissatisfaction_rate`

Default sort:

- highest `dissatisfaction_rate`
- then highest `fallback_rate`

Use percentage formatting for rates.

Important:

- highlight rows with low sample size
- do not over-emphasize tiny samples as if they were critical regressions

## Usage Panel

Source:

- `dashboard.usage_panels`

This panel answers:

- which providers/models are being used most
- where latency concentration is
- whether true token accounting is available yet

Render:

- note/banner if `token_usage_available = false`
- provider request counts
- model request breakdown table

Model request breakdown columns:

- `provider_name`
- `model_name`
- `request_count`
- `avg_latency_ms`

Do not label this as exact cost if token accounting is not available.
Current meaning is usage volume proxy, not billing truth.

## Memory Digest Panel

Source:

- `dashboard.memory_panels`

This panel should feel like a structured report of what the memory system is currently learning.

Render:

- summary stat cards
  - `total_signals`
  - `stable_signals`
  - `active_hypotheses`
  - `tentative_hypotheses`
- top signal dimensions
- top signals
- top hypotheses
- reporting bias snapshot

Top signals columns:

- `pattern_type`
- `dimension`
- `canonical_label`
- `status`
- `evidence_score`
- `counter_evidence_score`

Top hypotheses columns:

- `dimension`
- `label`
- `status`
- `confidence`
- `evidence_count`
- `counter_evidence_count`

Reporting bias should be rendered as compact meters or labeled numeric rows:

- `underreport_score`
- `overreport_score`
- `vagueness_score`
- `missing_detail_score`
- `log_confidence_score`

Important:

- this panel is diagnostic, not user-facing personality UI
- keep wording clinical and engineering-oriented

## Operational Errors Panel

Source:

- `dashboard.operational_panels`

Render two blocks:

- `error_by_component`
- `top_error_codes`

`error_by_component` columns:

- `component`
- `total_count`
- `critical_count`
- `degraded_count`
- `last_seen_at`

`top_error_codes` can be table or ranked list:

- `label`
- `count`

This section should visually separate:

- degraded-but-recovered behavior
- critical failures

## Alerts Panel

Source:

- `dashboard.attention_panels.open_alerts`
- optionally full list from `GET /api/observability/alerts`

Render:

- compact alert list in dashboard
- optional drill-down drawer or modal for full alert history

Columns:

- severity
- title
- summary
- last_seen_at

Actions:

- `Acknowledge`
- `Resolve`

Use:

- `POST /api/observability/alerts/{alert_id}/status`

Do not require a page reload after status changes.

## Review Queue Panel

Source:

- `dashboard.attention_panels.review_queue`
- optionally full list from `GET /api/observability/review-queue`

Render as a work queue.

Columns:

- priority
- queue_type
- title
- summary
- status
- created_at

Actions:

- `Triaged`
- `In Progress`
- `Resolved`
- `Ignored`

Optional fields:

- `assigned_to`
- `notes`

Use:

- `POST /api/observability/review-queue/{item_id}/status`

## Critical Errors Panel

Source:

- `dashboard.attention_panels.critical_errors`

This is separate from the aggregate operational error panel.

Show the newest critical items with:

- `component`
- `operation`
- `error_code`
- `message`
- `created_at`

This panel should be visually urgent but not noisy.

## Empty / Loading / Error States

Loading:

- use skeletons for summary cards and tables
- do not render raw JSON while loading

Empty states:

- if no alerts: show `No open alerts`
- if no review items: show `Review queue is clear`
- if no memory signals: show `No memory digest yet`
- if no usage data: show `No task runs in selected window`

Error state:

- show a retry action
- preserve last successful payload on screen if possible

## Interaction Rules

- refresh should re-request dashboard data without full page reload
- evaluating alerts should call the evaluate endpoint, then refresh dashboard
- alert and review queue status changes should update the local UI optimistically if safe
- filter changes should only change observability state, not mutate any product data

## Non-Negotiable UX Rules

- do not merge error/debug/eval/memory into one chart
- do not present memory digest like a user-facing profile
- do not label provider/model request counts as exact token cost
- do not hide low sample size conditions
- do not bury review queue actions behind multiple clicks

## Recommended Visual Direction

- neutral internal-tool styling
- strong information hierarchy
- table clarity over decorative polish
- use color sparingly:
  - red for critical
  - amber for warning
  - green for healthy
  - gray for neutral

## Future Extensions

Expected future additions:

- exact token / cost accounting
- offline eval run history
- prompt / model regression comparisons
- per-user trace drilldown
- attachment pipeline diagnostics

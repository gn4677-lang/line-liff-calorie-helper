# Surface Interaction Spec v2

Implementation-facing spec for how `LINE chat` and the three LIFF pages divide responsibility.

This is the current answer to:

- what belongs in chat
- what belongs on each page
- how proactive behavior should be placed
- how users should move between surfaces without confusion

## Product Principle

The product should feel like:

- `LINE chat` = the fastest way to capture reality and ask the next useful question
- `今日紀錄` = the operational cockpit for today
- `食物推薦` = the decision tool for the next eating choice
- `體重熱量` = the weekly control panel

The system should not make the user wonder:

- where should I do this?
- why is this being asked here?
- why does this page duplicate what chat already handled?

## Surface Split

### LINE chat

Primary job:

- capture and route
- ask the next necessary question
- handle interruptions
- trigger the right page when a task becomes multi-step
- deliver high-value proactive nudges without becoming a push bot

Best for:

- text / photo / audio / video meal logging
- one-turn corrections
- quick remaining-calorie checks
- quick nutrition questions
- future event probes
- weekly drift probes
- apply / dismiss async updates

Should not become:

- a dense dashboard
- a long planning workspace
- a recommendation browser

### 今日紀錄

Primary question:

- what happened today, what is unresolved, and what should I do next?

This is the daily execution cockpit.

Best for:

- active draft handling
- confirmation / clarification
- reviewing today's logs
- seeing pending async updates
- handling today-specific recovery overlay

### 食物推薦

Primary question:

- what can I eat right now, and where should I get it?

This is the immediate decision page.

Best for:

- recommendations by calorie context
- nearby search
- destination-aware search
- favorite stores and golden orders
- deciding between safe / convenient / indulgent / high-protein options

### 體重熱量

Primary question:

- am I generally on track this week, and is any course correction worth doing?

This is the weekly control and review page.

Best for:

- weight trend
- 7-day and 14-day view
- weekly drift
- overlay state
- plan events
- soft course-correction decisions

## Cross-Surface Rule

Every user job should have one clear home.

### Chat is the home for

- input capture
- low-friction logging
- short clarifications
- one-shot corrections
- ask-first nudges
- short-lived decisions

### 今日紀錄 is the home for

- today's truth state
- active draft resolution
- meal timeline
- same-day async updates
- today's recovery overlay

### 食物推薦 is the home for

- recommendation browsing
- location choice
- nearby restaurant discovery
- safe orders
- decision comparison

### 體重熱量 is the home for

- trend and drift
- weekly context
- whether a recovery action is worth doing
- progress explanation

## Conversation Design

Conversation should do four things well:

1. capture food with minimal friction
2. ask one useful follow-up when necessary
3. detect when the task belongs on a page
4. surface proactive next steps without becoming nagging

### Visible chat modes

The backend can keep the 10-way router, but the user-facing behavior should collapse into these modes:

- logging a meal
- correcting a recent meal
- asking what to eat
- asking about progress / calories / weight
- asking nutrition or food knowledge
- handling async or proactive follow-ups

The user should not feel the internal router.

### Meal logging

Default flow:

- user sends text / image / audio / video
- system estimates quickly
- if confidence is high, auto-record and show result
- if not, ask only one high-impact question
- if budget is exhausted, stop gracefully and say it is using a generic portion estimate

Chat reply should always feel like:

- capture first
- question second

Not:

- interrogation first

### Correction

When the user says things like:

- `飯只有半碗`
- `飲料其實沒喝`
- `那餐是分著吃`

Chat should:

- create a correction preview
- show old kcal vs new kcal
- ask whether to overwrite

This belongs in chat first because it is usually a continuation of the meal-capture thread.

### Recommendation handoff

If the user asks:

- `現在可以吃什麼`
- `附近有什麼不容易爆`
- `等等去信義區吃什麼`

Chat should:

- branch the location context
- give a fast shortlist if the answer is easy
- suggest opening `食物推薦` when deeper browsing is needed

### Future event / weekly drift

When chat detects:

- future feast
- buffet
- social meal
- weekly drift clearly over target

It should use `ask-first`:

- `要不要我先幫你排一下前後幾天怎麼吃？`
- `這週目前有點超標，要不要我幫你拉回來一點？`

The actual multi-option planning should live in LIFF, not in a long chat thread.

### Async updates

When a background job finishes:

- chat may notify once
- the decision itself should stay lightweight:
  - `套用更新`
  - `先維持原本`

If the update needs more context, opening `今日紀錄` is the fallback.

## Quick Reply Design

Quick replies are dynamic mini-controllers.

Use them for:

- clarification answer chips
- portion comparison
- location branching
- future-event ask-first
- weekly recovery ask-first
- apply / dismiss async update
- fallback disambiguation

Do not use them as:

- a persistent navigation system
- a replacement for the three pages

## Page Design

## 1. 今日紀錄

### Page role

This page is not a generic dashboard.

It answers:

- what has happened today
- what is still unresolved
- what should I do next

### Content order

#### A. Today status strip

Always visible at top:

- consumed kcal
- remaining kcal
- target kcal
- weekly drift micro-summary
- overlay badge when active

This strip should answer the state of the day at a glance.

#### B. Active draft card

If a draft exists, this becomes the highest-priority card.

Must show:

- estimated kcal
- range
- primary uncertainties
- current confirmation mode
- follow-up question if any
- answer chips when available
- confirm / force confirm / correction actions

If no draft exists, replace with a low-friction entry card:

- text input
- quick add
- upload entry points
- recent anchor suggestions

#### C. Pending async updates card

This should sit near the top when present.

Must show:

- how many updates are waiting
- original kcal vs suggested kcal
- reason
- apply / dismiss

This belongs here because async updates are usually about today's logs.

#### D. Meal timeline

Today-only list of logs in chronological order.

Each row should show:

- meal type
- short description
- kcal
- uncertainty badge when relevant
- edit / revise action
- async update applied badge if relevant

This is the main audit trail for the day.

#### E. Next step card

This is a proactive card.

Show only one main suggested action at a time, for example:

- finish an unresolved draft
- browse nearby dinner options
- accept or dismiss a suggested update
- soften today's intake because overlay is active

This is where proactive behavior should feel like helpful sequencing, not nagging.

#### F. Recovery overlay card

Visible only when active.

Must show:

- overlay active until when
- today's adjusted budget
- why the overlay exists
- stop overlay action if needed

### 今日紀錄 should not show

- dense nearby browsing
- all recommendation groups
- long-term trend charts

## 2. 食物推薦

### Page role

This page is the decision workspace for the next eating choice.

It answers:

- what can I eat now
- what can I eat where I am going
- what is safest / easiest / most satisfying under today's context

### Content order

#### A. Context chooser

This is the top controller for the whole page.

Must let the user choose:

- now / later
- current area / destination / saved place / manual input
- meal type
- optional style bias:
  - safe
  - convenient
  - satisfying
  - high-protein

This replaces hidden assumptions with explicit context.

#### B. Fast recommendation rail

Immediate shortlist based on:

- remaining kcal
- meal type
- hard dislikes
- known golden orders
- nearby context if available

These are the first 3-5 things the user can plausibly choose.

#### C. Nearby module

This is the nearby-search launcher and results surface.

Must support:

- current area
- destination
- home area
- office area
- manual place search

Must show:

- heuristic shortlist immediately
- richer shortlist when async job finishes
- distance / open-now / kcal range
- reason factors
- external link

#### D. Favorite stores and golden orders

This should be a first-class block, not a buried settings feature.

Must show:

- favorite stores
- stable store-order pairs
- recently successful orders

This is one of the highest-value proactive memory outputs.

#### E. Recommendation groups

Grouped recommendations can still exist, but should be secondary to the fast shortlist.

Suggested groups:

- 最穩
- 最方便
- 想吃爽一點
- 高蛋白優先
- 聚餐前適合
- 爆卡後適合

Each item must show:

- kcal range
- reason factors
- whether it is favorite / golden / nearby / memory-based

#### F. Planning and compensation preview

This should not take over the page, but it should be available here because users often decide food and compensation together.

Must show:

- today's meal budget split
- compensation options when relevant
- overlay-aware planning state

### 食物推薦 should not show

- full meal-logging timeline
- active clarification thread
- detailed 14-day weight analysis

## 3. 體重熱量

### Page role

This page is the weekly and trend view.

It answers:

- am I generally on track
- is this week manageable
- should I change anything

### Content order

#### A. Weekly status hero

Must show:

- latest weight
- 7-day average
- 14-day direction
- weekly target
- weekly consumed
- weekly drift
- status label:
  - on track
  - slightly over
  - meaningfully over
  - meaningfully under

#### B. Trend card

Show:

- weight trend
- recent caloric adherence trend
- overlay effect if active

This should give context, not just raw numbers.

#### C. Weekly recovery decision card

Only show if relevant.

Must ask:

- should I leave this alone, or make a small recovery plan?

Actions:

- 回到正常
- 小幅回收 1 天
- 分 2-3 天攤平

This is where weekly proactive logic belongs by default, not chat first.

#### D. Plan events card

Show upcoming known events:

- tomorrow dinner out
- weekend feast
- travel / buffet / social meal

Each event can have:

- plan status
- whether surrounding days are already arranged
- CTA to plan

#### E. Logging quality / confidence card

This should feel gentle and internal, not scolding.

Show soft signals such as:

- recent correction frequency
- how complete recent logs are
- whether the system is currently using stricter confirmation

This helps explain why the assistant may be asking slightly more questions.

### 體重熱量 should not show

- nearby store browsing
- multi-step meal clarification UI
- large recommendation catalogue

## Proactivity Placement

The same proactive behavior should not appear everywhere.

### Put it in chat when

- it is time-sensitive
- it needs a quick yes/no
- it is a continuation of the last message
- it is an interrupt

Examples:

- background research found a better estimate
- a future feast was just mentioned
- the current intake still needs one high-impact clarification

### Put it in 今日紀錄 when

- it concerns today's truth state
- it concerns unresolved logging
- it concerns today's async updates

Examples:

- active draft
- pending suggested update
- today's overlay
- today's missing dinner

### Put it in 食物推薦 when

- it concerns a choice between eating options
- it needs location context
- it needs store memory

Examples:

- nearby search
- saved-place search
- favorite stores
- golden orders

### Put it in 體重熱量 when

- it concerns weekly control
- it concerns trend understanding
- it concerns future event load and recovery worthiness

Examples:

- weekly drift over target
- whether to offer recovery
- tomorrow event planning reminder

## Notification Policy

Notifications should be rare and high-value.

Allowed in v1:

- async research completed
- unfinished draft left hanging
- tomorrow has a stored event
- weekly drift clearly over target and there has been no response yet

For every notification, there must be one next action only.

Do not send notifications for:

- every recommendation refresh
- every small drift change
- routine status updates

## Navigation Rules

### From chat to page

Chat should open LIFF when:

- recommendation becomes location-heavy
- planning becomes multi-step
- async update has rich context
- the user needs to browse options

### From page to chat

Pages should push the user back to chat only when:

- they want to continue a conversational correction
- they need to share location through LINE
- they want the fastest capture route

### Rich Menu role

Rich Menu should remain stable:

- `今日紀錄`
- `體重熱量`
- `食物推薦`

This gives orientation.

Quick reply gives temporary contextual choices.

## Exact UI Priority

If antigravity is deciding what to perfect first, the priority order should be:

1. `今日紀錄`
2. `食物推薦`
3. `體重熱量`
4. chat quick reply polish

Reason:

- today logging and correction is the product core
- recommendation is the next major value surface
- progress matters, but it is less frequent than the other two

## Implementation Notes

Frontend should treat these as distinct surfaces with distinct state loads:

- `今日紀錄`
  - summary
  - active draft
  - today logs
  - pending async updates
  - overlay
- `食物推薦`
  - recommendations
  - location context
  - nearby job state
  - saved places
  - favorite stores
  - golden orders
- `體重熱量`
  - weekly summary
  - trend data
  - overlay state
  - plan events
  - recovery CTA

If the UI starts collapsing these into one screen, the product will become harder to use, not easier.

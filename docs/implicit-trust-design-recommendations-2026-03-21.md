# Implicit Trust Design — Codex Recommendations

Date: 2026-03-21

## Context

After reviewing the product spec, current codebase, and Build Order v3, the human operator raised a valid concern:

> Explicit "was this helpful?" feedback questions degrade UX. Real users don't want to answer extra questions.

This document replaces the earlier "add explicit feedback prompts" recommendation with a corrected approach.

---

## Core Principle

**Trust is built through behavior change, not questions.**

Users don't trust an app because it asked "was this right?". They trust it because it silently improved after they corrected it.

The goal: make the system learn without asking, and make the learning visible without being intrusive.

---

## What NOT to Do

Do NOT add explicit feedback prompts such as:
- "這個估算是偏高了？偏低了？"
- "這個建議你想吃嗎？"
- "這個建議有幫助嗎？"

These interrupt the user's flow and feel like survey questions, not product features.

---

## What TO Do Instead

### 1. Corrections Should Be Self-Announcing

When a user corrects the system, do NOT just apply the correction silently.

**Current behavior (likely):**
- User says "不是 650，是 800" → system updates silently → nothing shown

**Better behavior:**
- User says "不是 650，是 800" → system updates → shows "好，已更新為 800，以後會用這個值"

This is a one-line confirmation, not a question. It shows the system listened.

**Implementation direction:**
- In the LINE chat confirmation flow, after a correction is applied, send a short confirmation message that names what changed
- Keep it to one line. "好，已更新" is enough.
- Do NOT ask follow-up questions after this.

### 2. Show System Learning in UI Pages

The UI pages (Today, Eat, Progress) should surface what the system has remembered, without requiring the user to ask.

**Today page:**
- When showing a food entry that was corrected before, show a subtle indicator: "上次你說是 800 kcal"
- When auto-using a user's corrected value, briefly note "用你上次的修正值"

**Eat page:**
- Golden options should be labeled as "你的黃金選項" not just sorted differently
- When showing a recommendation influenced by past choices, show why: "你上週在這附近選過"

**Progress page:**
- When showing weekly coaching, frame it as "根據你這週的記錄" not as a generic statement
- If the system adjusted something based on past corrections, show the adjustment: "已根據你的修正更新估算"

### 3. Memory Updates Should Be Immediate and Durable

The system should update immediately on correction, not wait for a background job.

**Check:**
- When `feedback_event` with type `correction_after_answer` is recorded, does it immediately update the relevant `foods` or `preferences` record?
- Does the update persist across sessions, or only apply to the current draft?

The correction loop should be: user corrects → system updates → next similar case uses new value → user notices the improvement.

### 4. Recommendation Outcome Tracking Should Influence Future Results

Currently the system records `recommendation_clicked` / `recommendation_ignored`. 

**Verify and strengthen:**
- Ignored recommendations should lower that candidate's score for similar contexts
- Clicked recommendations should raise similar candidates
- The influence should be visible within 1-2 interactions, not after weeks of data

**UI visibility:**
- When a recommendation appears that was influenced by past behavior, show a brief reason: "根據你上次在這附近選的"

### 5. Reporting Bias Profile Should Inform Estimation Without Announcing It

The `reporting_bias` profile exists. Verify it is being used during estimation.

**Do:**
- When `underreport_score` is high, the system should gently auto-adjust estimates upward
- When `vagueness_score` is high, the system should ask one more clarification question

**Don't:**
- Announce "因為你之前習慣少報，所以我們自動加了 10%"
- The bias adjustment should be invisible to the user

---

## Relationship to Build Order v3

These recommendations complement the three sprints without conflicting:

| Sprint | Focus | Trust alignment |
|--------|-------|-----------------|
| Sprint 1 | Chat meal capture | Corrections become self-announcing in the chat flow |
| Sprint 2 | Eat decision loop | Recommendations show "根據你上次..." reasoning |
| Sprint 3 | Weekly coaching | Coaching frames use "根據你這週的記錄" |

The observability contracts (`StructuredIntentRoute`, `ClarificationDecision`, etc.) requested in Build Order v3 are still necessary infrastructure. They enable the trust improvements by making the system's reasoning visible in traces.

---

## Priority for Implementation

1. **Immediate**: Make corrections self-announcing (one confirmation message after apply)
2. **Soon**: Add "根據你上次..." context to Eat page recommendations
3. **Soon**: Verify reporting_bias is actually influencing estimation silently
4. **During Sprint 2**: Add context reasons to recommendation cards
5. **During Sprint 3**: Frame coaching as "根據你這週..." not generic advice

---

## Files Likely to Touch

- `backend/app/services/intake.py` or `confirmation.py` — correction flow + confirmation message
- `backend/app/services/recommendations.py` — add context reasons to recommendation output
- `backend/app/services/memory.py` or memory packet assembly — ensure corrections update immediately
- `frontend/src/pages/EatPage.tsx` — show "你的黃金選項" labels and "根據你上次..." context
- `frontend/src/pages/TodayPage.tsx` — show corrected-value notes
- `frontend/src/pages/ProgressPage.tsx` — frame coaching with contextual basis

---

## Success Signal

The right success signal is NOT user-reported satisfaction.

The right signal is:
- User corrects once → same mistake doesn't happen again within 2 interactions
- User ignores a recommendation → similar recommendation doesn't appear again without a different context
- User sees a recommendation → they can guess why it was shown (because the UI shows the reason)

If the user can say "它記得我说过的话"，the trust design is working.

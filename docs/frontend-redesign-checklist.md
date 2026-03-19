# Frontend Redesign Checklist

Use this as the delivery checklist for any major LIFF frontend redesign.

## Product Fit

- [ ] Preserve the 3-page structure: `Today`, `Progress`, `Eat`
- [ ] Keep `Today` as the primary daily cockpit
- [ ] Make remaining calories the strongest visual anchor
- [ ] Keep recommendation count intentionally small and decision-oriented
- [ ] Keep the app feeling like a personal fat-loss operating system, not a generic calorie tracker

## LIFF and Auth

- [ ] Preserve `GET /api/client-config` bootstrap
- [ ] Preserve LIFF SDK initialization
- [ ] Preserve LIFF login redirect when user is not logged in
- [ ] Preserve sending `X-Line-Id-Token` to backend
- [ ] Do not move secrets into frontend code
- [ ] Ensure unauthenticated states fail clearly

## Today Page

- [ ] Meal logging is possible in under 30 seconds
- [ ] Intake input is easy to find immediately
- [ ] Draft state is clearly separated from confirmed logs
- [ ] Clarification step feels compact, not like a form wizard
- [ ] Confirm and force confirm actions are visible and understandable
- [ ] Current day log list is easy to scan
- [ ] Coach message is visible but not visually dominant over core actions

## Progress Page

- [ ] Latest weight or weight entry is visible immediately
- [ ] 7-day average is understandable at a glance
- [ ] 14-day direction is understandable at a glance
- [ ] Target adjustment hint is readable and calm
- [ ] Single-day noise does not visually overpower trend information

## Eat Page

- [ ] Recommendation groups are visually distinct
- [ ] Each recommendation communicates why it is suitable
- [ ] Planning and compensation controls are clear
- [ ] Recommendation UI helps decide, not just browse

## Mobile and LIFF Usability

- [ ] Optimized for common mobile widths inside LINE
- [ ] No critical CTA is pushed below confusing scroll depth
- [ ] Tap targets are comfortable on mobile
- [ ] Typographic hierarchy survives small screens
- [ ] Layout still works in standalone browser outside LINE

## Visual Direction

- [ ] Avoid generic dashboard styling
- [ ] Avoid default purple AI aesthetic
- [ ] Use a clear visual system with intentional spacing and hierarchy
- [ ] Empty states, loading states, and errors feel designed, not leftover
- [ ] Motion is used sparingly and meaningfully

## Engineering Boundaries

- [ ] Do not casually rename backend response fields
- [ ] Do not break existing endpoint paths
- [ ] Keep component structure maintainable
- [ ] Keep frontend state flow understandable
- [ ] Build still passes with `npm run build`

# Antigravity Reviewer Checklist

Use this after antigravity returns a frontend revision.

## Product Alignment

- [ ] Does the UI still clearly answer the three core questions?
- [ ] `Progress`: am I on track?
- [ ] `Today`: what did I eat and what should I do next?
- [ ] `Eat`: what can I eat right now?

## Structural Fit

- [ ] Is the 3-page structure preserved?
- [ ] Is `Today` still the center of gravity?
- [ ] Are recommendation and planning surfaces separated cleanly?

## Interaction Quality

- [ ] Is meal logging fast without hidden friction?
- [ ] Is clarification compact and easy to understand?
- [ ] Is draft vs confirmed state obvious?
- [ ] Are key actions visible without hunting?

## Mobile Fit

- [ ] Does it feel correct inside LINE LIFF?
- [ ] Does it avoid desktop-first spacing and card density?
- [ ] Are the most important numbers and actions above the fold on common mobile screens?

## Design Quality

- [ ] Does it avoid generic SaaS / admin styling?
- [ ] Does it have a real visual direction?
- [ ] Is the hierarchy strong around remaining calories and current action?
- [ ] Do recommendation groups feel meaningfully different?

## Technical Safety

- [ ] Is LIFF auth flow still intact?
- [ ] Are backend endpoint names unchanged unless explicitly discussed?
- [ ] Are request and response fields still compatible with current backend?
- [ ] Does the code avoid embedding tokens or secrets?
- [ ] Does `npm run build` still pass?

## Release Readiness

- [ ] Could you hand this UI to a real user without having to explain where to start?
- [ ] Does the first screen make the next action obvious?
- [ ] Does the app feel like a usable product, not a prototype shell?

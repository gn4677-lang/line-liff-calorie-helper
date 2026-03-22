# Phase C Dual-Deploy Analysis

Date: 2026-03-21

## Recommendation

Do not make Phase C a pre-launch blocker.

For the current product shape, the better path is:

1. launch on the existing same-origin topology
2. keep `web` and `worker` separated operationally
3. revisit dual deploy only if concrete operational triggers appear

BuilderSpace does not block a future dual deploy. All BuilderSpace calls already belong on the backend, so the real cost of Phase C is not the LLM provider. The real cost is auth/session, CORS/CSRF, deploy coordination, and observability complexity.

## Current Baseline

The app is currently optimized for same-origin:

- FastAPI serves `frontend/dist`
- `VITE_API_BASE_URL=''`
- LIFF, API, and session assumptions all align with one public origin
- runtime roles are already split into `APP_RUNTIME_ROLE=web` and `APP_RUNTIME_ROLE=worker`
- webhook ingress is already decoupled from request-time processing

This means the control plane is now production-shaped, even though deployment is still single-origin.

## What Phase C Would Actually Change

Phase C is not "more production". It is a different topology.

It would mean:

- frontend deployed separately as static assets / CDN
- API deployed separately
- worker deployed separately
- LIFF app points at frontend origin, not API origin
- auth/session no longer rely on same-origin defaults
- CORS, CSRF, cookies, and bootstrap/session refresh all become explicit

## Benefits If You Do It

### 1. Better deployment isolation

- Frontend deploys no longer require touching API containers.
- API hotfixes no longer require redeploying frontend assets.
- Worker rollouts stay isolated from UI releases.

### 2. Better scaling independence

- CDN/frontends can scale on read-heavy traffic.
- API can scale on request volume.
- worker can scale on queue depth.

This matters more when webhook volume, LIFF browsing, and background refinement stop moving together.

### 3. Cleaner future multi-surface expansion

If you later add:

- web dashboard beyond LIFF
- separate admin domain
- mobile app client
- partner/internal tools

then separate frontend/API deploys become more valuable.

### 4. Better cache and edge strategy

- frontend can be aggressively cached and distributed
- API can keep shorter-lived, authenticated behavior
- release cadence is cleaner for static assets

## Costs If You Do It

### 1. Auth/session complexity rises immediately

Today same-origin keeps LIFF bootstrap simpler.

Dual deploy means you must choose one of:

- cross-site cookie strategy
- signed header/session token bootstrap
- token refresh flow owned by frontend

That adds:

- `SameSite=None; Secure` cookie requirements
- stricter CSRF design
- origin validation complexity
- more failure modes on mobile in-app browsers

For LIFF specifically, this is not a cosmetic cost. It is one of the main risk multipliers.

### 2. CORS and operator setup become stricter

You now need exact alignment across:

- frontend origin
- API origin
- LIFF URL
- LINE webhook URL
- cookie domain
- CORS allowlist

The app is currently not missing features because of same-origin. It would only gain operational separation, but at the price of a more fragile configuration matrix.

### 3. Debugging gets harder

Same-origin lets you inspect one deploy artifact.

Dual deploy introduces new failure classes:

- frontend points at wrong API
- stale CDN assets after API change
- cookie not sent cross-site
- preflight/CORS mismatch
- staging/prod cross-wire

For a LINE + LIFF + async-worker system, these are real sources of launch pain.

### 4. Your current team constraints do not yet demand it

Nothing in the current codebase suggests that same-origin is the bottleneck today.

The bigger remaining work is still:

- recommendation policy eval depth
- operational key rotation / secret source of truth
- real staging/canary discipline
- production observability usage

Those all improve launch readiness more than topology splitting does.

## Comparison

| Dimension | Stay Same-Origin Now | Move To Dual Deploy Now |
| --- | --- | --- |
| Launch risk | Lower | Higher |
| LIFF auth complexity | Lower | Higher |
| CORS/CSRF complexity | Lower | Higher |
| Operational isolation | Moderate | Higher |
| Frontend release independence | Moderate | Higher |
| Worker/API/frontend scaling independence | Moderate | Higher |
| Speed to public launch | Faster | Slower |
| Short-term engineering ROI | Better | Worse |
| Long-term platform flexibility | Moderate | Better |

## When Phase C Becomes Worth Doing

Treat dual deploy as justified when at least one of these becomes true:

- frontend release cadence diverges from API cadence enough to cause friction
- LIFF/web frontend traffic becomes large enough that CDN optimization matters materially
- worker scale and API scale need different operational policies
- you add a second client surface that shares the same API
- you want stricter boundary separation between public frontend and private/admin APIs
- same-origin auth assumptions are already being replaced by explicit token/session flows

If none of those are true yet, Phase C is mostly architecture churn.

## Recommended Path

### Near term

- keep same-origin for public launch
- keep `web` / `worker` split as the main operational boundary
- keep BuilderSpace server-side only
- keep Phase C documented but deferred

### Before revisiting Phase C

Finish these first:

1. confirm public/staging URLs and secret-manager source of truth
2. rotate exposed credentials
3. use the new webhook/worker observability in real traffic
4. expand eval coverage for recommendation policy and routing quality

### If you later activate Phase C

Do it as an auth-and-control-plane project, not as a frontend hosting project.

The order should be:

1. define session strategy
2. define CORS/CSRF/origin policy
3. define frontend bootstrap and refresh behavior
4. then split deployment artifacts

## Final Judgment

Phase C is useful, but not currently necessary.

For this app today:

- same-origin is the better production choice
- separate `web` and `worker` already give most of the operational win you need
- dual deploy should be treated as a later optimization for scale, release independence, and multi-surface growth

If you force Phase C now, you will mostly buy configuration and auth risk, not user-visible product quality.

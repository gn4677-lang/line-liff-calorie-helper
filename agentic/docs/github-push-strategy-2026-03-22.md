# GitHub Push Strategy (2026-03-22)

This note explains how to push the repo while keeping the legacy app and the agentic rewrite understandable.

## Recommended Shape

Keep the repo readable by using:

- one visible legacy tree at repo root
- one visible new tree under `agentic/`
- one explicit migration note
- one explicit branch/tag history marker

## What To Push

Push all of these:

- the current repository contents, including both:
  - `backend/` and `frontend/`
  - `agentic/`
- branch:
  - `codex/agentic-rewrite`
- tag:
  - `pre-agentic-rewrite-2026-03-21`

## How Future Readers Should Understand The Repo

The intended interpretation is:

- `backend/` + `frontend/`
  - legacy app
  - rollback/reference path
- `agentic/`
  - new rewrite mainline
  - future product direction

Do not present the root app as the future architecture.

## Recommended GitHub Workflow

Short term:

1. Keep `main` stable and readable
2. Keep `codex/agentic-rewrite` as the active rewrite branch
3. Make it obvious in docs that `agentic/` is the new mainline

During canary:

1. Continue development in `codex/agentic-rewrite`
2. Keep legacy root app intact for rollback/reference
3. Avoid mixing unrelated legacy cleanup with agentic architecture work

After cutover:

1. Decide whether to merge the agentic branch into `main`
2. Only after rollout is stable, consider simplifying the repo structure
3. If desired, move the legacy root app into an archive/legacy location in a later cleanup pass

## Why This Is Better Than Hiding One Version

This approach keeps:

- rollback clarity
- implementation history
- operator confidence
- future debugging context

It is easier to understand than:

- deleting the old app too early
- force-merging both architectures into the same folders
- relying only on git history without clear workspace structure


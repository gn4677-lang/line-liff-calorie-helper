# Repo Notes

## Testing on Windows

- The backend test suite uses SQLite files under pytest temp directories.
- `backend/tests/conftest.py` now disposes the SQLAlchemy engine in fixture teardown to avoid Windows file locks on `test.db`.
- Preferred backend test command:

```powershell
& 'C:\Users\exsaf\AppData\Local\Programs\Python\Python312\python.exe' -m pytest backend\tests -q --basetemp backend\.pytest_tmp
```

- `pytest.ini` pins `cache_dir` to `backend/.pytest_cache`, so agents should let pytest use the repo config instead of writing cache data to the workspace root.
- If pytest falls back to `C:\Users\exsaf\AppData\Local\Temp\pytest-of-exsaf`, Windows permission errors can cascade through most fixtures. Prefer commands that pass `--basetemp` explicitly or use `.\scripts\run_agentic_checks.ps1`, which now does this in both default and `-Fast` modes.

- If a prior interrupted run leaves temp files behind, rerun with a fresh temp directory instead of reusing the same one:

```powershell
$temp = 'backend\.pytest_tmp_run_' + [DateTime]::UtcNow.ToString('yyyyMMddHHmmssfff')
& 'C:\Users\exsaf\AppData\Local\Programs\Python\Python312\python.exe' -m pytest backend\tests -q --basetemp $temp
```

- If a stale permission issue still triggers `PytestCacheWarning`, treat it as non-fatal and rerun with a fresh `--basetemp` before assuming the suite is broken.

## Agentic / LLM Change Policy

Default backend tests are not sufficient for agentic changes.

If a change touches any of the following, treat it as an `agentic change` and run the full checklist below:

- provider contracts or prompt payloads
- `llm_support.py`
- prompt assembly
- memory / planning / recommendation packets
- recommendation reranking
- confirmation gates driven by model output
- tool selection or tool schemas
- background jobs that call providers
- any route that can hit an LLM path directly or indirectly
- observability fields used to understand LLM behavior

### Required inspection

When handling an agentic change, do not stop at "the schema exists" or "the helper was added".
You must trace the full path end-to-end:

1. entrypoint
2. service layer
3. provider call
4. prompt / structured payload
5. fallback path
6. background / async path
7. observability path
8. test coverage

In this repo, that means checking both synchronous routes and deferred jobs. A packet that is only returned by `/api/memory/profile` or only stored in metadata is **not** considered "wired".

### Required test standard

For agentic changes, add or update tests that verify actual behavior, not just helper existence.

Minimum expectations:

- Test the LLM path with provider methods monkeypatched.
- Test the fallback path when no token / no remote LLM is available.
- Verify the outcome state, not only the final text.
- For routing or tool-use behavior, verify the selected action, ordering, persisted state, or gate decision.
- For review / judge style logic, verify how model output changes the final decision.
- For trajectory-like flows, avoid overfitting to one exact intermediate trace if multiple valid paths exist; assert the required outcome and critical constraints instead.

If you change an agentic surface in this repo, run at least:

```powershell
$temp = 'backend\.pytest_tmp_run_' + [DateTime]::UtcNow.ToString('yyyyMMddHHmmssfff')
& 'C:\Users\exsaf\AppData\Local\Programs\Python\Python312\python.exe' -m pytest `
  backend\tests\test_llm_integration_wiring.py `
  backend\tests\test_knowledge_packets.py `
  backend\tests\test_confirmation_and_qa.py `
  backend\tests\test_summary_and_recommendations.py `
  backend\tests\test_video_intake.py `
  backend\tests\test_observability_console.py `
  -q --basetemp $temp
```

If the change is broad, run the full backend suite:

```powershell
$temp = 'backend\.pytest_tmp_run_' + [DateTime]::UtcNow.ToString('yyyyMMddHHmmssfff')
& 'C:\Users\exsaf\AppData\Local\Programs\Python\Python312\python.exe' -m pytest backend\tests -q --basetemp $temp
```

The default enforcement command for agentic work is now:

```powershell
.\scripts\run_agentic_checks.ps1
```

Useful switches:

```powershell
.\scripts\run_agentic_checks.ps1 -Fast
.\scripts\run_agentic_checks.ps1 -FullBackend
.\scripts\run_agentic_checks.ps1 -IncludeFrontend
.\scripts\run_agentic_checks.ps1 -RequireRemoteLlmRuntime
```

### Known gate notes

- The full agentic marker suite is the required signoff gate.
- For faster local iteration, use:

```powershell
.\scripts\run_agentic_checks.ps1 -Fast
```

- `-Fast` runs the high-signal agentic suites directly instead of the whole marker selection. Use it while iterating, then rerun the default gate before claiming the work is complete.
- Windows video tests previously depended on generating a sample MP4 via `ffmpeg` during the suite. That was flaky on some local environments and caused false agentic gate failures.
- The repo now carries a fixed fixture at `backend/tests/fixtures/meal-video.mp4`, and `test_video_intake.py` accepts explicit degraded probe fallback when metadata probing fails.
- `tesseract` is still optional for the gate. Missing `tesseract` should not block production-grade signoff unless the task specifically raises OCR quality requirements.

Tests that cover agentic behavior should carry the `@pytest.mark.agentic` marker, or a file-level `pytestmark = pytest.mark.agentic`.

### Required runtime verification

If the change is supposed to hit a real remote LLM path, do not claim it is "fully connected" unless you also verify the runtime assumption:

- `AI_PROVIDER=builderspace`
- valid `AI_BUILDER_TOKEN`
- the route or job actually reaches the remote provider

If those are not active, state clearly that code wiring is complete but runtime LLM execution is still gated by configuration.

### Required observability checks

For agentic changes, verify that the affected path records enough telemetry to debug behavior later.

Check for the relevant task family and summary fields, including when applicable:

- `provider_name`
- `model_name`
- `prompt_version`
- `route_policy`
- `route_target`
- `llm_cache`
- `fallback_reason`
- task outcome / persisted effect

If a major user-facing agentic path bypasses observability, treat that as an incomplete change.

### Required reporting

When you finish an agentic change, explicitly report:

- which surfaces were truly wired
- which surfaces remain deterministic by design
- which tests were run
- whether the real remote LLM path was or was not exercised
- any remaining gaps

Do not summarize an agentic change as "checked" unless the items above were covered.

### Eval guidance

Use task-based eval thinking for agentic work:

- evaluate the harness plus the model together
- prefer multi-turn / trajectory-aware checks for agent loops
- verify environment state or persisted output, not only final assistant text
- run repeated trials when non-determinism matters
- calibrate LLM-as-judge style grading against at least a small human-reviewed sample before trusting it

### References

- OpenAI Evaluation Best Practices: https://developers.openai.com/api/docs/guides/evaluation-best-practices
- OpenAI Reasoning Best Practices: https://developers.openai.com/api/docs/guides/reasoning-best-practices
- Anthropic, Demystifying evals for AI agents: https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents
- Anthropic, Writing effective tools for AI agents: https://www.anthropic.com/engineering/writing-tools-for-agents
- Repo spec: `docs/evals-observability-tech-spec.md`

## Current Runtime Facts

Keep these points in mind before reasoning about "what is wired" or "what runs in production":

- The app's active remote LLM provider is `BuilderSpace`.
- Runtime should be treated as BuilderSpace-backed only when `AI_PROVIDER=builderspace` and `AI_BUILDER_TOKEN` is present in the app environment.
- BuilderSpace MCP access inside Codex is **not** the same thing as app runtime configuration. Do not assume the app can call BuilderSpace just because the coding agent has BuilderSpace tooling.
- The currently implemented production topology is `same-origin`, not dual deploy:
  - FastAPI serves `frontend/dist`
  - `VITE_API_BASE_URL=''`
  - runtime roles are split with `APP_RUNTIME_ROLE=web` and `APP_RUNTIME_ROLE=worker`
- `/webhooks/line` is now the production webhook ingress and should be treated as `verify -> dedupe -> enqueue -> ACK`.
- The old inline behavior is kept only as a fallback/debug route at `/webhooks/line/_legacy_inline`; do not treat it as the primary production path.
- Background processing is lease-based on Postgres-backed tables:
  - `inbound_events`
  - `search_jobs`
- Recommendation responses now include LLM-facing policy outputs:
  - `coach_message`
  - `hero_reason`
  - `strategy_label`
- Planning is now split into bounded policy + copy layers:
  - deterministic allocation still owns the numbers
  - LLM selection/allocation remains bounded
  - a separate planning copywriter pass writes the final coach message
- Webhook observability now reaches the dashboard/eval layer:
  - `execution_phase` and `ingress_mode` are exposed in trace lists
  - webhook ingress/worker and planning-copy slices are available in `/api/observability/eval-export`
- The current rollout status lives in `docs/production-grade-llm-rollout-report-2026-03-20.md`.
- The Phase C tradeoff analysis lives in `docs/phase-c-dual-deploy-analysis-2026-03-21.md`.
- The operator-facing runtime handoff record lives in `docs/operator-runtime-registry.md`.
- Before public launch, treat BuilderSpace and Google Maps credentials as needing out-of-band rotation if they were ever exposed in chat or local `.env` history.

## Cross-Window Handoff Gaps

These are the most important facts a new agent still cannot reliably infer from code alone. Check them before making production claims or changing deployment assumptions:

- The actual production/staging base URLs:
  - app base URL
  - LINE webhook URL
  - LIFF URL
- Where secrets are really stored for deployment:
  - platform secret manager
  - environment variable source of truth
  - whether key rotation has already been performed
- Whether the current deployment target is:
  - local dev only
  - staging/canary
  - user-facing production
- The intended BuilderSpace operational settings:
  - workspace/project ownership
  - quota/spend expectations
  - model access assumptions outside local tests
- Whether `tesseract` should remain optional in production or is expected to be installed for higher-quality OCR/video refinement.
- Whether Phase C dual deploy is still deferred or has become an active requirement.

If any of the items above are unknown, say so explicitly instead of inferring them from the codebase.

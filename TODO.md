# TODO

## Previously: question — ubuntu image vs docker image for the kromoss VM
- [x] Check kube-labs CLI auth/backend state (signed in; backend recovered)
- [x] List available images + measure real disk per image (spun up 1-unit test VMs of both, then deleted them)
- [x] Give a recommendation backed by disk/RAM math → **docker-linux** (disk is tied to the image, not units)
- [x] Fold the playbook fixes into the repo — committed + pushed to `github.com/MahmoudMabrok/ImageLab` (branch `wip/styles-quality-live-progress`; molbal GGUF node, `patch_comfy_moss_lora.py`, cloudflared tunnel unit, `remote_tunnel.sh`, AGENTS.md, TODO.md); `make test` 33/33

## Completed

### Done 2026-11-25: each image remembers its build (look + quality tier + recipe)


Reported 2026-11-25: "info like quality, look not saved with generated images".
Style presets are currently baked into the prompt *text* (suffix) and the quality
tier only exists as pixel dimensions, so finished images lose their look/tier:
the result view can't display them and re-run has to guess. Persist both as
first-class job fields, show them, and make re-run/regenerate honor them.

- [x] Server: `jobs.styles` + `jobs.quality` columns (idempotent `ALTER TABLE` migration in `Store._migrate` for the live DB); `Engine.submit()` accepts/stores them; `/api/generate` accepts optional `styles`, `quality`; `render_prompt()` in `workflow.py` is the single place the saved looks are folded into the text-encoder prompt (verified: `test_render_prompt_*`)
- [x] UI: `generate()` sends raw (unsuffixed) prompt + `styles` + `quality`; result view + Recent card details show look/quality (harness: "card details show quality tier", "result view shows saved tier/look")
- [x] re-run/regenerate restore saved style chips + quality tier (and frame) via `restoreRecipe()`; pre-metadata jobs (and MCP jobs) fall back to inference + known-suffix stripping — no double-appended suffixes (harness: legacy re-run strips ", cinematic …" to "a cat", 0 chips fabricated; failed-job "Try again" still auto-generates)
- [x] Tests: `test_store.py::test_store_migrates_old_databases_adding_styles_and_quality` (hand-built pre-feature DB), `test_api_e2e.py::test_generate_persists_style_look_and_quality_tier`, `test_workflow.py::test_render_prompt_*` — `make test` 33/33
- [x] Bonus fix in the same build (found while deploying the previous fix): `_run_job` now fails a job fast when its ComfyUI prompt is in neither queue nor history for 60 s with no output (a restart's `interrupt` can kill the resubmitted prompt; the old code spun the single worker to the full 3600 s `JOB_TIMEOUT`, blocking every job behind it — hit live: `img_0eF8FGXorRhc` wedged the queue ~30 min until manual cancel) — `test_lost_prompt_fails_fast_and_frees_the_worker`
- [x] Headless-Chromium harness (meta-test.cjs, real `web/` files): 21/21 — saved look+tier on card and result, re-run restores chips/tier/frame, legacy suffix stripping, POST carries `styles`/`quality`, fresh job's card shows them
- [x] Deploy (waits for the in-flight 768×768 job → deploys idle) + live verification: public job `img_yBZoRd7_0uKl` (256×256, `styles:"cinematic"`, `quality:"draft"`) went `running 0.05` → `succeeded` over the tunnel with prompt stored clean and both fields intact; ComfyUI history shows the text encoder received `…no text, cinematic lighting, anamorphic lens…` (render_prompt path live); PNG 256×256 RGB; served `app.js` carries the metadata code


### Done 2026-11-25: live progress without a page refresh ("nre progress" bug)


Reported 2026-11-25 (again): progress still appears stale until the user refreshes the page.
SSE `job` events are supposed to drive every live update; the client has no polling
fallback while `status.ready` (only while the engine is starting). Reproduce on the
live tunnel first, then fix.

- [x] Reproduce: capture `/api/events` over the public tunnel during a real 256×256 job — **the tunnel delivers 0 bytes** (3 concurrent curl probes, HTTP/1.1 + HTTP/2, 40+ s, not even the snapshot), while a local curl on kromoss receives snapshot + `job` events within seconds. Gateway SSE is healthy; the quick tunnel buffers the stream.
- [x] Root cause: (a) — Cloudflare quick tunnel holds `/api/events` open without forwarding any data. The browser's `EventSource` stays "open" (no onerror → the old 3-strikes refresh never fires), and the 20 s poll fallback is gated on `!status.ready`, so with a healthy engine the UI had *no* data path at all except manual refresh.
- [x] No server fix needed: SSE loop re-verified healthy on the box (snapshot + status + job events in <2 s).
- [x] Client fix (`web/app.js`): `state.lastEventAt` tracks SSE data freshness; `sseStarved()` = >30 s without a real event (3 missed 15-s pings + margin) or not OPEN; `syncPoll()` runs on every 1 s `tick` — while any job is queued/running the whole job list is re-read from `/api/generations` and merged (1 rps during the ~3-4 min generation, 0 otherwise unless SSE is starved → 5 s cadence); `pullLatest` routes running→terminal transitions through `handleEvent` so the "Image ready" toast + auto-download fire exactly once; `visibilitychange`/`focus` wakes poll once.
- [x] Headless harness (tunnel-test.cjs): mock SSE stream delivers **zero bytes** (the exact tunnel behavior); job advances 12 steps server-side; progress climbed 5 → 33 → 67 → 92% and the result view appeared with no refresh — 8/8 checks; regression harness (details/rerun/local-expiry) 24/24.
- [x] Live verification: served `app.js` over the tunnel carries `syncPoll`/`sseStarved`/`lastEventAt` (grep count 8); the browser's data path — by-id/status REST — is what the fix polls, and jobs advanced `running 0.05` → `succeeded` through it (`img_VThYyBuSlvaZ` finished 8/8, the in-flight 768×768 user job completed normally after the deploy); with SSE still starved by the tunnel, progress is driven entirely by the 1 s poll
- [x] Restart bug found during the first deploy: the gateway restart re-queued a running user job (`_recover`) and resubmitted it after the ComfyUI queue was interrupted; the prompt vanished with no history entry, so the OLD poll loop spun toward the full `JOB_TIMEOUT` (3600 s), jamming the single worker and every job behind it (`img_0eF8FGXorRhc`; freed by manual cancel). Fixed in the engine: a prompt in neither ComfyUI queue nor history 60 s after submit now fails the job fast instead of spinning an hour — regression test drives the fake Comfy's new `drop_next`
- [x] `make test` green (33/33); re-deployed (engine + UI) with an idle-time deploy that waits for in-flight jobs; live re-verified over the tunnel


### Done 2026-11-25: live list status, 5-hour TTL, per-image build details + re-run

Requested 2026-11-25: (1) Recent-list entries must show current status without a manual
page refresh; (2) image TTL → 5 hours (explicit decision overriding the 5-minute default);
(3) each listed image keeps its prompt + build details with a one-click re-run.

- [x] `web/app.js` `tick()`: flips every succeeded job whose `remainingSeconds` hit 0 to `expired` locally — a card re-renders to "expired" without a refresh even when the SSE `expired` event is missed (background tab, reconnect, tunnel hiccup)
- [x] Recent cards show build details (`WxH · steps · cfg · seed · LoRA when ≠1`, `· neg` marker with the negative text in the tooltip) + a "re-run" button that restores prompt/seed/steps/cfg/LoRA/negative and the matching frame+quality into the composer
- [x] `fmtClock` renders hours as `h:mm:ss`; warn/crit thresholds scaled to 30/10 min
- [x] `gateway/config.py` `ttl_seconds` default 300 → 18000; `.env.example` updated; no copy changes needed in MCP (descriptions interpolate `ttl_seconds`)
- [x] All user-facing "5 minutes / five minutes / 5:00 / 5 min" copy → 5 hours (`web/index.html`, `web/app.js`, README, docs/MCP.md, docs/ARCHITECTURE.md, AGENTS.md, engine docstring)
- [x] Test asserts the new TTL copy and absence of the old in the served UI; `make test` green (29/29)
- [x] Headless-Chromium harness against the real `web/` code: 24/24 — details line, tooltip, 3-part clock, re-run populates every composer field (incl. frame/quality restore), stale card flipped to "expired" at exactly its 6 s countdown with no refresh and no server event
- [x] kromoss `/etc/imagelab.env` had `IMAGELAB_TTL_SECONDS=300` pinned → updated to 18000 in place; `make deploy MACHINE=kromoss`; public `/api/health` + `/api/config` report `ttl_seconds: 18000`, old copy gone from the served page, comfyui/imagelab/imagelab-tunnel all active

### Done 2026-11-24: auto-download finished images (UI preference)

Requested 2026-11-24: an option to auto-download an image when it finishes, so the user is
not left waiting on the tab for the download. Default: off. Persisted per browser (localStorage).

- [x] Toggle in the composer (`web/index.html` + `styles.css`): default off, preference in `localStorage["imagelab.autoDownload"]`
- [x] `app.js`: success transition funneled through `jobReceived` (covers SSE, polling fallback, snapshot) → one drain loop; persisted `saved`/`pending` sets dedupe reconnects, reloads and duplicate events; aborted cleanly if the image expires mid-flight
- [x] Boot restore: checkbox + note state, and any `pending` job re-drained after `/api/generations` hydrates the jobs
- [x] Test: served UI contains the toggle (`tests/test_api_e2e.py::test_ui_and_config_are_served`); `make test` green (29/29)
- [x] Verified in a real headless Chromium against the actual `web/` code (mock gateway, 15/15 checks): default off, no save while off, one save on completion (valid PNG), preference persists across reload, no duplicate save after reload, pending queue cleared when switched off
- [x] Deployed to kromoss; public UI over the tunnel serves the toggle, `/api/health` ready

### Done 2026-11-24: MCP privacy + real-time progress

- [x] `generate_image` no longer returns the job before the engine has queued it in ComfyUI (no "queued" status in responses); `wait_seconds=0` = hand back the ID as soon as ComfyUI accepts it
- [x] Remove `list_generations` from MCP tools and the `imagelab://generations` resource (MCP keeps `generate_image`, `get_generation`, `cancel_generation`, `engine_info`)
- [x] `get_generation` includes live `progress`/`step`/`step_total`/`queue_position`/`eta_seconds` while active, so agents can poll without a global listing
- [x] Tests: tool set has no listing tool; 512×512 MCP generation waits through model load (fake ComfyUI ~4 s) and returns the PNG inline; REST listing endpoint kept for the web UI; `make test` green (29/29)
- [x] Deployed to kromoss; public MCP `tools/list` → 4 tools, resources → `imagelab://engine` only
- [x] Real 256×256 generation over the public tunnel: blocking 280 s call 524'd at Cloudflare's 120 s point, job kept running; by-id polling showed `progress 0.75, step 6/8, eta 61 s`, then `succeeded` in 217.5 s with a valid 256×256 PNG
- [x] Docs: `docs/MCP.md` (4-tool surface, no-`queued` response shape, "Long-running calls behind a tunnel"), README (4 tools, 524 guidance + troubleshooting entry, measured 215.6 s figures), web agent panel — all updated

### Done 2026-11-24: global skill

- [x] `kube-labs-comfyui` skill at `~/.agents/skills/` (SKILL.md + REFERENCE.md): kube-labs CLI, disk math, CPU ComfyUI install, molbal GGUF fork, fused-qkv patch, fp16 LoRA, cloudflared quick tunnel (incl. 120 s/524 rule), measured benchmarks

### Done 2026-11-24 (earlier): deploy + e2e on kromoss

- [x] Provision kromoss (8-unit CPU), disk cleanup, ComfyUI venv, CPU torch
- [x] Models: kromoss-Q4_K_M.gguf, GPTQ Q4 text encoder, fp16 DMD2 LoRA (converted from fp32)
- [x] `systemd` units: comfyui, imagelab, imagelab-tunnel — all active
- [x] `Unexpected architecture type in GGUF file: 'moss_image'` → molbal/ComfyUI-GGUF fork
- [x] Fused-qkv LoRA patch (`scripts/patch_comfy_moss_lora.py`), applied on kromoss, baked into `remote_setup.sh`
- [x] First end-to-end generation over the public URL: 256×256, 8 steps, 215.6 s (includes model load), valid PNG
- [x] Quick tunnel published + URL captured into `/etc/imagelab.env`

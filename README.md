# ImageLab

A small, self-hosted image generation studio for [Kromoss](https://huggingface.co/lodestones/Kromoss) — a 5B DiT fine-tune of MOSS-Image with a Qwen3.5-9B text encoder. It runs on your own machine, gives you a real UI, and exposes the same engine to AI agents over the Model Context Protocol.

Every generated PNG is deleted **five hours after it is ready**. That keeps the disk light: this is a working surface, not an archive.

```
┌──────────────────────────────┐        ┌──────────────────────────────┐
│  Browser (vanilla JS UI)     │        │  Agent (Claude Code, Codex,  │
│  REST + SSE                  │        │  Cursor…) over MCP           │
└──────────────┬───────────────┘        └──────────────┬───────────────┘
               │                                       │
               ▼                                       ▼
      ┌────────────────────────────────────────────────────────┐
      │  FastAPI gateway :8080                                 │
      │  queue · SQLite · SSE · 5-hour reaper · MCP at /mcp     │
      └───────────────────────────┬────────────────────────────┘
                                  │ HTTP + WebSocket
                                  ▼
      ┌────────────────────────────────────────────────────────┐
      │  ComfyUI :8188 (headless)                              │
      │  Kromoss GGUF Q4_K_M · Qwen3.5-9B · FLUX.2 VAE         │
      │  8-step DMD2 LoRA · euler / simple · CFG 1             │
      └────────────────────────────────────────────────────────┘
```

## What you get

- **A proper studio UI** — prompt composer, style presets, aspect ratios, quality tiers (each finished image remembers its look, tier and full recipe), live progress (SSE plus a 1 s poll of in-flight jobs, so it survives proxies/tunnels that swallow the SSE stream), download (or opt-in auto-download, remembered per browser), cancel, delete-now, and a recent strip with countdowns and one-click re-run.
- **MCP for agents** — `generate_image`, `get_generation`, `cancel_generation`, `engine_info`. Images come back inline as base64 and are also served over HTTP. Agents only see the jobs they start (no listing endpoint).
- **Self-destructing images** — the reaper runs every two seconds and removes files whose five-hour TTL expired. Metadata is kept for a day so the UI can show what happened.
- **Two profiles** — a CPU profile that fits a kube-labs 8-unit machine, and a GPU INT8 profile for a real card.
- **No front-end build step** — the UI is three static files served by the gateway.

## Profiles

| | CPU (default) | GPU INT8 |
|---|---|---|
| Transformer | `kromoss-Q4_K_M.gguf` (GGUF, ~3.6 GB) | `kromoss_int8_convrot.safetensors` (~5.4 GB) |
| Text encoder | `qwen3.5_9b_w4a8_gptq.safetensors` (~7.3 GB) | same |
| VAE | `flux2-vae_small.safetensors` (~0.25 GB) | same |
| LoRA | `8-steps-dmd2-lora.safetensors` (1.2 GB fp32, auto-converted to fp16: ~0.6 GB) | same |
| Weights on disk | **~11.7 GB** | ~14.2 GB |
| Default size | 512×512, 8 steps | 1024×1024, 8 steps |
| Loader | `UnetLoaderGGUF` | `UNETLoader` |

Why CPU uses GGUF: kube-labs machines are CPU-only (max 8 units = 8 vCPU / 16 GB RAM / 16 GB disk, no GPU). ggml Q4 kernels are the CPU-native path. The INT8 ConvRot file is built for CUDA/HIP — its int8 attention path has no CPU implementation, so it would be slower *and* it does not fit in 16 GB of disk alongside PyTorch and ComfyUI.

The loader is [molbal's comfyui-gguf-reboot fork](https://github.com/molbal/ComfyUI-GGUF), not the stock city96 node pack. Kromoss GGUF files declare the `moss_image` architecture, which the stock loader rejects; the fork accepts it and keeps the `UnetLoaderGGUF` node name, so the workflow graph is unchanged.

Set the profile with environment variables (`profiles/cpu-kube-labs.env` or `profiles/gpu-int8.env`), then restart the gateway.

## Quick start on kube-labs

Prerequisites: the `kube-labs` CLI, authenticated, and `jq` locally.

```bash
# 1. Create an 8-unit machine (CPU only; that is the largest size)
kube-labs vm create --image docker-linux --units 8 --name kromoss --wait

# 2. Provision it: CPU PyTorch, ComfyUI, the GGUF node, and disk cleanup
make setup MACHINE=kromoss

# 3. Download the CPU weights (~12.4 GB; the LoRA is converted to fp16 in place, saving ~0.6 GB)
make models MACHINE=kromoss

# 4. Upload this repo and start both services
make deploy MACHINE=kromoss

# 5. Publish the UI on a Cloudflare quick tunnel and print the URL
make tunnel MACHINE=kromoss
```

`make setup` removes Docker and containerd on the remote box to reclaim ~1.3 GB. That is intentional — the machine exists to run ComfyUI, and the disk is the binding constraint.

The first generation is slow because ComfyUI loads the 9B text encoder and the transformer from disk. The UI says so; subsequent jobs reuse the warm process.

### Manual equivalent

```bash
kube-labs exec kromoss -- bash /srv/imagelab/scripts/remote_setup.sh
kube-labs exec kromoss -- bash /srv/imagelab/scripts/remote_models.sh
./scripts/deploy.sh kromoss
./scripts/tunnel.sh kromoss 8080
```

Services are managed by systemd:

```bash
kube-labs exec kromoss -- systemctl status comfyui imagelab
kube-labs exec kromoss -- journalctl -u imagelab -n 100
```

## Using the UI

1. Type a prompt (or press **Surprise me**).
2. Optionally add style suffixes, pick an aspect ratio and quality.
3. Press **Generate** (⌘↵ / Ctrl↵).
4. Watch the progress ring; you can close the tab — the job keeps running.
5. Download the PNG before the countdown reaches zero. **Delete now** removes it immediately.

`Draft` (512 px) is the sensible default on CPU. `Balanced` (640 px) and `Detail` (768 px) scale pixels, and CPU time scales with them.

## Public URL with Cloudflare

`make tunnel MACHINE=kromoss` installs `cloudflared` on the machine, runs it as
`imagelab-tunnel.service`, and prints the `https://<name>.trycloudflare.com`
URL. It also writes that URL to `IMAGELAB_PUBLIC_URL` and restarts the gateway so
generated links and MCP responses use the public host.

A quick tunnel needs no Cloudflare account. The hostname is **ephemeral**: it
changes whenever `imagelab-tunnel` restarts. For a stable hostname, create a
named tunnel with `cloudflared tunnel login` and `cloudflared tunnel create`,
then point its ingress at `http://127.0.0.1:8080`.

The platform’s own URL (or a local port-forward) is still available with
`make tunnel-platform MACHINE=kromoss`.

```bash
# On the machine
systemctl status imagelab-tunnel
journalctl -u imagelab-tunnel -n 50
```

Set `IMAGELAB_API_KEY` before publishing publicly. The quick tunnel is a real
public listener; without a key, anyone with the hostname can generate images.

## Using MCP

The gateway speaks Streamable HTTP at `/mcp`. No SDK is required on the server side.

### Claude Code

```bash
claude mcp add --transport http imagelab https://<your-machine>/mcp
```

### Generic client config

```json
{
  "mcpServers": {
    "imagelab": {
      "type": "http",
      "url": "https://<your-machine>/mcp"
    }
  }
}
```

### Stdio-only clients

```bash
python -m gateway.mcp_stdio --url https://<your-machine>/mcp
```

Add `--key <API_KEY>` when the server has `IMAGELAB_API_KEY` set.

### Tools

| Tool | Arguments | Returns |
|---|---|---|
| `generate_image` | `prompt`, `width`, `height`, `steps`, `cfg`, `seed`, `negative_prompt`, `wait_seconds` | Job summary + PNG inline when ready |
| `get_generation` | `id` | Your job by id, with live progress while running + PNG inline while alive |
| `cancel_generation` | `id` | Updated status |
| `engine_info` | — | Device, queue, defaults, limits, TTL |

`generate_image` blocks until the engine has the job, then for up to `wait_seconds` (default 90, max 600). On CPU, a job often exceeds that, so it returns `running` (with progress, step and ETA) and the agent polls `get_generation`. There is deliberately no listing tool — agents only ever see the jobs they started; cross-user history stays in the web UI and `GET /api/generations`. The tool text tells the agent to save the bytes immediately, because the URL dies with the file.

**Over a Cloudflare quick tunnel, prefer `wait_seconds: 0`.** Quick tunnels cut off origin requests after 120 s (error 524); the job keeps running server-side, but the agent that blocked has no listing tool to recover the ID. With `wait_seconds: 0` the tool returns the id as soon as the engine has the job (sub-second), and the agent polls `get_generation` at its own pace. A tunnel restart changes the hostname, so a long-blocking call has a second chance to die.

See [docs/MCP.md](docs/MCP.md) for raw JSON-RPC examples and the exact response shape.

## REST API

```bash
curl -s http://127.0.0.1:8080/api/generate \
  -H 'Content-Type: application/json' \
  -d '{"prompt":"a tabby cat holding a sign that says KROMOSS","width":512,"height":512,"steps":8}'
```

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/api/health` | Engine status, queue, counts, defaults, limits |
| `GET` | `/api/config` | Public config for the UI |
| `POST` | `/api/generate` | Queue a generation (202) |
| `GET` | `/api/generations` | Recent generations |
| `GET` | `/api/generations/{id}` | One generation |
| `POST` | `/api/generations/{id}/cancel` | Cancel queued/running |
| `DELETE` | `/api/generations/{id}` | Delete the image now |
| `GET` | `/api/images/{id}` | The PNG (410 after expiry) |
| `GET` | `/api/events` | SSE: snapshot, job updates, expiries, status |
| `POST` | `/mcp` | MCP JSON-RPC |

OpenAPI docs live at `/api/docs`.

## Configuration

Copy `.env.example` to `/etc/imagelab.env` on the machine (the deploy script does this once) and edit it.

| Variable | Default | Meaning |
|---|---|---|
| `COMFY_URL` | `http://127.0.0.1:8188` | ComfyUI endpoint |
| `COMFY_OUTPUT_DIR` | `/srv/ComfyUI/output` | Where ComfyUI writes PNGs |
| `IMAGELAB_UNET` | `kromoss-Q4_K_M.gguf` | Transformer file name |
| `IMAGELAB_UNET_LOADER` | `UnetLoaderGGUF` | `UnetLoaderGGUF` or `UNETLoader` |
| `IMAGELAB_CLIP` | `qwen3.5_9b_w4a8_gptq.safetensors` | Text encoder |
| `IMAGELAB_CLIP_TYPE` | `moss_image` | ComfyUI CLIP type |
| `IMAGELAB_CLIP_DEVICE` | `default` | `cpu` keeps the 9B encoder paged off the compute device |
| `IMAGELAB_VAE` | `flux2-vae_small.safetensors` | VAE |
| `IMAGELAB_LORA` | `8-steps-dmd2-lora.safetensors` | Step-distilled LoRA |
| `IMAGELAB_DEVICE_LABEL` | `CPU` | Shown in the UI |
| `IMAGELAB_TTL_SECONDS` | `18000` | Image lifetime after completion (5 hours) |
| `IMAGELAB_JOB_TIMEOUT` | `3600` | Hard per-job timeout |
| `IMAGELAB_DEFAULT_WIDTH/HEIGHT` | `512` | Defaults |
| `IMAGELAB_DEFAULT_STEPS` | `8` | Defaults |
| `IMAGELAB_MAX_DIMENSION` | `1024` | Upper bound |
| `IMAGELAB_MAX_STEPS` | `16` | Upper bound |
| `IMAGELAB_ETA_SCALE` | `1` | ETA calibration multiplier (`0.04` for GPU) |
| `IMAGELAB_DATA_DIR` | `/srv/imagelab/data` | SQLite + images |
| `IMAGELAB_API_KEY` | empty | Optional shared secret |
| `IMAGELAB_PUBLIC_URL` | empty | Absolute URLs in `/api/config` |

If `IMAGELAB_API_KEY` is set, every `/api/*` and `/mcp` request needs `Authorization: Bearer <key>` or `X-API-Key: <key>`. The UI asks once and stores the key in `localStorage`. **Do not expose the machine publicly without a key.**

## How the TTL works

- A successful job gets `expires_at = finished_at + IMAGELAB_TTL_SECONDS`.
- The reaper wakes every two seconds, finds due jobs, deletes the file, sets `status='expired'`, clears `filename`, and emits an SSE `expired` event.
- The image endpoint returns `410 Gone` once the file is gone.
- Metadata older than 24 hours is purged.
- Deleting an image early uses the same path, so the UI and agents see a consistent state.
- On restart, interrupted `running` jobs are requeued and orphan PNGs are removed.

The countdown in the UI is computed from `expires_in` plus local elapsed time, so it stays honest even if SSE reconnects.

## Performance

CPU generation is the whole story on kube-labs. With 8 vCPU and the Q4 GGUF transformer:

- 256×256, 8 steps: **measured 215.6 s** (≈ 3.6 min) on kromoss, including the one-time model load (3.6 GB GGUF transformer + 9 B text encoder). Sampling alone is the bulk of that after warm-up.
- 512×512, 8 steps: 4× the pixels, expect roughly ten minutes including any model load.
- 640×640: ~1.6× the pixels of 512, so noticeably longer.
- 768×768 and above: tens of minutes. Use it for a final pass, not iteration.

The ETA in the UI is a calibrated guess until real jobs complete; after that it uses observed progress. Run `make trial` to measure your machine and adjust `IMAGELAB_ETA_SCALE`.

On a 24 GB GPU with the INT8 profile, the same settings are interactive (seconds, not minutes). That is the profile to use if you have a card.

## Development

```bash
make install     # venv + dev dependencies
make test        # 29 tests: graph, store, MCP, engine e2e, API e2e
make run         # gateway on :8080 (expects ComfyUI at :8188)
```

The gateway is deliberately dependency-light: FastAPI, httpx, websockets, SQLite. MCP is implemented directly in `gateway/mcp_http.py` rather than through an SDK, so protocol upgrades cannot break the server.

```
gateway/
  config.py     environment-driven settings
  store.py      SQLite job store (claim, expire, purge)
  workflow.py   ComfyUI graph builder + ETA
  comfy.py      async ComfyUI client (submit, history, WS progress)
  engine.py     queue worker, events, TTL reaper, waiters
  main.py       FastAPI app, REST, SSE, static UI
  mcp_http.py   MCP JSON-RPC over Streamable HTTP
  mcp_stdio.py  stdio bridge for local agents
web/            the UI (no build step)
scripts/        provisioning, deploy, tunnel, trial
profiles/       CPU and GPU environment profiles
systemd/        comfyui.service, imagelab.service, imagelab-tunnel.service
tests/          pytest suite
```

More detail in [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## Troubleshooting

**`engine offline` in the UI.** ComfyUI is not up. Check `systemctl status comfyui` and `journalctl -u comfyui -n 100`. The gateway reconnects automatically.

**First job never finishes.** ComfyUI is loading a 9B text encoder from disk on a CPU box. Watch `journalctl -u comfyui -f`; the first load can take minutes. Subsequent jobs are much faster.

**`ComfyUI rejected the workflow`.** The node names or file names do not match the installed ComfyUI. Confirm the GGUF custom node is present (`custom_nodes/ComfyUI-GGUF`) and that `models/diffusion_models/kromoss-Q4_K_M.gguf` exists.

**`Unexpected architecture type in GGUF file: 'moss_image'`.** The stock city96 loader is installed. Re-run `make setup` (or clone [molbal/ComfyUI-GGUF](https://github.com/molbal/ComfyUI-GGUF)) and restart ComfyUI.

**`start (0) + length (...) exceeds dimension size (...)`.** ComfyUI is mapping the MOSS-Image LoRA onto a GGUF model without the fused-qkv fix. Run `python3 scripts/patch_comfy_moss_lora.py /srv/ComfyUI/comfy/lora.py` and restart ComfyUI (`make setup` applies it automatically).

**MCP call over the tunnel dies with Cloudflare error 524.** Quick tunnels cut origin requests at 120 s. The generation keeps running server-side, but the blocked client has no listing tool to recover the job id. Use `wait_seconds: 0` and poll `get_generation` (see [docs/MCP.md](docs/MCP.md)).

**Out of disk.** `df -h /`. The CPU profile needs ~11.7 GB of weights plus ~1.5 GB for Python (the fp32 LoRA is converted to fp16 automatically by `remote_models.sh`). If you are still tight, the next lever is a smaller text-encoder quant; the GGUF node accepts `qwen3`/`qwen3vl` text encoders as well.

**Images vanish before you saved them.** Five hours is a long time, but the TTL is `IMAGELAB_TTL_SECONDS` — lower it for ephemeral hosts, or turn on auto-download in the UI.

## Model and license

Kromoss is published by [lodestones](https://huggingface.co/lodestones/Kromoss) under Apache-2.0. This repo is just a runner; it does not redistribute weights. Check the model card for the current license and usage terms.

## Status

- Gateway, UI, MCP server, tests, and deployment scripts are complete.
- Verified end to end on kromoss (2026-11-24): a 256×256, 8-step generation submitted over the public Cloudflare URL with MCP completed in 215.6 s and returned a valid PNG; the UI, REST, and MCP endpoints all answer over the tunnel.

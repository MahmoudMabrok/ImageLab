#!/usr/bin/env bash
# Download the CPU profile weights for Kromoss.
#   transformer : kromoss-Q4_K_M.gguf            ~3.4 GiB
#   text encoder: qwen3.5_9b_w4a8_gptq.safetensors ~6.8 GiB (official Comfy-Org build)
#   vae         : flux2-vae_small.safetensors     ~0.23 GiB
#   lora        : 8-steps-dmd2-lora.safetensors   ~1.1 GiB (8 steps, CFG 1)
set -euo pipefail

ROOT="${ROOT:-/srv}"
COMFY_DIR="$ROOT/ComfyUI"
HF="${HF_ENDPOINT:-https://huggingface.co}"

dl() { # dl <url> <dest>
  local url="$1" dest="$2"
  if [ -s "$dest" ]; then
    echo "  have $(basename "$dest")"
    return
  fi
  echo "  fetching $(basename "$dest")"
  aria2c -q -x 8 -s 8 -k 4M --file-allocation=none --allow-overwrite=true \
    --dir "$(dirname "$dest")" --out "$(basename "$dest")" "$url"
}

mkdir -p "$COMFY_DIR/models/diffusion_models" "$COMFY_DIR/models/text_encoders" \
         "$COMFY_DIR/models/vae" "$COMFY_DIR/models/loras"

echo "==> Diffusion model (GGUF Q4_K_M)"
dl "$HF/molbal/Kromoss-GGUF/resolve/main/kromoss-Q4_K_M.gguf" \
   "$COMFY_DIR/models/diffusion_models/kromoss-Q4_K_M.gguf"

echo "==> Text encoder (Qwen3.5-9B w4a8 GPTQ)"
dl "$HF/Comfy-Org/MOSS-Image/resolve/main/text_encoders/qwen3.5_9b_w4a8_gptq.safetensors" \
   "$COMFY_DIR/models/text_encoders/qwen3.5_9b_w4a8_gptq.safetensors"

echo "==> VAE"
dl "$HF/Comfy-Org/MOSS-Image/resolve/main/vae/flux2-vae_small.safetensors" \
   "$COMFY_DIR/models/vae/flux2-vae_small.safetensors"

echo "==> 8-step turbo LoRA"
LORA="$COMFY_DIR/models/loras/8-steps-dmd2-lora.safetensors"
dl "$HF/lodestones/Kromoss/resolve/main/8-steps-dmd2-lora.safetensors" "$LORA"

# fp32 -> fp16 saves ~0.6 GB, which is what makes this fit on a 16 GB disk.
# In place, so IMAGELAB_LORA keeps its name.
CONVERTER="$(dirname "$0")/convert_lora_fp16.py"
if [ -x "$COMFY_DIR/.venv/bin/python" ] && [ -f "$CONVERTER" ]; then
  echo "==> LoRA fp32 -> fp16"
  "$COMFY_DIR/.venv/bin/python" "$CONVERTER" "$LORA" || true
fi

echo "==> Sizes"
du -sh "$COMFY_DIR/models"/*/* | sort -h
df -h / | tail -1

#!/usr/bin/env bash
# GPU profile weights: INT8 ConvRot transformer + w4a8 text encoder.
# Use on a CUDA/HIP host with >=16 GB VRAM (24 GB recommended).
set -euo pipefail

ROOT="${ROOT:-/srv}"
COMFY_DIR="$ROOT/ComfyUI"
HF="${HF_ENDPOINT:-https://huggingface.co}"

dl() {
  local url="$1" dest="$2"
  [ -s "$dest" ] && { echo "  have $(basename "$dest")"; return; }
  echo "  fetching $(basename "$dest")"
  aria2c -q -x 8 -s 8 -k 4M --file-allocation=none --allow-overwrite=true \
    --dir "$(dirname "$dest")" --out "$(basename "$dest")" "$url"
}

mkdir -p "$COMFY_DIR/models/diffusion_models" "$COMFY_DIR/models/text_encoders" \
         "$COMFY_DIR/models/vae" "$COMFY_DIR/models/loras"

echo "==> Diffusion model (INT8 ConvRot, 5.4 GB)"
dl "$HF/lodestones/Kromoss/resolve/main/diffusion_models/kromoss_int8_convrot.safetensors" \
   "$COMFY_DIR/models/diffusion_models/kromoss_int8_convrot.safetensors"

echo "==> Text encoder (Qwen3.5-9B w4a8 GPTQ)"
dl "$HF/Comfy-Org/MOSS-Image/resolve/main/text_encoders/qwen3.5_9b_w4a8_gptq.safetensors" \
   "$COMFY_DIR/models/text_encoders/qwen3.5_9b_w4a8_gptq.safetensors"

echo "==> VAE"
dl "$HF/Comfy-Org/MOSS-Image/resolve/main/vae/flux2-vae_small.safetensors" \
   "$COMFY_DIR/models/vae/flux2-vae_small.safetensors"

echo "==> 8-step turbo LoRA"
dl "$HF/lodestones/Kromoss/resolve/main/8-steps-dmd2-lora.safetensors" \
   "$COMFY_DIR/models/loras/8-steps-dmd2-lora.safetensors"

du -sh "$COMFY_DIR/models"/*/* | sort -h

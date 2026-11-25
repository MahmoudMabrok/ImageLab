#!/usr/bin/env python3
"""Make ComfyUI's MOSS-Image LoRA map work with GGUF weights.

ComfyUI splits a LoRA trained with separate ``proj.q``/``k``/``v`` across the
model's fused ``proj.qkv`` weight. The stock key map computes the slice width as
``sd[k].shape[0] // 3``. For GGUF tensors the state-dict entry is a packed 1-D
buffer, so that gives the packed byte count instead of the logical width and
``calculate_weight`` fails with:

    RuntimeError: start (0) + length (...) exceeds dimension size (...)

The unet config carries the real model width, so use it. This is idempotent and
safe to re-run after a ComfyUI update.

    python3 scripts/patch_comfy_moss_lora.py /srv/ComfyUI/comfy/lora.py
"""

from __future__ import annotations

import sys
from pathlib import Path

MARKER = 'qkv_third = model.model_config.unet_config.get("dim"'

OLD = '''    if isinstance(model, comfy.model_base.MOSSImage):
        for k in sdk:
            if k.startswith("diffusion_model.") and k.endswith(".weight"):
                key_map[k[len("diffusion_model."):-len(".weight")]] = k  # bare module paths
            if k.endswith(".proj.qkv.weight"):  # fused q/k/v files; LoRAs address the separate projections
                third = sd[k].shape[0] // 3
'''

NEW = '''    if isinstance(model, comfy.model_base.MOSSImage):
        # GGUF state_dict entries are packed 1-D, so sd[k].shape is the packed
        # storage size, not the logical fused-qkv width. The unet config is
        # correct for both GGUF and safetensors.
        qkv_third = model.model_config.unet_config.get("dim", 3072)
        for k in sdk:
            if k.startswith("diffusion_model.") and k.endswith(".weight"):
                key_map[k[len("diffusion_model."):-len(".weight")]] = k  # bare module paths
            if k.endswith(".proj.qkv.weight"):  # fused q/k/v files; LoRAs address the separate projections
                third = qkv_third
'''


def main() -> int:
    path = Path(sys.argv[1] if len(sys.argv) > 1 else "/srv/ComfyUI/comfy/lora.py")
    if not path.is_file():
        print(f"missing: {path}", file=sys.stderr)
        return 1

    text = path.read_text()
    if MARKER in text:
        print(f"already patched: {path}")
        return 0
    if OLD not in text:
        print(f"MOSS-Image LoRA block not found in {path}; patch skipped", file=sys.stderr)
        return 1

    path.write_text(text.replace(OLD, NEW, 1))
    print(f"patched MOSS-Image GGUF LoRA slice width: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

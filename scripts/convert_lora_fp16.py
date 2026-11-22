#!/usr/bin/env python3
"""Convert a LoRA to fp16 in place.

The 8-step DMD2 LoRA ships as fp32 and is ~1.2 GB. On a 16 GB disk that is the
difference between fitting and not fitting, and ComfyUI loads it into a
bf16/fp16 model anyway. Scalars (alpha) keep their original dtype.

    /srv/ComfyUI/.venv/bin/python scripts/convert_lora_fp16.py \
        /srv/ComfyUI/models/loras/8-steps-dmd2-lora.safetensors
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description="Convert LoRA tensors to fp16 in place")
    parser.add_argument("path", type=Path)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    path: Path = args.path
    if not path.is_file():
        print(f"missing: {path}", file=sys.stderr)
        return 1

    import torch
    from safetensors.torch import load_file, save_file

    tensors = load_file(str(path))
    out: dict[str, "torch.Tensor"] = {}
    changed = 0
    for key, value in tensors.items():
        if (
            value.is_floating_point()
            and value.numel() > 1
            and value.dtype not in (torch.float16, torch.bfloat16)
        ):
            out[key] = value.to(torch.float16).contiguous()
            changed += 1
        else:
            out[key] = value.contiguous()

    if changed == 0:
        print(f"already fp16: {path} ({path.stat().st_size / 1e9:.2f} GB)")
        return 0

    before = path.stat().st_size
    if args.dry_run:
        print(f"would convert {changed} tensors ({before / 1e9:.2f} GB)")
        return 0

    tmp = path.with_name(path.name + ".tmp")
    save_file(out, str(tmp), metadata={"format": "pt"})
    os.replace(tmp, path)
    after = path.stat().st_size
    print(
        f"converted {changed} tensors: {before / 1e9:.2f} GB -> {after / 1e9:.2f} GB"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

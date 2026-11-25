"""Builds the ComfyUI API graph for a Kromoss generation.

The default graph is the CPU-friendly path: GGUF transformer + 8-step DMD2
LoRA at CFG 1, so the negative branch is skipped entirely (ConditioningZeroOut)
and the text encoder runs once.
"""

from __future__ import annotations

from typing import Any

from .config import Settings

NODE_UNET = "1"
NODE_CLIP = "2"
NODE_VAE = "3"
NODE_POS = "4"
NODE_NEG = "5"
NODE_LATENT = "6"
NODE_LORA = "7"
NODE_SAMPLER = "8"
NODE_DECODE = "9"
NODE_SAVE = "10"

# The style presets ("looks") as prompt wording. The UI keeps the idea and
# the look as separate job fields (prompt + styles); this is the single
# place that folds the selected looks back into the text encoder's prompt.
STYLE_SUFFIXES = {
    "cinematic": ", cinematic lighting, anamorphic lens, film still, dramatic contrast",
    "photo": ", photorealistic, natural skin texture, 85mm lens, shallow depth of field",
    "anime": ", anime-style digital illustration, clean linework, cel shading",
    "product": ", product photography, seamless backdrop, softbox, crisp detail",
    "poster": ", graphic poster design, bold typography, limited palette",
    "illustration": ", editorial illustration, textured brushwork, muted palette",
}


def render_prompt(prompt: str, styles: str = "") -> str:
    """The idea + the selected style presets, in the order they were chosen.

    This is what the text encoder actually sees; the job stores the two
    parts separately so the UI can show and restore them.
    """
    text = (prompt or "").strip()
    for raw in (styles or "").split(","):
        key = raw.strip()
        if key in STYLE_SUFFIXES:
            text = (text + STYLE_SUFFIXES[key]).strip()
    return text.strip().lstrip(",").strip()


def clamp_dimension(value: int, settings: Settings) -> int:
    value = int(value)
    value = max(settings.min_dimension, min(settings.max_dimension, value))
    return value - (value % 16)


def build_workflow(
    settings: Settings,
    *,
    prompt: str,
    negative: str,
    width: int,
    height: int,
    steps: int,
    cfg: float,
    seed: int,
    lora_strength: float | None = None,
) -> dict[str, Any]:
    width = clamp_dimension(width, settings)
    height = clamp_dimension(height, settings)
    steps = max(1, min(settings.max_steps, int(steps)))
    cfg = max(1.0, min(10.0, float(cfg)))
    strength = settings.lora_strength if lora_strength is None else float(lora_strength)

    if settings.unet_loader == "UNETLoader":
        unet: dict[str, Any] = {
            "class_type": "UNETLoader",
            "inputs": {"unet_name": settings.unet_name, "weight_dtype": "default"},
        }
    else:
        unet = {
            "class_type": "UnetLoaderGGUF",
            "inputs": {"unet_name": settings.unet_name},
        }

    graph: dict[str, Any] = {
        NODE_UNET: unet,
        NODE_CLIP: {
            "class_type": "CLIPLoader",
            "inputs": {
                "clip_name": settings.clip_name,
                "type": settings.clip_type,
            },
        },
        NODE_VAE: {
            "class_type": "VAELoader",
            "inputs": {"vae_name": settings.vae_name},
        },
        NODE_POS: {
            "class_type": "CLIPTextEncode",
            "inputs": {"text": prompt, "clip": [NODE_CLIP, 0]},
        },
        NODE_LATENT: {
            "class_type": "EmptyFlux2LatentImage",
            "inputs": {"width": width, "height": height, "batch_size": 1},
        },
        NODE_SAMPLER: {
            "class_type": "KSampler",
            "inputs": {
                "model": [NODE_LORA if settings.lora_name else NODE_UNET, 0],
                "positive": [NODE_POS, 0],
                "negative": [NODE_NEG, 0],
                "latent_image": [NODE_LATENT, 0],
                "seed": int(seed),
                "steps": steps,
                "cfg": cfg,
                "sampler_name": settings.sampler,
                "scheduler": settings.scheduler,
                "denoise": 1.0,
            },
        },
        NODE_DECODE: {
            "class_type": "VAEDecode",
            "inputs": {"samples": [NODE_SAMPLER, 0], "vae": [NODE_VAE, 0]},
        },
        NODE_SAVE: {
            "class_type": "SaveImage",
            "inputs": {"images": [NODE_DECODE, 0], "filename_prefix": "imagelab"},
        },
    }

    if settings.clip_device and settings.clip_device != "default":
        graph[NODE_CLIP]["inputs"]["device"] = settings.clip_device

    # CFG 1 means the negative branch is never evaluated. Zeroing it avoids a
    # second (expensive on CPU) pass through the 9B text encoder.
    if cfg <= 1.01:
        graph[NODE_NEG] = {
            "class_type": "ConditioningZeroOut",
            "inputs": {"conditioning": [NODE_POS, 0]},
        }
    else:
        graph[NODE_NEG] = {
            "class_type": "CLIPTextEncode",
            "inputs": {"text": negative, "clip": [NODE_CLIP, 0]},
        }

    if settings.lora_name:
        graph[NODE_LORA] = {
            "class_type": "LoraLoaderModelOnly",
            "inputs": {
                "model": [NODE_UNET, 0],
                "lora_name": settings.lora_name,
                "strength_model": strength,
            },
        }

    return graph


def estimated_seconds(settings: Settings, width: int, height: int, steps: int) -> int:
    """Rough ETA used by the UI before the first job of a size completes.

    Calibrated on 8 vCPU (kube-labs) with the Q4 GGUF profile: 8 steps at
    512x512 lands around ten minutes including text encoding. Scales with
    pixels and steps; a GPU host overrides this via IMAGELAB_ETA_SCALE.
    """
    megapixels = (width * height) / (512 * 512)
    base = 180 + 420 * megapixels * (steps / 8.0)
    return max(15, int(base * max(0.001, settings.eta_scale)))

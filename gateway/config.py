"""Runtime configuration, read from the environment."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


def _int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, "") or default)
    except ValueError:
        return default


def _float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, "") or default)
    except ValueError:
        return default


def _bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None or raw == "":
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    # Engine
    comfy_url: str = field(default_factory=lambda: os.getenv("COMFY_URL", "http://127.0.0.1:8188"))
    comfy_output_dir: Path = field(
        default_factory=lambda: Path(os.getenv("COMFY_OUTPUT_DIR", "/srv/ComfyUI/output"))
    )
    unet_name: str = field(
        default_factory=lambda: os.getenv("IMAGELAB_UNET", "kromoss-Q4_K_M.gguf")
    )
    unet_loader: str = field(
        default_factory=lambda: os.getenv("IMAGELAB_UNET_LOADER", "UnetLoaderGGUF")
    )
    clip_name: str = field(
        default_factory=lambda: os.getenv("IMAGELAB_CLIP", "qwen3.5_9b_w4a8_gptq.safetensors")
    )
    clip_type: str = field(default_factory=lambda: os.getenv("IMAGELAB_CLIP_TYPE", "moss_image"))
    vae_name: str = field(
        default_factory=lambda: os.getenv("IMAGELAB_VAE", "flux2-vae_small.safetensors")
    )
    lora_name: str = field(
        default_factory=lambda: os.getenv("IMAGELAB_LORA", "8-steps-dmd2-lora.safetensors")
    )
    lora_strength: float = field(
        default_factory=lambda: _float("IMAGELAB_LORA_STRENGTH", 1.0)
    )
    sampler: str = field(default_factory=lambda: os.getenv("IMAGELAB_SAMPLER", "euler"))
    scheduler: str = field(default_factory=lambda: os.getenv("IMAGELAB_SCHEDULER", "simple"))
    clip_device: str = field(default_factory=lambda: os.getenv("IMAGELAB_CLIP_DEVICE", "default"))
    device_label: str = field(default_factory=lambda: os.getenv("IMAGELAB_DEVICE_LABEL", "CPU"))
    eta_scale: float = field(default_factory=lambda: _float("IMAGELAB_ETA_SCALE", 1.0))

    # Defaults and limits
    default_width: int = field(default_factory=lambda: _int("IMAGELAB_DEFAULT_WIDTH", 512))
    default_height: int = field(default_factory=lambda: _int("IMAGELAB_DEFAULT_HEIGHT", 512))
    default_steps: int = field(default_factory=lambda: _int("IMAGELAB_DEFAULT_STEPS", 8))
    default_cfg: float = field(default_factory=lambda: _float("IMAGELAB_DEFAULT_CFG", 1.0))
    default_negative: str = field(
        default_factory=lambda: os.getenv(
            "IMAGELAB_DEFAULT_NEGATIVE",
            "nsfw, worst quality, bad anatomy, watermark, jpeg artifact",
        )
    )
    max_steps: int = field(default_factory=lambda: _int("IMAGELAB_MAX_STEPS", 16))
    max_dimension: int = field(default_factory=lambda: _int("IMAGELAB_MAX_DIMENSION", 1024))
    min_dimension: int = field(default_factory=lambda: _int("IMAGELAB_MIN_DIMENSION", 256))
    max_prompt_chars: int = field(default_factory=lambda: _int("IMAGELAB_MAX_PROMPT_CHARS", 4000))

    # Jobs
    ttl_seconds: int = field(default_factory=lambda: _int("IMAGELAB_TTL_SECONDS", 300))
    job_timeout_seconds: int = field(default_factory=lambda: _int("IMAGELAB_JOB_TIMEOUT", 3600))
    history_keep_seconds: int = field(
        default_factory=lambda: _int("IMAGELAB_HISTORY_KEEP_SECONDS", 86400)
    )
    mcp_wait_default: int = field(default_factory=lambda: _int("IMAGELAB_MCP_WAIT", 90))
    mcp_wait_max: int = field(default_factory=lambda: _int("IMAGELAB_MCP_WAIT_MAX", 600))

    # Paths / server
    data_dir: Path = field(default_factory=lambda: Path(os.getenv("IMAGELAB_DATA_DIR", "/srv/imagelab/data")))
    host: str = field(default_factory=lambda: os.getenv("IMAGELAB_HOST", "0.0.0.0"))
    port: int = field(default_factory=lambda: _int("IMAGELAB_PORT", 8080))
    api_key: str = field(default_factory=lambda: os.getenv("IMAGELAB_API_KEY", ""))
    public_url: str = field(default_factory=lambda: os.getenv("IMAGELAB_PUBLIC_URL", ""))
    cors_origins: str = field(default_factory=lambda: os.getenv("IMAGELAB_CORS_ORIGINS", "*"))

    @property
    def images_dir(self) -> Path:
        return self.data_dir / "images"

    @property
    def db_path(self) -> Path:
        return self.data_dir / "imagelab.sqlite3"

    def ensure_dirs(self) -> None:
        self.images_dir.mkdir(parents=True, exist_ok=True)

    def public_base(self) -> str:
        return self.public_url.rstrip("/") if self.public_url else ""


settings = Settings()

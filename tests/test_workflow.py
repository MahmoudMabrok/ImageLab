"""The ComfyUI graph must stay valid and cheap on CPU."""

from __future__ import annotations

from gateway.config import Settings
from gateway.workflow import build_workflow, clamp_dimension, estimated_seconds


def make_settings(**overrides) -> Settings:
    base = Settings()
    if not overrides:
        return base
    import dataclasses

    return dataclasses.replace(base, **overrides)


def test_cfg_one_skips_the_negative_text_encoder():
    graph = build_workflow(
        make_settings(),
        prompt="a cat",
        negative="blurry",
        width=512,
        height=512,
        steps=8,
        cfg=1.0,
        seed=1,
    )
    assert graph["5"]["class_type"] == "ConditioningZeroOut"
    assert graph["5"]["inputs"]["conditioning"] == ["4", 0]
    # Only one CLIPTextEncode node exists, so the 9B encoder runs once.
    encoders = [n for n in graph.values() if n["class_type"] == "CLIPTextEncode"]
    assert len(encoders) == 1


def test_cfg_above_one_encodes_the_negative_prompt():
    graph = build_workflow(
        make_settings(),
        prompt="a cat",
        negative="blurry",
        width=512,
        height=512,
        steps=8,
        cfg=3.5,
        seed=1,
    )
    assert graph["5"]["class_type"] == "CLIPTextEncode"
    assert graph["5"]["inputs"]["text"] == "blurry"
    assert graph["8"]["inputs"]["cfg"] == 3.5


def test_dimensions_are_clamped_to_multiples_of_sixteen():
    settings = make_settings(min_dimension=256, max_dimension=1024)
    assert clamp_dimension(500, settings) == 496
    assert clamp_dimension(10, settings) == 256
    assert clamp_dimension(4096, settings) == 1024


def test_workflow_uses_the_lora_and_the_gguf_loader():
    graph = build_workflow(
        make_settings(unet_loader="UnetLoaderGGUF"),
        prompt="a cat",
        negative="",
        width=512,
        height=512,
        steps=8,
        cfg=1.0,
        seed=1,
    )
    assert graph["1"]["class_type"] == "UnetLoaderGGUF"
    assert graph["7"]["class_type"] == "LoraLoaderModelOnly"
    assert graph["8"]["inputs"]["model"] == ["7", 0]
    assert graph["6"]["class_type"] == "EmptyFlux2LatentImage"


def test_safetensors_profile_uses_the_plain_loader():
    graph = build_workflow(
        make_settings(unet_loader="UNETLoader", unet_name="kromoss_int8_convrot.safetensors"),
        prompt="a cat",
        negative="",
        width=512,
        height=512,
        steps=8,
        cfg=1.0,
        seed=1,
    )
    assert graph["1"]["class_type"] == "UNETLoader"
    assert graph["1"]["inputs"]["unet_name"] == "kromoss_int8_convrot.safetensors"


def test_eta_grows_with_pixels_and_steps():
    settings = make_settings(eta_scale=1.0)
    small = estimated_seconds(settings, 512, 512, 8)
    big = estimated_seconds(settings, 1024, 1024, 8)
    longer = estimated_seconds(settings, 512, 512, 16)
    assert 400 <= small <= 900
    assert big > small
    assert longer > small
    fast = estimated_seconds(make_settings(eta_scale=0.04), 1024, 1024, 8)
    assert fast < small

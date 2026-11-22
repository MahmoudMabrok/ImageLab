"""Full-stack smoke test: real gateway process + fake ComfyUI + MCP over HTTP."""

from __future__ import annotations

import base64
import json
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import httpx
import pytest

from .fake_comfy import FakeComfyServer


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def wait_for(url: str, timeout: float = 30) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            if httpx.get(url, timeout=1).status_code == 200:
                return
        except Exception:  # noqa: BLE001
            pass
        time.sleep(0.2)
    raise RuntimeError(f"{url} did not come up")


@pytest.fixture()
def stack(tmp_path):
    output = tmp_path / "comfy-output"
    output.mkdir()
    with FakeComfyServer(output, duration=0.6) as fake:
        port = free_port()
        env = {
            **os.environ,
            "COMFY_URL": fake.url,
            "COMFY_OUTPUT_DIR": str(output),
            "IMAGELAB_DATA_DIR": str(tmp_path / "data"),
            "IMAGELAB_TTL_SECONDS": "3",
            "IMAGELAB_JOB_TIMEOUT": "30",
            "IMAGELAB_DEFAULT_WIDTH": "512",
            "IMAGELAB_DEFAULT_HEIGHT": "512",
            "IMAGELAB_DEFAULT_STEPS": "8",
            "IMAGELAB_API_KEY": "",
        }
        repo = Path(__file__).resolve().parent.parent
        proc = subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "gateway.main:app",
             "--host", "127.0.0.1", "--port", str(port), "--log-level", "warning"],
            cwd=repo,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        )
        base = f"http://127.0.0.1:{port}"
        try:
            wait_for(base + "/api/health")
            yield base, tmp_path / "data"
        finally:
            proc.terminate()
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()


def test_ui_and_config_are_served(stack):
    base, _ = stack
    ui = httpx.get(base + "/")
    assert ui.status_code == 200
    assert "Kromoss Studio" in ui.text
    config = httpx.get(base + "/api/config").json()
    assert config["ttl_seconds"] == 3
    assert config["mcp"]["http"].endswith("/mcp")


def test_sse_snapshot_is_emitted(stack):
    base, _ = stack
    with httpx.stream("GET", base + "/api/events", timeout=10) as response:
        assert response.status_code == 200
        for line in response.iter_lines():
            if line.startswith("data: "):
                event = json.loads(line[6:])
                assert event["type"] == "snapshot"
                assert "status" in event
                return
    raise AssertionError("no SSE snapshot")


def test_generate_image_and_expiry(stack):
    base, data_dir = stack
    job = httpx.post(
        base + "/api/generate",
        json={"prompt": "a cat", "width": 512, "height": 512, "steps": 8, "cfg": 1},
        timeout=10,
    ).json()
    assert job["status"] == "queued"
    assert job["eta_seconds"] >= 0

    for _ in range(60):
        current = httpx.get(base + f"/api/generations/{job['id']}").json()
        if current["status"] in ("succeeded", "failed", "expired"):
            break
        time.sleep(0.25)
    assert current["status"] == "succeeded", current
    assert current["image_url"] == f"/api/images/{job['id']}"

    image = httpx.get(base + current["image_url"])
    assert image.status_code == 200
    assert image.content.startswith(b"\x89PNG")
    path = data_dir / "images" / f"{job['id']}.png"
    assert path.exists()

    # TTL is three seconds.
    for _ in range(40):
        time.sleep(0.25)
        if httpx.get(base + current["image_url"]).status_code == 410:
            break
    assert httpx.get(base + current["image_url"]).status_code == 410
    assert not path.exists()
    assert httpx.get(base + f"/api/generations/{job['id']}").json()["status"] == "expired"


def test_mcp_over_http_returns_the_png(stack):
    base, _ = stack
    headers = {"Accept": "application/json, text/event-stream"}
    init = httpx.post(
        base + "/mcp",
        headers=headers,
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2025-06-18",
                "capabilities": {},
                "clientInfo": {"name": "pytest", "version": "0"},
            },
        },
    )
    assert init.status_code == 200
    session = init.headers["mcp-session-id"]
    assert init.json()["result"]["serverInfo"]["name"] == "imagelab"
    headers["Mcp-Session-Id"] = session

    tools = httpx.post(
        base + "/mcp", headers=headers,
        json={"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
    ).json()
    assert {t["name"] for t in tools["result"]["tools"]} >= {"generate_image", "get_generation"}

    call = httpx.post(
        base + "/mcp", headers=headers,
        json={
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {
                "name": "generate_image",
                "arguments": {"prompt": "a cat", "wait_seconds": 15},
            },
        },
        timeout=30,
    ).json()
    result = call["result"]
    assert result["isError"] is False
    assert result["structuredContent"]["status"] == "succeeded"
    images = [c for c in result["content"] if c["type"] == "image"]
    assert images, result
    assert base64.b64decode(images[0]["data"]).startswith(b"\x89PNG")
    assert "deleted at" in result["content"][-1]["text"]

    job_id = result["structuredContent"]["id"]
    poll = httpx.post(
        base + "/mcp", headers=headers,
        json={
            "jsonrpc": "2.0", "id": 4, "method": "tools/call",
            "params": {"name": "get_generation", "arguments": {"id": job_id}},
        },
    ).json()
    assert poll["result"]["structuredContent"]["status"] == "succeeded"

"""MCP surface: handshake, tool discovery, validation and queueing."""

from __future__ import annotations

import dataclasses

import pytest

from gateway.config import Settings
from gateway.engine import Engine
from gateway.mcp_http import McpServer, build_tools
from gateway.store import Store


def make_settings(tmp_path) -> Settings:
    return dataclasses.replace(
        Settings(),
        data_dir=tmp_path,
        comfy_url="http://127.0.0.1:9",
        public_url="https://example.test",
        api_key="",
    )


@pytest.fixture()
def server(tmp_path):
    settings = make_settings(tmp_path)
    store = Store(settings.db_path)
    engine = Engine(settings, store)
    yield McpServer(settings, engine)
    store.close()


async def test_initialize_returns_a_session(server):
    result, headers = await server.handle(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2025-06-18",
                "capabilities": {},
                "clientInfo": {"name": "test", "version": "0"},
            },
        },
        None,
    )
    assert result is not None
    assert result["result"]["protocolVersion"] == "2025-06-18"
    assert result["result"]["serverInfo"]["name"] == "imagelab"
    assert headers["Mcp-Session-Id"]


async def test_tools_list_exposes_the_generation_surface(server):
    result, _ = await server.handle(
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}}, None
    )
    assert result is not None
    names = {tool["name"] for tool in result["result"]["tools"]}
    assert names == {
        "generate_image",
        "get_generation",
        "list_generations",
        "cancel_generation",
        "engine_info",
    }


async def test_generate_requires_a_prompt(server):
    result, _ = await server.handle(
        {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {"name": "generate_image", "arguments": {"prompt": "  "}},
        },
        None,
    )
    assert result is not None
    assert result["result"]["isError"] is True
    assert "prompt" in result["result"]["content"][0]["text"]


async def test_generate_queues_a_job_without_blocking(server):
    result, _ = await server.handle(
        {
            "jsonrpc": "2.0",
            "id": 4,
            "method": "tools/call",
            "params": {
                "name": "generate_image",
                "arguments": {"prompt": "a cat", "wait_seconds": 0},
            },
        },
        None,
    )
    assert result is not None
    payload = result["result"]
    assert payload["isError"] is False
    summary = payload["structuredContent"]
    assert summary["status"] == "queued"
    assert summary["id"].startswith("img_")
    assert server.engine.store.get(summary["id"]) is not None


async def test_unknown_method_is_a_jsonrpc_error(server):
    result, _ = await server.handle(
        {"jsonrpc": "2.0", "id": 5, "method": "nope", "params": {}}, None
    )
    assert result is not None
    assert result["error"]["code"] == -32601


def test_tool_schemas_follow_the_dimension_limits():
    tools = {tool["name"]: tool for tool in build_tools(Settings())}
    schema = tools["generate_image"]["inputSchema"]
    assert schema["properties"]["width"]["multipleOf"] == 16
    assert schema["properties"]["height"]["minimum"] == Settings().min_dimension
    assert schema["required"] == ["prompt"]

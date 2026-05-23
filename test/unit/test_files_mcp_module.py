"""MCP registrations for the files module."""

from __future__ import annotations

from typing import Any

import pydantic
import pytest
from fastmcp import FastMCP

from onedata_mcp.modules import files


@pytest.fixture
def patched_list_files(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    """Capture kwargs passed through to api.list_files."""

    captured: dict[str, Any] = {}

    async def fake_list(parent_id_or_path: str, **kw: Any) -> dict[str, Any]:
        captured["parent_id_or_path"] = parent_id_or_path
        captured["kw"] = kw
        return {
            "children": [],
            "revision": "",
            "continuation_token": "",
        }

    monkeypatch.setattr(files, "list_files", fake_list)
    return captured


@pytest.fixture
def patched_list_files_recursive(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    captured: dict[str, Any] = {}

    async def fake_list_recursive(parent_id_or_path: str, **kw: Any) -> dict[str, Any]:
        captured["parent_id_or_path"] = parent_id_or_path
        captured["kw"] = kw
        return {"files": []}

    monkeypatch.setattr(files, "list_files_recursive", fake_list_recursive)
    return captured


@pytest.mark.asyncio
async def test_list_files_tool_passes_parent_id_or_path(
    patched_list_files: dict[str, Any],
) -> None:
    mcp = FastMCP(name="test-files-list")
    files.register_module(mcp)

    await mcp.call_tool(
        "list_files",
        {"parent_id_or_path": "/krk-iu", "limit": 10},
    )

    assert patched_list_files["parent_id_or_path"] == "/krk-iu"
    assert patched_list_files["kw"].get("limit") == 10


@pytest.mark.asyncio
async def test_list_files_tool_rejects_path_argument(
    patched_list_files: dict[str, Any],
) -> None:
    mcp = FastMCP(name="test-files-list-reject-path")
    files.register_module(mcp)

    with pytest.raises(pydantic.ValidationError):
        await mcp.call_tool("list_files", {"path": "/krk-iu", "limit": 10})

    assert "parent_id_or_path" not in patched_list_files


@pytest.mark.asyncio
async def test_list_files_recursive_tool_passes_parent_id_or_path(
    patched_list_files_recursive: dict[str, Any],
) -> None:
    mcp = FastMCP(name="test-files-rec-list")
    files.register_module(mcp)

    await mcp.call_tool(
        "list_files_recursive",
        {"parent_id_or_path": "/krk-p/sub", "limit": 50},
    )

    assert patched_list_files_recursive["parent_id_or_path"] == "/krk-p/sub"
    assert patched_list_files_recursive["kw"].get("limit") == 50


@pytest.mark.asyncio
async def test_files_module_registers_set_file_xattrs() -> None:
    mcp = FastMCP(name="test-files-metadata")
    files.register_module(mcp)
    tools = await mcp.list_tools()
    tool_names = {t.name for t in tools}
    assert "set_file_xattrs" in tool_names
    assert "set_file_metadata" in tool_names

    meta = next(t for t in tools if t.name == "set_file_metadata")
    params = meta.parameters or {}
    mtype_schema = params.get("properties", {}).get("metadata_type", {})
    assert set(mtype_schema.get("enum", [])) == {"json", "rdf"}

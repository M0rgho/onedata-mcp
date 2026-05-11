"""MCP registrations for the files module."""

from __future__ import annotations

import pytest
from fastmcp import FastMCP

from onedata_mcp.modules import files


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

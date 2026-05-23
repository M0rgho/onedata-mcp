"""MCP registrations for the harvesters module."""

from __future__ import annotations

import pytest
from fastmcp import FastMCP

from onedata_mcp.modules import harvesters


@pytest.mark.asyncio
async def test_query_harvester_index_schema_is_flat() -> None:
    mcp = FastMCP(name="test-harvesters")
    harvesters.register_module(mcp)
    tools = await mcp.list_tools()
    meta = next(t for t in tools if t.name == "query_harvester_index")
    params = meta.parameters or {}
    props = params.get("properties", {})
    assert set(props) == {"harvester_id", "index_id", "method", "path", "body"}
    assert set(props["method"].get("enum", [])) == {"get", "post"}
    assert params.get("required") == ["harvester_id", "index_id", "method", "path"]
    body = props["body"]
    body_types = {body.get("type")}
    for branch in body.get("anyOf", ()):
        body_types.add(branch.get("type"))
    assert "object" in body_types
    assert "$defs" not in params or "HarvesterQuery" not in params.get("$defs", {})

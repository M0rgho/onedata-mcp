"""MCP registrations for the harvesters module."""

from __future__ import annotations

import pytest
from fastmcp import FastMCP

from onedata_mcp.modules import harvesters


@pytest.mark.asyncio
async def test_query_harvester_index_schema_uses_nested_query() -> None:
    mcp = FastMCP(name="test-harvesters")
    harvesters.register_module(mcp)
    tools = await mcp.list_tools()
    meta = next(t for t in tools if t.name == "query_harvester_index")
    params = meta.parameters or {}
    props = params.get("properties", {})
    assert set(props) == {"harvester_id", "index_id", "query"}
    assert params.get("required") == ["harvester_id", "index_id", "query"]
    query = props["query"]
    query_props = query.get("properties", {})
    assert set(query_props) == {"method", "path", "body"}
    assert set(query_props["method"].get("enum", [])) == {"get", "post"}
    assert query.get("required") == ["method", "path"]
    body = query_props["body"]
    body_types = {body.get("type")}
    for branch in body.get("anyOf", ()):
        body_types.add(branch.get("type"))
    assert "object" in body_types

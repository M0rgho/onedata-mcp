"""Unit tests for mutating MCP tool guard."""

from __future__ import annotations

import pytest
from fastmcp import FastMCP
from mcp_write_guard import (
    McpWriteGuardError,
    check_mcp_tool_allowed,
    guarded_call_tool,
    mcp_write_guard,
    set_allowed_write_tools,
    write_guard_disabled,
)

from onedata_mcp.token_policy import WRITE_TOOL_NAMES


@pytest.fixture
def recording_mcp() -> FastMCP:
    mcp = FastMCP("guard-test")

    @mcp.tool(name="create_file")
    async def _create_file() -> str:
        return "created"

    @mcp.tool(name="list_files")
    async def _list_files() -> str:
        return "listed"

    return mcp


def test_guard_disabled_by_default_in_unit_tests() -> None:
    assert write_guard_disabled()


def test_blocks_unexpected_write_tool() -> None:
    with mcp_write_guard(frozenset()):
        with pytest.raises(McpWriteGuardError, match="create_file"):
            check_mcp_tool_allowed("create_file")
        check_mcp_tool_allowed("list_files")


def test_allows_declared_write_tools() -> None:
    with mcp_write_guard(frozenset({"create_file"})):
        check_mcp_tool_allowed("create_file")


@pytest.mark.asyncio
async def test_guarded_call_tool_returns_error_payload(recording_mcp: FastMCP) -> None:
    with mcp_write_guard(frozenset()), pytest.raises(McpWriteGuardError):
        await guarded_call_tool(recording_mcp, "create_file", {})


@pytest.mark.asyncio
async def test_guarded_call_tool_passes_when_allowed(recording_mcp: FastMCP) -> None:
    with mcp_write_guard(WRITE_TOOL_NAMES):
        result = await guarded_call_tool(recording_mcp, "create_file", {})
        assert result is not None


def test_guard_disabled_when_policy_is_none() -> None:
    token = set_allowed_write_tools(None)
    try:
        check_mcp_tool_allowed("create_file")
    finally:
        from mcp_write_guard import reset_allowed_write_tools

        reset_allowed_write_tools(token)

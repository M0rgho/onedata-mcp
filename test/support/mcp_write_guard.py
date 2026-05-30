"""Fail fast when tests invoke mutating MCP tools without opting in."""

from __future__ import annotations

import json
from contextlib import contextmanager
from contextvars import ContextVar, Token
from typing import Any

from fastmcp import FastMCP
from fastmcp.exceptions import ToolError
from tool_serialization import tool_result_to_text

from onedata_mcp.token_policy import WRITE_TOOL_NAMES

# ``None`` = guard disabled (e.g. unit tests). ``frozenset()`` = deny all write tools.
_allowed_write_tools: ContextVar[frozenset[str] | None] = ContextVar(
    "mcp_allowed_write_tools",
    default=None,
)


class McpWriteGuardError(Exception):
    """Raised when a mutating tool is invoked outside the test's declared allowance."""

    def __init__(self, tool_name: str, *, allowed: frozenset[str]) -> None:
        self.tool_name = tool_name
        self.allowed = allowed
        if allowed:
            hint = f"Allowed mutating tools for this test: {', '.join(sorted(allowed))}."
        else:
            hint = (
                "This test did not opt in to mutating MCP tools. "
                "Add @pytest.mark.e2e_isolated_confined_write, "
                "@pytest.mark.allow_mcp_write_tools('create_file', ...), "
                "or scenario.allowed_write_tools for Forge runs."
            )
        super().__init__(
            f"MCP tool {tool_name!r} is blocked in this test (unexpected write). {hint}"
        )


def write_guard_disabled() -> bool:
    return _allowed_write_tools.get() is None


def current_allowed_write_tools() -> frozenset[str] | None:
    return _allowed_write_tools.get()


def set_allowed_write_tools(allowed: frozenset[str] | None) -> Token:
    return _allowed_write_tools.set(allowed)


def reset_allowed_write_tools(token: Token) -> None:
    _allowed_write_tools.reset(token)


@contextmanager
def mcp_write_guard(allowed: frozenset[str] | None):
    """Temporarily set the write-tool policy (``None`` disables the guard)."""

    token = set_allowed_write_tools(allowed)
    try:
        yield
    finally:
        reset_allowed_write_tools(token)


def check_mcp_tool_allowed(tool_name: str) -> None:
    allowed = _allowed_write_tools.get()
    if allowed is None or tool_name not in WRITE_TOOL_NAMES:
        return
    if tool_name not in allowed:
        raise McpWriteGuardError(tool_name, allowed=allowed)


async def guarded_call_tool(
    app: FastMCP,
    tool_name: str,
    arguments: dict[str, Any],
) -> Any:
    check_mcp_tool_allowed(tool_name)
    return await app.call_tool(tool_name, arguments)


async def guarded_dispatch_mcp(
    app: FastMCP,
    tool_name: str,
    arguments: dict[str, Any],
) -> tuple[str, bool, str | None]:
    """Same contract as ``forge_harness._dispatch_mcp`` (JSON text, ok flag, error)."""

    try:
        check_mcp_tool_allowed(tool_name)
    except McpWriteGuardError as exc:
        err = str(exc)
        return json.dumps({"error": err}, ensure_ascii=False), False, err

    try:
        result = await app.call_tool(tool_name, arguments)
        return tool_result_to_text(result), True, None
    except ToolError as e:
        err = str(e)
        return json.dumps({"error": err}, ensure_ascii=False), False, err
    except Exception as e:
        err = str(e)
        return json.dumps({"error": err}, ensure_ascii=False), False, err


def merge_write_policy_with_scenario(
    base: frozenset[str] | None,
    scenario_allowed: frozenset[str],
) -> frozenset[str] | None:
    if base is None:
        return None
    if not scenario_allowed:
        return base
    return base | scenario_allowed

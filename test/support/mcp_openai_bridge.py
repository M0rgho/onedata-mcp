from __future__ import annotations

from typing import Any

from fastmcp import FastMCP


async def list_all_mcp_tools(app: FastMCP) -> list[Any]:
    tools = await app.list_tools()
    tools_sorted = sorted(tools, key=lambda t: t.name)
    return tools_sorted


def fastmcp_tool_to_openai(tool: Any) -> dict[str, Any]:
    parameters = (
        tool.parameters if tool.parameters is not None else {"type": "object", "properties": {}}
    )
    return {
        "type": "function",
        "function": {
            "name": tool.name,
            "description": tool.description or "",
            "parameters": parameters,
        },
    }


async def build_openai_tools_filtered(app: FastMCP, names: frozenset[str]) -> list[dict[str, Any]]:
    all_tools = await list_all_mcp_tools(app)
    selected = [t for t in all_tools if t.name in names]
    unknown = names - {t.name for t in selected}
    if unknown:
        raise KeyError(f"MCP server has no tools named: {sorted(unknown)}")
    return [fastmcp_tool_to_openai(t) for t in selected]


async def build_openai_tools_full(app: FastMCP) -> tuple[list[dict[str, Any]], frozenset[str]]:
    all_tools = await list_all_mcp_tools(app)
    return (
        [fastmcp_tool_to_openai(t) for t in all_tools],
        frozenset(t.name for t in all_tools),
    )

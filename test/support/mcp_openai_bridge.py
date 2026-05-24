from __future__ import annotations

from typing import Any

from fastmcp import FastMCP

DEFAULT_FORGE_AGENT_SYSTEM_PROMPT = (
    "You are a careful assistant. Use the provided tools when they help answer "
    "the user. Prefer tools over guessing when data is needed."
)


def mcp_server_instructions_text(app: FastMCP) -> str:
    """MCP ``InitializeResult.instructions`` equivalent from an in-process ``FastMCP`` app."""

    raw = getattr(app, "instructions", None)
    if not isinstance(raw, str):
        return ""
    return raw.strip()


def build_forge_system_message(
    mcp_app: FastMCP,
    scenario_system_prompt: str | None,
    *,
    default_agent_prompt: str = DEFAULT_FORGE_AGENT_SYSTEM_PROMPT,
) -> tuple[str, str | None]:
    """Compose the chat system message like an MCP host (server instructions + agent prompt).

    MCP clients surface ``instructions`` from ``initialize`` to the model, typically merged
    into the system context before the session-specific system prompt. We prepend server
    instructions and append the scenario (or default) agent text, separated by a blank line.
    """

    server = mcp_server_instructions_text(mcp_app)
    agent = (scenario_system_prompt or default_agent_prompt).strip()
    if server and agent:
        return f"{server}\n\n{agent}", server
    if server:
        return server, server
    return agent or default_agent_prompt, None


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

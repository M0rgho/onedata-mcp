"""Forge system prompt composition (MCP server instructions + scenario text)."""

from __future__ import annotations

from types import SimpleNamespace

from mcp_openai_bridge import build_forge_system_message, mcp_server_instructions_text

from onedata_mcp.main import mcp


def test_mcp_server_instructions_from_live_app() -> None:
    text = mcp_server_instructions_text(mcp)
    assert "get_file_metadata" in text
    assert "query_harvester_index" in text


def test_build_forge_system_message_prepends_server_instructions() -> None:
    fake = SimpleNamespace(
        instructions="Server guidance about paths.",
    )
    composed, server_only = build_forge_system_message(
        fake,  # type: ignore[arg-type]
        "Scenario-specific rules.",
    )
    assert server_only == "Server guidance about paths."
    assert composed.startswith("Server guidance about paths.")
    assert composed.endswith("Scenario-specific rules.")
    assert "\n\n" in composed


def test_build_forge_system_message_default_agent_when_scenario_empty() -> None:
    fake = SimpleNamespace(instructions="MCP block.")
    composed, server_only = build_forge_system_message(fake, None)  # type: ignore[arg-type]
    assert server_only == "MCP block."
    assert "careful assistant" in composed

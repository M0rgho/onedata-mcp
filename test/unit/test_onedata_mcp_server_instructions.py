"""Onedata MCP server instructions (Forge merges these into the system prompt)."""

from __future__ import annotations

from onedata_mcp.main import ONEDATA_MCP_SERVER_INSTRUCTIONS


def test_server_instructions_guide_metadata_and_harvester_not_list_paging() -> None:
    text = ONEDATA_MCP_SERVER_INSTRUCTIONS
    assert "get_file_metadata" in text
    assert "query_harvester_index" in text
    assert "__onedata.fileName" in text
    assert "list_files" in text
    assert "token/offset" in text or "token" in text

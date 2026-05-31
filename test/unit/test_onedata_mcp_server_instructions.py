"""Onedata MCP server instructions (Forge merges these into the system prompt)."""

from __future__ import annotations

from onedata_mcp.main import ONEDATA_MCP_SERVER_INSTRUCTIONS


def test_server_instructions_guide_metadata_and_harvester_not_list_paging() -> None:
    text = ONEDATA_MCP_SERVER_INSTRUCTIONS
    assert "get_file_metadata" in text
    assert "get_harvester_index_schema" in text
    assert "query_harvester_index" in text
    assert "Before searching" in text
    assert text.index("get_harvester_index_schema") < text.index("_mapping")
    assert "_mapping" in text
    assert "__onedata.fileName.keyword" in text
    assert "list_files" in text
    assert "token/offset" in text or "token" in text


def test_server_instructions_zero_hits_retry_protocol() -> None:
    text = ONEDATA_MCP_SERVER_INSTRUCTIONS
    assert "What to do when a query returns zero hits" in text
    assert "get_harvester_index_schema" in text
    assert "mappings.properties" in text
    assert "match_all" in text
    assert "Do not add `.keyword`" in text

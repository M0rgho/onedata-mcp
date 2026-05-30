"""Shared Forge E2E configuration for ``github_dataset`` harvester scenarios."""

from __future__ import annotations

import pytest
from e2e_types import ForgeRunResult
from env_checks import forge_credentials_available, onedata_credentials_available

GITHUB_FORGE_USER_SYSTEM = (
    "You help people work with their Onedata storage: spaces, files, and harvester search "
    "indexes. Answer from live lookups; do not invent harvester ids, counts, or field names. "
    "In final replies use plain digits for numbers (12345), never thousands separators "
    "(not 12,345). For timestamps and mtimes report the raw Unix epoch seconds from the "
    "tool (e.g. 1774476088), not formatted dates or times (not 2025-12-31 23:48:08 UTC). "
    "For all repos under a GitHub owner, filter with repo.name prefix Owner/ (owner/repo "
    "slugs), not org.login — org is often missing on user-owned repos. "
    "Include every fact the user asked for (names, logins, counts, filenames, mtimes)."
)

FILE_LOOKUP_TOOLS = frozenset({"get_file_attributes", "list_files", "get_file_id"})

FILE_METADATA_TOOLS = frozenset({"get_file_metadata", "get_file_id", "get_file_attributes"})

HARVESTER_TOOLS = frozenset(
    {
        "list_user_harvesters",
        "get_harvester_index_schema",
        "query_harvester_index",
        "list_available_spaces",
        "list_files",
        "get_file_attributes",
        "get_file_metadata",
    }
)

GITHUB_FORGE_MAX_TOKENS = 8192
GITHUB_FORGE_MAX_TOOL_ROUNDS = 24
GITHUB_FORGE_HARD_MAX_TOOL_ROUNDS = 32

# Researched on shared github_dataset / github-index (2026-05), file github_event_40063.dat:
# payload.commits[0].author.email is in JSON metadata and indexed _source, but
# term on payload.commits.author.email → 0 hits (not mapped for search).
GITHUB_JSON_FIELD_NOT_INDEXED_EXAMPLE = {
    "actor_login": "RealCatDev",
    "repo_slug": "NucTe/ULang",
    "event_basename": "github_event_40063.dat",
    "commit_message": "Integrated new Result/Error system",
    "prompt_field_label": "commit author email",
    "index_term_field": "payload.commits.author.email",
    "json_value": "real.catdev@gmail.com",
    "file_creation_epoch": 1774476665,
}

GITHUB_FORGE_PYTESTMARK = [
    pytest.mark.asyncio,
    pytest.mark.e2e,
    pytest.mark.shared_tenant,
    pytest.mark.onedata_integration,
    pytest.mark.skipif(
        not forge_credentials_available(),
        reason="PLGRID_FORGE_API_KEY and PLGRID_FORGE_MODEL required",
    ),
    pytest.mark.skipif(
        not onedata_credentials_available(),
        reason="Full Onedata credentials required",
    ),
]


def assert_successful_harvester_queries(run: ForgeRunResult) -> None:
    assert any(c.ok for c in run.metrics.tool_calls), "No successful MCP tool calls"
    es_ok = [m for m in run.metrics.tool_calls if m.tool_name == "query_harvester_index" and m.ok]
    assert es_ok, "Expected at least one successful query_harvester_index"

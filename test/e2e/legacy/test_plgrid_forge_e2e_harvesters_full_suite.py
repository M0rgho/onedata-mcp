"""Harvester scenarios with an enlarged tool-pack (minimal vs full context)."""

from __future__ import annotations

from typing import Any

import pytest
from assertions_lib import assert_required_tools_and_optional_policy
from e2e_types import E2EScenario
from env_checks import forge_credentials_available, onedata_credentials_available
from forge_harness import run_forge_scenario

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.legacy,
    pytest.mark.e2e,
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

HARVESTER_SUITE = frozenset(
    {
        "list_available_spaces",
        "list_user_harvesters",
        "get_harvester_index_schema",
        "query_harvester_index",
    }
)


@pytest.mark.parametrize("tool_context_mode", ["minimal", "full"])
async def test_harvesters_full_suite_parametrized(
    request: Any,
    mcp_application: Any,
    forge_api_key: str,
    forge_model: str,
    forge_base_url: str,
    tool_context_mode: str,
) -> None:
    scenario = E2EScenario(
        name="harvester-full-suite-twice-named",
        user_prompt=(
            "I need insight from the harvester that ingests our openfoodfacts-images "
            "workspace—specifically from its generic search index (the one normally "
            "used for broad file metadata lookup). "
            "Discover the index schema with the tools, assemble a small valid request "
            "that matches what the plugin expects, and run it. "
            "You may list spaces or harvesters if that helps orient you. "
            "Summarise the notable fields or values in the response."
        ),
        required_tools=frozenset({"get_harvester_index_schema", "query_harvester_index"}),
        allowed_tools_for_minimal_context=HARVESTER_SUITE,
        max_tokens=4096,
        max_tool_rounds=22,
    )
    full_or_minimal = await run_forge_scenario(
        scenario=scenario,
        mcp_app=mcp_application,
        tool_context_mode=tool_context_mode,  # type: ignore[arg-type]
        forge_api_key=forge_api_key,
        forge_base_url=forge_base_url,
        model=forge_model,
        pytest_request=request,
    )
    assert_required_tools_and_optional_policy(full_or_minimal)
    assert full_or_minimal.metrics.required_tools_satisfied
    assert (full_or_minimal.final_assistant_text or "").strip()
    if tool_context_mode == "minimal":
        assert full_or_minimal.metrics.tools_in_context_count == len(HARVESTER_SUITE)
    else:
        assert full_or_minimal.metrics.tools_in_context_count >= 15

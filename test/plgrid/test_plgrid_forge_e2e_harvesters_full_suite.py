"""Alias module: mirrors plan naming for harvester scenarios with enlarged tool-pack."""

from __future__ import annotations

from typing import Any

import pytest
from assertions_lib import assert_required_tools_and_optional_policy
from e2e_types import E2EScenario
from env_checks import forge_credentials_available, onedata_credentials_available
from forge_harness import run_forge_scenario

pytestmark = [
    pytest.mark.asyncio,
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
        "list_user_spaces",
        "list_user_harvesters",
        "get_harvester_index_schema",
        "query_harvester_index",
        "list_marketplace_spaces",
    }
)


_EXPECTED_HARVESTER_ID = "38aead36531afe751f19ee8dbc1de4d7chb7d6"
_EXPECTED_HARVESTER_INDEX_ID = "df3a594999a498af355cf487e28fec59chdedf"


@pytest.mark.parametrize("tool_context_mode", ["minimal", "full"])
async def test_harvesters_full_suite_parametrized(
    request: Any,
    mcp_application: Any,
    forge_api_key: str,
    forge_model: str,
    forge_base_url: str,
    tool_context_mode: str,
) -> None:
    hid, iid = _EXPECTED_HARVESTER_ID, _EXPECTED_HARVESTER_INDEX_ID
    scenario = E2EScenario(
        name="harvester-full-suite-twice-named",
        user_prompt=(
            f"I need insight from harvester index data for harvester `{hid}` "
            f"and index `{iid}`. "
            "Discover the index schema using the tools, then build a valid query "
            "yourself and run it. "
            "You may look at related context (spaces, harvesters) if that helps. "
            "Summarise the notable fields or values in the response."
        ),
        required_tools=frozenset({"get_harvester_index_schema", "query_harvester_index"}),
        allowed_tools_for_minimal_context=HARVESTER_SUITE,
        max_tokens=3584,
        max_tool_rounds=16,
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

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

EXAMPLE_QUERY: dict[str, str] = {"method": "get", "path": "resource_id"}

_EXPECTED_HARVESTER_ID = "38aead36531afe751f19ee8dbc1de4d7chb7d6"
_EXPECTED_HARVESTER_INDEX_ID = "df3a594999a498af355cf487e28fec59chdedf"


@pytest.mark.parametrize("tool_context_mode", ["minimal", "full"])
async def test_harvesters_only_query_tool_in_context(
    request: Any,
    mcp_application: Any,
    forge_api_key: str,
    forge_model: str,
    forge_base_url: str,
    tool_context_mode: str,
) -> None:
    hid, iid = _EXPECTED_HARVESTER_ID, _EXPECTED_HARVESTER_INDEX_ID
    scenario = E2EScenario(
        name="harvester-min-tools",
        user_prompt=(
            f"I'm supposed to execute a harvester index query with harvester `{hid}`, "
            f"index `{iid}`, and body {EXAMPLE_QUERY!r}. "
            "Can you run exactly that lookup and summarise what came back?"
        ),
        required_tools=frozenset({"query_harvester_index"}),
        allowed_tools_for_minimal_context=frozenset({"query_harvester_index"}),
        max_tool_rounds=12,
    )

    outcome = await run_forge_scenario(
        scenario=scenario,
        mcp_app=mcp_application,
        tool_context_mode=tool_context_mode,  # type: ignore[arg-type]
        forge_api_key=forge_api_key,
        forge_base_url=forge_base_url,
        model=forge_model,
        pytest_request=request,
    )
    assert_required_tools_and_optional_policy(outcome)
    assert (outcome.final_assistant_text or "").strip(), "Model should summarise tool output."
    if tool_context_mode == "minimal":
        assert outcome.metrics.tools_in_context_count == 1
    else:
        assert outcome.metrics.tools_in_context_count >= 10

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

# Discovery + schema + query: model must find IDs and build the plugin payload itself.
_MINIMAL_HARVESTER_TOOLS = frozenset(
    {
        "list_user_harvesters",
        "get_harvester_index_schema",
        "query_harvester_index",
    }
)


async def test_harvesters_minimal_context_discovers_then_queries(
    request: Any,
    mcp_application: Any,
    forge_api_key: str,
    forge_model: str,
    forge_base_url: str,
) -> None:
    scenario = E2EScenario(
        name="harvester-min-tools",
        user_prompt=(
            "Query the Onedata harvester backing our openfoodfacts-images-style workspace "
            "with a straightforward index lookup, and give a brief summary of the result."
        ),
        required_tools=frozenset({"query_harvester_index"}),
        allowed_tools_for_minimal_context=_MINIMAL_HARVESTER_TOOLS,
        max_tokens=4096,
        max_tool_rounds=20,
    )

    outcome = await run_forge_scenario(
        scenario=scenario,
        mcp_app=mcp_application,
        tool_context_mode="full",
        forge_api_key=forge_api_key,
        forge_base_url=forge_base_url,
        model=forge_model,
        pytest_request=request,
    )
    assert_required_tools_and_optional_policy(outcome)
    assert (outcome.final_assistant_text or "").strip(), "Model should summarise tool output."
    assert outcome.metrics.tools_in_context_count >= 10

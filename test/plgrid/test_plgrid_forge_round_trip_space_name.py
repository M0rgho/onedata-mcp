from __future__ import annotations

from typing import Any

import pytest
from assertions_lib import (
    assert_final_answer_contains_all,
    assert_required_tools_and_optional_policy,
)
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

_EXPECTED_SPACE_NAMES_SORTED = ("krk-iu", "krk-p", "openfoodfacts-images")


@pytest.mark.parametrize("tool_context_mode", ["minimal", "full"])
async def test_round_trip_mentions_live_space_names(
    request: Any,
    mcp_application: Any,
    forge_api_key: str,
    forge_model: str,
    forge_base_url: str,
    tool_context_mode: str,
) -> None:
    scenario = E2EScenario(
        name="round-trip-space-name",
        user_prompt=(
            "Can you look up which Onedata spaces I have and list every space name "
            "that comes back? I need the names spelled exactly as returned."
        ),
        required_tools=frozenset({"list_user_spaces"}),
        allowed_tools_for_minimal_context=frozenset({"list_user_spaces"}),
        max_tokens=4096,
    )

    run = await run_forge_scenario(
        scenario=scenario,
        mcp_app=mcp_application,
        tool_context_mode=tool_context_mode,  # type: ignore[arg-type]
        forge_api_key=forge_api_key,
        forge_base_url=forge_base_url,
        model=forge_model,
        pytest_request=request,
    )
    assert_required_tools_and_optional_policy(run)
    assert run.metrics.all_tool_calls_ok
    assert_final_answer_contains_all(
        run,
        _EXPECTED_SPACE_NAMES_SORTED,
        hint="Round-trip should surface every expected space name from the tool.",
    )

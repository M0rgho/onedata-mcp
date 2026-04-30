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
from plgrid_expected_answers import EXPECTED_FILE_BASENAME

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


@pytest.mark.parametrize("tool_context_mode", ["minimal", "full"])
async def test_file_attrs_round_trip_mentions_basename(
    request: Any,
    mcp_application: Any,
    forge_api_key: str,
    forge_model: str,
    forge_base_url: str,
    tool_context_mode: str,
) -> None:
    scenario = E2EScenario(
        name="round-trip-get-file-attributes",
        user_prompt=(
            "In my Onedata krk-iu space I have a plain-text file containing the "
            "entire Bee Movie screenplay. "
            "What filename (including extension) does Onedata report for that object?"
        ),
        required_tools=frozenset({"get_file_attributes"}),
        allowed_tools_for_minimal_context=frozenset({"get_file_attributes", "list_children"}),
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
        [EXPECTED_FILE_BASENAME],
        hint="Basename must match the expected file on the reference tenant.",
    )

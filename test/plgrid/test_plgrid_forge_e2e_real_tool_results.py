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

_EXPECTED_KRK_SPACE_NAMES = ("krk-iu", "krk-p")


@pytest.mark.parametrize("tool_context_mode", ["minimal", "full"])
async def test_e2e_live_lists_spaces_and_names_krk_p_or_iu(
    request: Any,
    mcp_application: Any,
    forge_api_key: str,
    forge_model: str,
    forge_base_url: str,
    tool_context_mode: str,
) -> None:
    scenario = E2EScenario(
        name="real-spaces-single-name",
        user_prompt=(
            "What Onedata spaces do I have access to right now? "
            "Please list each space name you can see so I know what's on my account."
        ),
        required_tools=frozenset({"list_user_spaces"}),
        allowed_tools_for_minimal_context=frozenset({"list_user_spaces"}),
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
        _EXPECTED_KRK_SPACE_NAMES,
        hint="Each expected krk space name must appear in the prose answer.",
    )

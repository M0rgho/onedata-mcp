from __future__ import annotations

from typing import Any

import pytest
from assertions_lib import assert_forge_scenario_outcome, recall_for_names_in_text
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


# Reference PLGrid tenant: generic list_available_spaces answer must still name both krk spaces.
_EXPECTED_KRK_SPACES = frozenset({"krk-p", "github_dataset"})


async def test_e2e_space_list_includes_krk_without_prompting_names(
    request: Any,
    mcp_application: Any,
    forge_api_key: str,
    forge_model: str,
    forge_base_url: str,
) -> None:
    expected = _EXPECTED_KRK_SPACES
    scenario = E2EScenario(
        name="list-spaces-expect-krk-subset",
        user_prompt=(
            "Please use Onedata and tell me every workspace I'm enrolled in—"
            "just the space names, nothing else I need to act on."
        ),
        required_tools=frozenset({"list_available_spaces"}),
        allowed_tools_for_minimal_context=frozenset({"list_available_spaces"}),
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
    assert run.metrics.all_tool_calls_ok
    recall = recall_for_names_in_text(expected, run.final_assistant_text)
    assert recall >= 1.0, f"Expected all {sorted(expected)} names in answer"
    assert_forge_scenario_outcome(
        run,
        answer_fragments=sorted(expected),
        answer_hint="Both reference krk spaces must appear but were not named in the user message.",
    )

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

# Reference PLGrid tenant: oracle for list_available_spaces answers.
_EXPECTED_SPACE_NAMES_SORTED = ("krk-iu", "krk-p", "openfoodfacts-images")

_PROMPTS = [
    "Which Onedata spaces am I enrolled in?",
    "Could you tell me what Onedata workspaces I have?",
    "I'm trying to see what shared spaces are on my Onedata account—what shows up?",
]


@pytest.mark.parametrize("user_prompt", _PROMPTS)
@pytest.mark.parametrize("tool_context_mode", ["minimal", "full"])
async def test_space_lookup_prompts(
    request: Any,
    user_prompt: str,
    tool_context_mode: str,
    mcp_application: Any,
    forge_api_key: str,
    forge_model: str,
    forge_base_url: str,
) -> None:
    scenario = E2EScenario(
        name=f"space-param-{hash(user_prompt) % 10_000}",
        user_prompt=user_prompt,
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
    assert_required_tools_and_optional_policy(run)
    assert run.metrics.all_tool_calls_ok
    assert_final_answer_contains_all(
        run,
        _EXPECTED_SPACE_NAMES_SORTED,
        hint="Each expected space name must appear in prose.",
    )

from __future__ import annotations

from typing import Any

import pytest
from assertions_lib import assert_forge_scenario_outcome
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
_EXPECTED_SPACE_NAMES_SORTED = ("github_dataset", "krk-p", "openfoodfacts-images", "europeana")

_PROMPTS = [
    "Which Onedata spaces am I enrolled in?",
    "Could you tell me what Onedata workspaces I have?",
    "I'm trying to see what shared spaces are on my Onedata account—what shows up?",
]


@pytest.mark.parametrize("user_prompt", _PROMPTS)
async def test_space_lookup_prompts(
    request: Any,
    user_prompt: str,
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
    assert run.metrics.all_tool_calls_ok
    assert_forge_scenario_outcome(
        run,
        answer_fragments=_EXPECTED_SPACE_NAMES_SORTED,
        answer_hint="Each expected space name must appear in prose.",
    )

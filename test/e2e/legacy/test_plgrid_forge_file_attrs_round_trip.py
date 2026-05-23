from __future__ import annotations

from typing import Any

import pytest
from assertions_lib import assert_final_answer_contains_all
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


_ROUND_TRIP_TOOLS = frozenset({"get_file_attributes", "list_files", "list_files_recursive"})


@pytest.mark.parametrize("tool_context_mode", ["minimal", "full"])
async def test_file_attrs_round_trip_mentions_basename(
    request: Any,
    mcp_application: Any,
    forge_api_key: str,
    forge_model: str,
    forge_base_url: str,
    tool_context_mode: str,
) -> None:
    """Basename via attrs, directory listing, or recursive file list (minimal allowlist)."""
    expected_basename = "bee_movie_script"  # /krk-iu/bee_movie_script on PLGrid reference tenant

    scenario = E2EScenario(
        name="round-trip-get-file-attributes",
        user_prompt=(
            "In my Onedata krk-iu space I have a plain-text file containing the "
            "entire Bee Movie screenplay. "
            "What filename (including extension) does Onedata report for that object?"
        ),
        required_tools=frozenset(),
        allowed_tools_for_minimal_context=_ROUND_TRIP_TOOLS,
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
    hit = run.metrics.unique_tools_called & _ROUND_TRIP_TOOLS
    assert hit, (
        "Expected basename via get_file_attributes, list_files, and/or "
        f"list_files_recursive — got {sorted(run.metrics.unique_tools_called)}."
    )
    if tool_context_mode == "minimal":
        assert run.metrics.unique_tools_called <= _ROUND_TRIP_TOOLS, (
            "Minimal round-trip exposes only attrs/list tools — "
            f"got {sorted(run.metrics.unique_tools_called)}."
        )
    assert_final_answer_contains_all(
        run,
        [expected_basename],
        hint="Basename must match the expected file on the reference tenant.",
    )

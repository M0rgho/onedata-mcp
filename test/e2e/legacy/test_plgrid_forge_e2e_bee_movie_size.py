from __future__ import annotations

from typing import Any

import pytest
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


_BEE_MOVIE_SIZE_TOOLS = frozenset({"get_file_attributes", "list_files"})


async def test_e2e_reports_bee_movie_size(
    request: Any,
    mcp_application: Any,
    forge_api_key: str,
    forge_model: str,
    forge_base_url: str,
) -> None:
    """Accept ``list_files`` or ``get_file_attributes`` for screenplay file size."""
    logical_path = "/krk-iu/bee_movie_script"
    expected_size_bytes = 49474

    scenario = E2EScenario(
        name="bee-movie-file-size",
        user_prompt=(
            "In Onedata space krk-iu I store a plain-text file that is the full Bee "
            "Movie screenplay. What's the size of that file? "
            "Return the size in bytes without any formatting."
        ),
        required_tools=frozenset(),
    )
    run = await run_forge_scenario(
        scenario=scenario,
        mcp_app=mcp_application,
        forge_api_key=forge_api_key,
        forge_base_url=forge_base_url,
        model=forge_model,
        pytest_request=request,
    )
    acceptable = run.metrics.unique_tools_called & _BEE_MOVIE_SIZE_TOOLS
    assert acceptable, (
        "Expected size via get_file_attributes and/or list_files; "
        f"got {sorted(run.metrics.unique_tools_called)}."
    )
    assert run.metrics.all_tool_calls_ok
    answer = (run.final_assistant_text or "").strip()
    assert answer == str(expected_size_bytes), (
        f"Expected exact byte count for {logical_path}: {expected_size_bytes!s}. Got: {answer!r}"
    )

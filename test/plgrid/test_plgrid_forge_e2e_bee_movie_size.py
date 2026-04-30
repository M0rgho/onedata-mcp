from __future__ import annotations

from typing import Any

import pytest
from assertions_lib import assert_required_tools_and_optional_policy
from e2e_types import E2EScenario
from env_checks import forge_credentials_available, onedata_credentials_available
from forge_harness import run_forge_scenario

BEE_PATH = "/krk-iu/bee_movie_script"
_EXPECTED_FILE_SIZE_BYTES = 49474

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
async def test_e2e_reports_bee_movie_size(
    request: Any,
    mcp_application: Any,
    forge_api_key: str,
    forge_model: str,
    forge_base_url: str,
    tool_context_mode: str,
) -> None:
    scenario = E2EScenario(
        name="bee-movie-file-size",
        user_prompt=("How large is `bee_movie_script` in my `krk-iu` space—size in bytes, please?"),
        required_tools=frozenset({"get_file_attributes"}),
        allowed_tools_for_minimal_context=frozenset({"get_file_attributes"}),
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
    text = run.final_assistant_text or ""
    needle_plain = str(_EXPECTED_FILE_SIZE_BYTES)
    needle_grouped = f"{_EXPECTED_FILE_SIZE_BYTES:,}"
    lowered = text.lower()
    assert needle_plain in lowered or needle_grouped.lower() in lowered, (
        f"Expected byte size {_EXPECTED_FILE_SIZE_BYTES} "
        f"({needle_plain} or {needle_grouped}) for {BEE_PATH} in prose. "
        f"Got: {text[:900]!r}"
    )

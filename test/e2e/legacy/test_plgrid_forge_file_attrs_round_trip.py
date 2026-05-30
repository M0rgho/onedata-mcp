from __future__ import annotations

from typing import Any

import pytest
from assertions_lib import assert_final_answer_contains_all
from e2e_types import E2EScenario
from env_checks import forge_credentials_available, onedata_credentials_available
from legacy_forge import run_legacy_forge_scenario

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


async def test_file_attrs_round_trip_mentions_basename(
    request: Any,
    mcp_application: Any,
    forge_api_key: str,
    forge_model: str,
    forge_base_url: str,
) -> None:
    """Basename via attrs, directory listing, or recursive file list (minimal allowlist)."""
    expected_basename = "github_event_11898.dat"

    scenario = E2EScenario(
        name="round-trip-get-file-attributes",
        user_prompt=(
            "In Onedata space github_dataset, under the github_dataset directory, "
            f"I have a GitHub archive file named {expected_basename}. "
            "What filename (including extension) does Onedata report for that object?"
        ),
        required_tools=frozenset(),
    )

    run = await run_legacy_forge_scenario(
        scenario=scenario,
        mcp_app=mcp_application,
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
    assert_final_answer_contains_all(
        run,
        [expected_basename],
        hint="Basename must match the expected file on the reference tenant.",
    )

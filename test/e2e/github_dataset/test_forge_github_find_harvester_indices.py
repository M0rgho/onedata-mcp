"""Forge: find all search index ids for the GitHub harvester on github_dataset."""

from __future__ import annotations

from typing import Any

import pytest
from assertions_lib import assert_forge_scenario_outcome, assert_required_tools_and_optional_policy
from e2e_types import E2EScenario
from github_dataset_harvester import (
    GITHUB_DATASET_SPACE,
    discover_github_harvester_index_ids,
    index_ids_from_harvester_row,
)
from github_forge_e2e import (
    GITHUB_FORGE_MAX_TOKENS,
    GITHUB_FORGE_PYTESTMARK,
    GITHUB_FORGE_USER_SYSTEM,
)
from legacy_forge import run_shared_forge_scenario
from plgrid_ground_truth import mcp_tool_json_result

pytestmark = GITHUB_FORGE_PYTESTMARK


@pytest.mark.e2e_scenario("find-github-harvester-indices")
async def test_find_github_harvester_indices(
    request: Any,
    mcp_application: Any,
    forge_api_key: str,
    forge_model: str,
    forge_base_url: str,
) -> None:
    oracle_harvester_id, oracle_index_ids = await discover_github_harvester_index_ids(
        mcp_application
    )

    async def verify(app: Any) -> None:
        harvester_id, index_ids = await discover_github_harvester_index_ids(app)
        assert harvester_id == oracle_harvester_id
        assert index_ids == oracle_index_ids

        rows = await mcp_tool_json_result(
            app,
            "list_user_harvesters",
            {"space_name": GITHUB_DATASET_SPACE},
        )
        assert isinstance(rows, list)
        harvester = next(
            row for row in rows if isinstance(row, dict) and row.get("harvesterId") == harvester_id
        )
        assert index_ids_from_harvester_row(harvester) == oracle_index_ids

    scenario = E2EScenario(
        name="find-github-harvester-indices",
        system_prompt=GITHUB_FORGE_USER_SYSTEM,
        user_prompt=(
            f"I work in the {GITHUB_DATASET_SPACE} space. "
            "Find the GitHub-related harvester configured for this space and list every "
            "search index id it exposes."
        ),
        required_tools=frozenset({"list_user_harvesters"}),
        max_tokens=GITHUB_FORGE_MAX_TOKENS,
        max_tool_rounds=16,
    )
    run = await run_shared_forge_scenario(
        scenario=scenario,
        mcp_app=mcp_application,
        forge_api_key=forge_api_key,
        forge_base_url=forge_base_url,
        model=forge_model,
        pytest_request=request,
        verify_state=verify,
    )
    assert_required_tools_and_optional_policy(run)
    assert_forge_scenario_outcome(
        run,
        answer_fragments=tuple(sorted(oracle_index_ids)),
        answer_hint="Final reply must include every index id for the GitHub harvester.",
    )

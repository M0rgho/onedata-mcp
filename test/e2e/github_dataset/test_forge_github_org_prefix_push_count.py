"""Forge: PushEvent count across all repos under a GitHub owner prefix."""

from __future__ import annotations

from typing import Any

import pytest
from assertions_lib import assert_forge_scenario_outcome
from e2e_types import E2EScenario
from github_dataset_harvester import (
    GITHUB_DATASET_SPACE,
    count_push_events_by_org_prefix,
    discover_org_prefix_with_min_pushes,
)
from github_forge_e2e import (
    GITHUB_FORGE_HARD_MAX_TOOL_ROUNDS,
    GITHUB_FORGE_MAX_TOKENS,
    GITHUB_FORGE_PYTESTMARK,
    GITHUB_FORGE_USER_SYSTEM,
    assert_successful_harvester_queries,
)
from legacy_forge import run_shared_forge_scenario

pytestmark = GITHUB_FORGE_PYTESTMARK


@pytest.mark.e2e_scenario("github-org-prefix-push-count")
async def test_forge_github_org_prefix_push_count(
    request: Any,
    mcp_application: Any,
    forge_api_key: str,
    forge_model: str,
    forge_base_url: str,
    github_harvester_bundle: tuple[str, str, str],
    github_org_prefix_oracle: tuple[str, int, int],
) -> None:
    org_login, expected_count, repo_count = github_org_prefix_oracle
    harvester_id, index_id, _space_id = github_harvester_bundle

    async def verify(app: Any) -> None:
        found_org, found_count, found_repos = await discover_org_prefix_with_min_pushes(
            app, harvester_id, index_id, min_pushes=100
        )
        assert found_org == org_login
        assert found_count == expected_count
        assert found_repos == repo_count
        assert expected_count == await count_push_events_by_org_prefix(
            app, harvester_id, index_id, org_login
        )
        assert repo_count >= 1

    scenario = E2EScenario(
        name="forge-github-org-prefix-push-count",
        system_prompt=GITHUB_FORGE_USER_SYSTEM,
        user_prompt=(
            f"In {GITHUB_DATASET_SPACE}'s harvester search catalog, how many PushEvent "
            f"records are indexed across **all** repositories owned by the GitHub organization "
            f"{org_login!r} (every repo under that owner prefix)? Reply with the organization "
            "name and the total count."
        ),
        required_tools=frozenset({"query_harvester_index"}),
        max_tokens=GITHUB_FORGE_MAX_TOKENS,
        max_tool_rounds=GITHUB_FORGE_HARD_MAX_TOOL_ROUNDS,
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
    assert_successful_harvester_queries(run)
    assert_forge_scenario_outcome(
        run,
        answer_fragments=(org_login, str(expected_count)),
        answer_hint="Answer should name the GitHub organization and the PushEvent count.",
    )

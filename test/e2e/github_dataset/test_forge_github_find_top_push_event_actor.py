"""Forge: top PushEvent contributor and count."""

from __future__ import annotations

from typing import Any

import pytest
from assertions_lib import assert_forge_scenario_outcome
from e2e_types import E2EScenario
from github_dataset_harvester import (
    GITHUB_DATASET_SPACE,
    count_push_events_by_actor_login,
    discover_top_push_event_actor,
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


@pytest.mark.e2e_scenario("github-find-top-push-event-actor")
async def test_forge_github_top_push_event_actor(
    request: Any,
    mcp_application: Any,
    forge_api_key: str,
    forge_model: str,
    forge_base_url: str,
    github_harvester_bundle: tuple[str, str, str],
    github_top_push_actor_oracle: tuple[str, int],
) -> None:
    harvester_id, index_id, _space_id = github_harvester_bundle
    expected_login, expected_count = github_top_push_actor_oracle

    async def verify(app: Any) -> None:
        login, count = await discover_top_push_event_actor(app, harvester_id, index_id)
        assert login == expected_login
        assert count == expected_count
        assert count == await count_push_events_by_actor_login(app, harvester_id, index_id, login)

    scenario = E2EScenario(
        name="forge-find-github-top-push-event-actor",
        system_prompt=GITHUB_FORGE_USER_SYSTEM,
        user_prompt=(
            f"In the {GITHUB_DATASET_SPACE} space find and report the GitHub account with the highest number of PushEvent records."
        ),
        required_tools=frozenset({"list_user_harvesters", "query_harvester_index"}),
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
        answer_fragments=(str(expected_count), expected_login),
        answer_hint="Answer should name the top PushEvent contributor and their count.",
    )

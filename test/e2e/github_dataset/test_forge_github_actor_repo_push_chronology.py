"""Forge: 1st and 5th chronological PushEvent files for actor + repo."""

from __future__ import annotations

from typing import Any

import pytest
from assertions_lib import assert_forge_scenario_outcome
from e2e_types import E2EScenario
from github_dataset_harvester import (
    GITHUB_DATASET_SPACE,
    discover_actor_repo_push_chronology_files,
    discover_actor_repo_push_pair,
)
from github_forge_e2e import (
    FILE_LOOKUP_TOOLS,
    GITHUB_FORGE_HARD_MAX_TOOL_ROUNDS,
    GITHUB_FORGE_MAX_TOKENS,
    GITHUB_FORGE_PYTESTMARK,
    GITHUB_FORGE_USER_SYSTEM,
    HARVESTER_TOOLS,
    assert_successful_harvester_queries,
)
from legacy_forge import run_shared_forge_scenario

pytestmark = GITHUB_FORGE_PYTESTMARK


@pytest.mark.e2e_scenario("github-actor-repo-push-chronology")
async def test_forge_github_actor_repo_push_chronology(
    request: Any,
    mcp_application: Any,
    forge_api_key: str,
    forge_model: str,
    forge_base_url: str,
    github_harvester_bundle: tuple[str, str, str],
    github_actor_repo_chronology_oracle: tuple[str, str, int, str, Any, str, Any],
) -> None:
    actor_login, repo_slug, _push_count, exp_first, exp_first_mtime, exp_fifth, exp_fifth_mtime = (
        github_actor_repo_chronology_oracle
    )
    harvester_id, index_id, _space_id = github_harvester_bundle

    async def verify(app: Any) -> None:
        login, repo, count = await discover_actor_repo_push_pair(
            app, harvester_id, index_id, min_pushes=5
        )
        assert login == actor_login
        assert repo == repo_slug
        assert count >= 5
        (
            first_base,
            first_mtime,
            fifth_base,
            fifth_mtime,
        ) = await discover_actor_repo_push_chronology_files(
            app, harvester_id, index_id, login, repo
        )
        assert first_base == exp_first
        assert first_mtime == exp_first_mtime
        assert fifth_base == exp_fifth
        assert fifth_mtime == exp_fifth_mtime

    scenario = E2EScenario(
        name="forge-github-actor-repo-push-chronology",
        system_prompt=GITHUB_FORGE_USER_SYSTEM,
        user_prompt=(
            f"I'm reconciling archived pushes in {GITHUB_DATASET_SPACE} for contributor "
            f"{actor_login!r} on repository {repo_slug!r}. In chronological order, what are "
            "the .dat filenames and provider last-modified times for their very first push "
            "to that repo, and again for their fifth push to the same repo? "
            "List both pairs clearly."
        ),
        required_tools=frozenset({"query_harvester_index"}),
        allowed_tools_for_minimal_context=HARVESTER_TOOLS,
        max_tokens=GITHUB_FORGE_MAX_TOKENS,
        max_tool_rounds=GITHUB_FORGE_HARD_MAX_TOOL_ROUNDS,
    )
    run = await run_shared_forge_scenario(
        scenario=scenario,
        mcp_app=mcp_application,
        tool_context_mode="full",
        forge_api_key=forge_api_key,
        forge_base_url=forge_base_url,
        model=forge_model,
        pytest_request=request,
        verify_state=verify,
    )
    assert_successful_harvester_queries(run)
    assert_forge_scenario_outcome(
        run,
        answer_fragments=(
            actor_login,
            repo_slug,
            exp_first,
            str(exp_first_mtime),
            exp_fifth,
            str(exp_fifth_mtime),
        ),
        any_of=(FILE_LOOKUP_TOOLS,),
        answer_hint="Answer should include repo, both filenames, and both mtimes.",
    )

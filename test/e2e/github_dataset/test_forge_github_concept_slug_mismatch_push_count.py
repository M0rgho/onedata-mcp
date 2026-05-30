"""Forge: internal nickname vs repository slug fragment."""

from __future__ import annotations

from typing import Any

import pytest
from assertions_lib import assert_forge_scenario_outcome
from e2e_types import E2EScenario
from github_dataset_harvester import (
    GITHUB_DATASET_SPACE,
    count_push_events_by_repo_slug,
    discover_concept_slug_mismatch_pair,
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


@pytest.mark.e2e_scenario("github-concept-slug-mismatch-push-count")
async def test_forge_github_concept_slug_mismatch_push_count(
    request: Any,
    mcp_application: Any,
    forge_api_key: str,
    forge_model: str,
    forge_base_url: str,
    github_harvester_bundle: tuple[str, str, str],
    github_concept_slug_mismatch_oracle: tuple[str, str, str, int],
) -> None:
    concept, slug_fragment, repo_slug, expected_count = github_concept_slug_mismatch_oracle
    harvester_id, index_id, _space_id = github_harvester_bundle
    assert concept.lower() not in repo_slug.lower()
    assert slug_fragment.lower() in repo_slug.lower()

    async def verify(app: Any) -> None:
        (
            found_concept,
            found_fragment,
            found_repo,
            found_count,
        ) = await discover_concept_slug_mismatch_pair(app, harvester_id, index_id)
        assert found_concept == concept
        assert found_fragment == slug_fragment
        assert found_repo == repo_slug
        assert found_count == expected_count
        assert expected_count == await count_push_events_by_repo_slug(
            app, harvester_id, index_id, repo_slug
        )

    scenario = E2EScenario(
        name="forge-github-concept-slug-mismatch-push-count",
        system_prompt=GITHUB_FORGE_USER_SYSTEM,
        user_prompt=(
            f"In {GITHUB_DATASET_SPACE} we internally nicknamed one GitHub effort the "
            f"{concept!r} initiative, but that word does **not** appear in the repository slug "
            f"on GitHub. Find the matching repository in the harvester catalog anyway, then "
            "tell me the full owner/name slug and how many PushEvent records are indexed for it."
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
        answer_fragments=(str(expected_count), repo_slug, slug_fragment),
        answer_hint="Answer should give the repo slug, fragment visible in it, and PushEvent count.",
    )

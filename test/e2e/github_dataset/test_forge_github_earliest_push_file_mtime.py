"""Forge: earliest PushEvent file mtime for a contributor."""

from __future__ import annotations

from typing import Any

import pytest
from assertions_lib import assert_required_tools_and_optional_policy
from e2e_types import E2EScenario
from github_dataset_harvester import (
    GITHUB_DATASET_SPACE,
    discover_earliest_push_event_file_mtime,
)
from github_forge_e2e import (
    FILE_LOOKUP_TOOLS,
    GITHUB_FORGE_HARD_MAX_TOOL_ROUNDS,
    GITHUB_FORGE_MAX_TOKENS,
    GITHUB_FORGE_PYTESTMARK,
    GITHUB_FORGE_USER_SYSTEM,
    assert_successful_harvester_queries,
)
from legacy_forge import run_shared_forge_scenario

pytestmark = GITHUB_FORGE_PYTESTMARK


@pytest.mark.e2e_scenario("github-earliest-push-file-mtime")
async def test_forge_github_earliest_push_file_mtime(
    request: Any,
    mcp_application: Any,
    forge_api_key: str,
    forge_model: str,
    forge_base_url: str,
    github_harvester_bundle: tuple[str, str, str],
    github_earliest_push_mtime_oracle: tuple[str, str, str, Any],
) -> None:
    actor_login, _basename, logical_path, expected_mtime = github_earliest_push_mtime_oracle
    harvester_id, index_id, _space_id = github_harvester_bundle

    async def verify(app: Any) -> None:
        basename, path, mtime = await discover_earliest_push_event_file_mtime(
            app, harvester_id, index_id, actor_login
        )
        assert path == logical_path
        assert basename.endswith(".dat")
        assert mtime == expected_mtime

    scenario = E2EScenario(
        name="forge-github-earliest-push-file-mtime",
        system_prompt=GITHUB_FORGE_USER_SYSTEM,
        user_prompt=(
            f"I want to find the earliest PushEvent for a {actor_login!r} contributor in {GITHUB_DATASET_SPACE}. "
            "Report the filename and modified timestamp of the found file."
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
    assert_required_tools_and_optional_policy(run, any_of=(FILE_LOOKUP_TOOLS,))
    assert_successful_harvester_queries(run)

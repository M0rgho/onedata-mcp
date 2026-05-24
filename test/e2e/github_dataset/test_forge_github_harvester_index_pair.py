"""Forge: harvester overview on github_dataset."""

from __future__ import annotations

from typing import Any

import pytest
from assertions_lib import assert_required_tools_and_optional_policy
from e2e_types import E2EScenario
from github_dataset_harvester import GITHUB_DATASET_SPACE, discover_github_harvester_bundle
from github_forge_e2e import (
    GITHUB_FORGE_MAX_TOKENS,
    GITHUB_FORGE_PYTESTMARK,
    GITHUB_FORGE_USER_SYSTEM,
)
from legacy_forge import run_shared_forge_scenario

pytestmark = GITHUB_FORGE_PYTESTMARK


@pytest.mark.e2e_scenario("github-harvester-index-pair")
async def test_forge_github_harvester_index_pair(
    request: Any,
    mcp_application: Any,
    forge_api_key: str,
    forge_model: str,
    forge_base_url: str,
    github_harvester_bundle: tuple[str, str, str],
) -> None:
    async def verify(app: Any) -> None:
        discovered = await discover_github_harvester_bundle(app)
        assert discovered == github_harvester_bundle

    scenario = E2EScenario(
        name="forge-github-harvester-index-pair",
        system_prompt=GITHUB_FORGE_USER_SYSTEM,
        user_prompt=(
            f"I mainly work in the {GITHUB_DATASET_SPACE} space. "
            "What GitHub-related harvester is configured there, and which search indexes "
            "does it expose? Summarize in plain language (names and ids if you find them)."
        ),
        required_tools=frozenset({"list_user_harvesters"}),
        allowed_tools_for_minimal_context=frozenset(
            {"list_user_harvesters", "list_available_spaces"}
        ),
        max_tokens=GITHUB_FORGE_MAX_TOKENS,
        max_tool_rounds=16,
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
    assert_required_tools_and_optional_policy(run)

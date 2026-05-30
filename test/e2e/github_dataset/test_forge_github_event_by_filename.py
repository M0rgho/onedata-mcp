"""Forge: event type for a known .dat filename."""

from __future__ import annotations

from typing import Any

import pytest
from assertions_lib import assert_required_tools_and_optional_policy
from e2e_types import E2EScenario
from github_dataset_harvester import (
    GITHUB_DATASET_SPACE,
    first_search_hit,
    hit_source,
    indexed_event_type,
    mcp_harvester_search,
    onedata_meta,
)
from github_forge_e2e import (
    GITHUB_FORGE_MAX_TOKENS,
    GITHUB_FORGE_MAX_TOOL_ROUNDS,
    GITHUB_FORGE_PYTESTMARK,
    GITHUB_FORGE_USER_SYSTEM,
    assert_successful_harvester_queries,
)
from isolated_helpers import es_hits_total
from legacy_forge import run_shared_forge_scenario

pytestmark = GITHUB_FORGE_PYTESTMARK


@pytest.mark.e2e_scenario("github-event-by-filename")
async def test_forge_github_event_by_filename(
    request: Any,
    mcp_application: Any,
    forge_api_key: str,
    forge_model: str,
    forge_base_url: str,
    github_harvester_bundle: tuple[str, str, str],
    github_sample_event_basename: str,
) -> None:
    harvester_id, index_id, _space_id = github_harvester_bundle
    basename = github_sample_event_basename

    async def verify(app: Any) -> None:
        body = await mcp_harvester_search(
            app,
            harvester_id,
            index_id,
            {
                "size": 2,
                "query": {"term": {"__onedata.fileName.keyword": basename}},
                "_source": ["type", "__onedata"],
            },
        )
        assert es_hits_total(body) is not None and (es_hits_total(body) or 0) >= 1
        hit = first_search_hit(body)
        assert hit is not None
        event_type = indexed_event_type(hit_source(hit))
        assert event_type is not None
        assert onedata_meta(hit_source(hit)).get("fileName") == basename

    scenario = E2EScenario(
        name="forge-github-event-by-filename",
        system_prompt=GITHUB_FORGE_USER_SYSTEM,
        user_prompt=(
            f"In {GITHUB_DATASET_SPACE} I have an event file named {basename!r}. "
            "What GitHub event type does our harvester search catalog associate with it?"
        ),
        required_tools=frozenset({"query_harvester_index"}),
        max_tokens=GITHUB_FORGE_MAX_TOKENS,
        max_tool_rounds=GITHUB_FORGE_MAX_TOOL_ROUNDS,
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
    assert_successful_harvester_queries(run)

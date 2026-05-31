"""Forge: anchor event file → actor, event type, and same-type event count (hardcoded oracle)."""

from __future__ import annotations

from typing import Any

import pytest
from assertions_lib import assert_forge_scenario_outcome
from e2e_types import E2EScenario
from github_dataset_harvester import (
    GITHUB_DATASET_SPACE,
    first_search_hit,
    hit_source,
    indexed_actor_login,
    indexed_event_type,
    mcp_harvester_search,
    onedata_meta,
)
from github_forge_e2e import (
    GITHUB_FORGE_HARD_MAX_TOOL_ROUNDS,
    GITHUB_FORGE_MAX_TOKENS,
    GITHUB_FORGE_PYTESTMARK,
    GITHUB_FORGE_USER_SYSTEM,
    assert_successful_harvester_queries,
)
from isolated_helpers import es_hits_total
from legacy_forge import run_shared_forge_scenario

pytestmark = GITHUB_FORGE_PYTESTMARK

# Researched on shared github_dataset / github-index (2026-05): dim12512a has 12_548 PushEvents
# (not github-actions[bot]). Anchor file from a term query on __onedata.fileName.keyword.
EVENT_BASENAME = "github_event_30.dat"
ACTOR_LOGIN = "dim12512a"
EVENT_TYPE = "PushEvent"
EXPECTED_SAME_TYPE_TOTAL = 12_548


async def _count_events_by_actor_and_type(
    app: Any, harvester_id: str, index_id: str, actor_login: str, event_type: str
) -> int:
    body = await mcp_harvester_search(
        app,
        harvester_id,
        index_id,
        {
            "size": 0,
            "track_total_hits": True,
            "query": {
                "bool": {
                    "must": [
                        {"term": {"type": event_type}},
                        {"term": {"actor.login": actor_login}},
                    ]
                }
            },
        },
    )
    total = es_hits_total(body)
    if total is None:
        msg = f"No hits.total for {actor_login!r} / {event_type!r}"
        raise AssertionError(msg)
    return total


@pytest.mark.e2e_scenario("find-github-event-by-filename")
async def test_find_github_event_by_filename(
    request: Any,
    mcp_application: Any,
    forge_api_key: str,
    forge_model: str,
    forge_base_url: str,
    github_harvester_bundle: tuple[str, str, str],
) -> None:
    harvester_id, index_id, _space_id = github_harvester_bundle

    async def verify(app: Any) -> None:
        body = await mcp_harvester_search(
            app,
            harvester_id,
            index_id,
            {
                "size": 2,
                "query": {"term": {"__onedata.fileName.keyword": EVENT_BASENAME}},
                "_source": ["type", "actor", "__onedata"],
            },
        )
        assert es_hits_total(body) is not None and (es_hits_total(body) or 0) >= 1
        hit = first_search_hit(body)
        assert hit is not None
        source = hit_source(hit)
        assert indexed_event_type(source) == EVENT_TYPE
        assert indexed_actor_login(source) == ACTOR_LOGIN
        assert onedata_meta(source).get("fileName") == EVENT_BASENAME
        total = await _count_events_by_actor_and_type(
            app, harvester_id, index_id, ACTOR_LOGIN, EVENT_TYPE
        )
        assert total == EXPECTED_SAME_TYPE_TOTAL

    scenario = E2EScenario(
        name="find-github-event-by-filename",
        system_prompt=GITHUB_FORGE_USER_SYSTEM,
        user_prompt=(
            f"In the {GITHUB_DATASET_SPACE} space, there is an event file named {EVENT_BASENAME!r}. "
            "First, find and report the GitHub event type for this file. "
            "Then, determine and report how many events of this same type the user referenced in the file has created in total."
            "Mention the user name in the answer"
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
        answer_fragments=(
            str(EXPECTED_SAME_TYPE_TOTAL),
            ACTOR_LOGIN,
            EVENT_TYPE,
        ),
        answer_hint=(
            "Answer should name the actor, event type, and total count of same-type events "
            f"({EXPECTED_SAME_TYPE_TOTAL})."
        ),
    )

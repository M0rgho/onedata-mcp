"""Forge: all commit SHAs from PushEvents by mmomtchev (hardcoded oracle, 2026-05 catalog)."""

from __future__ import annotations

from typing import Any

import pytest
from assertions_lib import assert_forge_scenario_outcome
from e2e_types import E2EScenario
from github_dataset_harvester import GITHUB_DATASET_SPACE, mcp_harvester_search
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

# Researched on shared github_dataset / github-index (2026-05): two PushEvents for mmomtchev
# on mmomtchev/ffmpeg (github_event_51.dat, github_event_30832.dat).
ACTOR_LOGIN = "mmomtchev"
EXPECTED_PUSH_EVENT_COUNT = 2
EXPECTED_COMMIT_HASHES: frozenset[str] = frozenset(
    {
        "ac683d7a5043b27906f6c3bf882065fae31867ad",
        "7fefb1f6405a93f8e820446624a73d13d4dd2d56",
        "9f7f57d2811ebf5bf275cc00392966ac9ac6eaca",
    }
)


def _commit_hashes_from_push_event_hits(body: dict[str, Any]) -> frozenset[str]:
    hits = body.get("hits", {}).get("hits")
    if not isinstance(hits, list):
        msg = "PushEvent search response missing hits.hits"
        raise AssertionError(msg)
    shas: set[str] = set()
    for hit in hits:
        if not isinstance(hit, dict):
            continue
        source = hit.get("_source")
        if not isinstance(source, dict):
            continue
        commits = source.get("payload", {}).get("commits")
        if not isinstance(commits, list):
            continue
        for commit in commits:
            if not isinstance(commit, dict):
                continue
            sha = commit.get("sha")
            if isinstance(sha, str) and sha:
                shas.add(sha)
    return frozenset(shas)


async def _fetch_mmomtchev_push_commit_hashes(
    app: Any, harvester_id: str, index_id: str
) -> tuple[int, frozenset[str]]:
    body = await mcp_harvester_search(
        app,
        harvester_id,
        index_id,
        {
            "size": 100,
            "track_total_hits": True,
            "query": {
                "bool": {
                    "must": [
                        {"term": {"type": "PushEvent"}},
                        {"term": {"actor.login": ACTOR_LOGIN}},
                    ]
                }
            },
            "sort": [{"created_at": "asc"}],
        },
    )
    total = es_hits_total(body)
    if total is None:
        msg = f"PushEvent count query returned no hits.total for {ACTOR_LOGIN!r}"
        raise AssertionError(msg)
    return total, _commit_hashes_from_push_event_hits(body)


@pytest.mark.e2e_scenario("find-github-push-commit-hashes")
async def test_forge_github_mmomtchev_push_commit_hashes(
    request: Any,
    mcp_application: Any,
    forge_api_key: str,
    forge_model: str,
    forge_base_url: str,
    github_harvester_bundle: tuple[str, str, str],
) -> None:
    harvester_id, index_id, _space_id = github_harvester_bundle

    async def verify(app: Any) -> None:
        push_count, commit_hashes = await _fetch_mmomtchev_push_commit_hashes(
            app, harvester_id, index_id
        )
        assert push_count == EXPECTED_PUSH_EVENT_COUNT
        assert commit_hashes == EXPECTED_COMMIT_HASHES

    scenario = E2EScenario(
        name="forge-github-push-commit-hashes",
        system_prompt=GITHUB_FORGE_USER_SYSTEM,
        user_prompt=(
            f"In {GITHUB_DATASET_SPACE} space find and list every commit "
            f"hash (SHA) that appears in PushEvent records made by GitHub user {ACTOR_LOGIN!r}. "
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
        answer_fragments=tuple(sorted(EXPECTED_COMMIT_HASHES)),
        answer_hint="Answer should list every commit SHA from mmomtchev PushEvents.",
    )

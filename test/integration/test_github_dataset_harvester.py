"""MCP integration probes for shared ``github_dataset`` / ``github-index`` (no Forge)."""

from __future__ import annotations

from typing import Any

import pytest
from env_checks import onedata_credentials_available
from github_dataset_harvester import (
    GITHUB_DATASET_DIR,
    GITHUB_INDEX_NAME,
    count_push_events_by_actor_login,
    count_push_events_by_org_prefix,
    discover_actor_repo_push_chronology_files,
    discover_actor_repo_push_pair,
    discover_github_harvester_bundle,
    discover_github_harvester_index_ids,
    discover_org_prefix_with_min_pushes,
    discover_top_push_event_actor,
    index_ids_from_harvester_row,
    mcp_harvester_search,
    schema_declares_field,
)
from github_forge_e2e import GITHUB_JSON_FIELD_NOT_INDEXED_EXAMPLE
from isolated_helpers import es_hits_total
from plgrid_ground_truth import mcp_tool_json_result

# Hardcoded oracle: ``test_forge_github_mmomtchev_push_commit_hashes.py`` (shared catalog, 2026-05).
_MMOMTCHEV_LOGIN = "mmomtchev"
_MMOMTCHEV_PUSH_EVENT_COUNT = 2
_MMOMTCHEV_COMMIT_HASHES: frozenset[str] = frozenset(
    {
        "ac683d7a5043b27906f6c3bf882065fae31867ad",
        "7fefb1f6405a93f8e820446624a73d13d4dd2d56",
        "9f7f57d2811ebf5bf275cc00392966ac9ac6eaca",
    }
)

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.onedata_integration,
    pytest.mark.shared_tenant,
    pytest.mark.skipif(
        not onedata_credentials_available(),
        reason="ONEDATA_ONEZONE_* and ONEDATA_ONEPROVIDER_* required",
    ),
]


@pytest.mark.e2e_scenario("github-harvester-index-ids")
async def test_github_harvester_lists_all_index_ids(mcp_application: Any) -> None:
    """``github-harvester-index-pair`` oracle: every index id on the GitHub harvester."""
    harvester_id, index_ids = await discover_github_harvester_index_ids(mcp_application)
    rows = await mcp_tool_json_result(
        mcp_application,
        "list_user_harvesters",
        {"space_name": "github_dataset"},
    )
    harvester = next(
        r for r in rows if isinstance(r, dict) and r.get("harvesterId") == harvester_id
    )
    assert index_ids_from_harvester_row(harvester) == index_ids
    assert GITHUB_INDEX_NAME in {
        i.get("name") for i in (harvester.get("indices") or []) if isinstance(i, dict)
    }
    github_index_id = next(
        i.get("indexId")
        for i in harvester["indices"]
        if isinstance(i, dict) and i.get("name") == GITHUB_INDEX_NAME
    )
    assert isinstance(github_index_id, str)
    assert github_index_id in index_ids


@pytest.mark.e2e_scenario("github-index-mcp-bundle")
async def test_github_index_bundle_resolves_current_index(mcp_application: Any) -> None:
    harvester_id, index_id, space_id = await discover_github_harvester_bundle(mcp_application)
    rows = await mcp_tool_json_result(
        mcp_application,
        "list_user_harvesters",
        {"space_name": "github_dataset"},
    )
    harvester = next(
        r for r in rows if isinstance(r, dict) and r.get("harvesterId") == harvester_id
    )
    index_names = {i.get("name") for i in (harvester.get("indices") or []) if isinstance(i, dict)}
    assert GITHUB_INDEX_NAME in index_names
    assert index_id == next(
        i.get("indexId")
        for i in harvester["indices"]
        if isinstance(i, dict) and i.get("name") == GITHUB_INDEX_NAME
    )
    schema = await mcp_tool_json_result(
        mcp_application,
        "get_harvester_index_schema",
        {"harvester_id": harvester_id, "index_id": index_id},
    )
    assert schema_declares_field(schema, "type")
    assert not schema_declares_field(schema, "eventType")
    assert schema_declares_field(schema, "org")
    body = await mcp_harvester_search(
        mcp_application,
        harvester_id,
        index_id,
        {"size": 0, "track_total_hits": True, "query": {"match_all": {}}},
    )
    assert (es_hits_total(body) or 0) > 1000
    assert space_id


@pytest.mark.e2e_scenario("github-index-top-push-actor")
async def test_github_index_top_push_event_actor_via_type(mcp_application: Any) -> None:
    harvester_id, index_id, _space_id = await discover_github_harvester_bundle(mcp_application)
    login, agg_count = await discover_top_push_event_actor(mcp_application, harvester_id, index_id)
    count = await count_push_events_by_actor_login(mcp_application, harvester_id, index_id, login)
    assert agg_count >= 1
    assert count == agg_count
    wrong = await mcp_harvester_search(
        mcp_application,
        harvester_id,
        index_id,
        {
            "size": 0,
            "track_total_hits": True,
            "query": {
                "bool": {
                    "must": [
                        {"term": {"eventType": "PushEvent"}},
                        {"term": {"actor.login": login}},
                    ]
                }
            },
        },
    )
    assert es_hits_total(wrong) == 0


@pytest.mark.e2e_scenario("github-index-actor-repo-chronology")
async def test_github_index_actor_repo_push_chronology_probe(mcp_application: Any) -> None:
    harvester_id, index_id, _space_id = await discover_github_harvester_bundle(mcp_application)
    login, repo, count = await discover_actor_repo_push_pair(
        mcp_application, harvester_id, index_id, min_pushes=5
    )
    assert count >= 5
    (
        first_base,
        first_created_at,
        fifth_base,
        fifth_created_at,
    ) = await discover_actor_repo_push_chronology_files(
        mcp_application, harvester_id, index_id, login, repo
    )
    assert first_base.endswith(".dat")
    assert fifth_base.endswith(".dat")
    assert first_created_at
    assert fifth_created_at


@pytest.mark.e2e_scenario("github-index-org-prefix")
async def test_github_index_org_prefix_push_count(mcp_application: Any) -> None:
    harvester_id, index_id, _space_id = await discover_github_harvester_bundle(mcp_application)
    org, agg_count, repo_count = await discover_org_prefix_with_min_pushes(
        mcp_application, harvester_id, index_id, min_pushes=100
    )
    prefix_count = await count_push_events_by_org_prefix(
        mcp_application, harvester_id, index_id, org
    )
    assert prefix_count == agg_count
    assert repo_count >= 1


@pytest.mark.e2e_scenario("github-index-gnome-org-prefix")
async def test_github_index_gnome_org_prefix_probe(mcp_application: Any) -> None:
    """Small org example (``GNOME/gobject-introspection``); prefix query, not exact ``repo.name`` term."""

    harvester_id, index_id, _space_id = await discover_github_harvester_bundle(mcp_application)
    gnome_count = await count_push_events_by_org_prefix(
        mcp_application, harvester_id, index_id, "GNOME"
    )
    assert gnome_count >= 1


# Hardcoded oracle: ``test_forge_github_event_by_filename.py`` (shared catalog, 2026-05).
_EVENT_BY_FILENAME_BASENAME = "github_event_30.dat"
_EVENT_BY_FILENAME_ACTOR = "dim12512a"
_EVENT_BY_FILENAME_TYPE = "PushEvent"
_EVENT_BY_FILENAME_SAME_TYPE_TOTAL = 12_548


@pytest.mark.e2e_scenario("github-event-by-filename")
async def test_github_event_by_filename_actor_same_type_count_hardcoded(
    mcp_application: Any,
) -> None:
    harvester_id, index_id, _space_id = await discover_github_harvester_bundle(mcp_application)
    body = await mcp_harvester_search(
        mcp_application,
        harvester_id,
        index_id,
        {
            "size": 2,
            "query": {"term": {"__onedata.fileName.keyword": _EVENT_BY_FILENAME_BASENAME}},
            "_source": ["type", "actor", "__onedata"],
        },
    )
    assert es_hits_total(body) is not None and (es_hits_total(body) or 0) >= 1
    hit = body.get("hits", {}).get("hits", [{}])[0]
    source = hit.get("_source") or {}
    assert source.get("type") == _EVENT_BY_FILENAME_TYPE
    assert (source.get("actor") or {}).get("login") == _EVENT_BY_FILENAME_ACTOR
    assert (source.get("__onedata") or {}).get("fileName") == _EVENT_BY_FILENAME_BASENAME
    count_body = await mcp_harvester_search(
        mcp_application,
        harvester_id,
        index_id,
        {
            "size": 0,
            "track_total_hits": True,
            "query": {
                "bool": {
                    "must": [
                        {"term": {"type": _EVENT_BY_FILENAME_TYPE}},
                        {"term": {"actor.login": _EVENT_BY_FILENAME_ACTOR}},
                    ]
                }
            },
        },
    )
    assert es_hits_total(count_body) == _EVENT_BY_FILENAME_SAME_TYPE_TOTAL


@pytest.mark.e2e_scenario("github-mmomtchev-push-commit-hashes")
async def test_github_mmomtchev_push_commit_hashes_hardcoded(mcp_application: Any) -> None:
    harvester_id, index_id, _space_id = await discover_github_harvester_bundle(mcp_application)
    body = await mcp_harvester_search(
        mcp_application,
        harvester_id,
        index_id,
        {
            "size": 100,
            "track_total_hits": True,
            "query": {
                "bool": {
                    "must": [
                        {"term": {"type": "PushEvent"}},
                        {"term": {"actor.login": _MMOMTCHEV_LOGIN}},
                    ]
                }
            },
        },
    )
    assert es_hits_total(body) == _MMOMTCHEV_PUSH_EVENT_COUNT
    shas: set[str] = set()
    hits = body.get("hits", {}).get("hits") or []
    for hit in hits:
        source = hit.get("_source") or {}
        for commit in source.get("payload", {}).get("commits") or []:
            sha = commit.get("sha")
            if isinstance(sha, str) and sha:
                shas.add(sha)
    assert frozenset(shas) == _MMOMTCHEV_COMMIT_HASHES


@pytest.mark.e2e_scenario("github-json-commit-email-not-indexed")
async def test_github_json_commit_author_email_hardcoded_example(mcp_application: Any) -> None:
    ex = GITHUB_JSON_FIELD_NOT_INDEXED_EXAMPLE
    path = f"{GITHUB_DATASET_DIR}/{ex['event_basename']}"
    harvester_id, index_id, _space_id = await discover_github_harvester_bundle(mcp_application)

    meta = await mcp_tool_json_result(
        mcp_application,
        "get_file_metadata",
        {"file_id_or_path": path, "metadata_types": ["json"]},
    )
    json_meta = meta.get("json") or {}
    commits = json_meta.get("payload", {}).get("commits") or []
    assert commits[0]["author"]["email"] == ex["json_value"]

    attrs = await mcp_tool_json_result(
        mcp_application,
        "get_file_attributes",
        {"file_id_or_path": path, "attributes": ["creationTime"]},
    )
    assert attrs.get("creationTime") == ex["file_creation_epoch"]

    term_email = await mcp_harvester_search(
        mcp_application,
        harvester_id,
        index_id,
        {
            "size": 0,
            "track_total_hits": True,
            "query": {"term": {ex["index_term_field"]: ex["json_value"]}},
        },
    )
    assert es_hits_total(term_email) == 0

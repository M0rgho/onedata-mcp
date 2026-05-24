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
    discover_org_prefix_with_min_pushes,
    discover_top_push_event_actor,
    mcp_harvester_search,
    schema_declares_field,
)
from github_forge_e2e import GITHUB_JSON_FIELD_NOT_INDEXED_EXAMPLE
from isolated_helpers import es_hits_total
from plgrid_ground_truth import mcp_tool_json_result

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.onedata_integration,
    pytest.mark.shared_tenant,
    pytest.mark.skipif(
        not onedata_credentials_available(),
        reason="ONEDATA_ONEZONE_* and ONEDATA_ONEPROVIDER_* required",
    ),
]


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
        first_mtime,
        fifth_base,
        fifth_mtime,
    ) = await discover_actor_repo_push_chronology_files(
        mcp_application, harvester_id, index_id, login, repo
    )
    assert first_base.endswith(".dat")
    assert fifth_base.endswith(".dat")
    assert first_mtime is not None
    assert fifth_mtime is not None


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
    """Small org example (``GNOME/gobject-introspection``); prefix query, not full slug term."""

    harvester_id, index_id, _space_id = await discover_github_harvester_bundle(mcp_application)
    gnome_count = await count_push_events_by_org_prefix(
        mcp_application, harvester_id, index_id, "GNOME"
    )
    assert gnome_count >= 1


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

"""Unit tests for github_dataset harvester helper parsing (no live Onedata)."""

from __future__ import annotations

from github_dataset_harvester import (
    GITHUB_INDEX_NAME,
    _aggregate_org_push_counts,
    _pick_github_index_id,
    _search_hits_list,
    first_search_hit,
    harvester_index_schema_properties,
    hit_source,
    indexed_actor_login,
    indexed_event_type,
    indexed_repo_name,
    onedata_meta,
    schema_declares_field,
)


def test_pick_github_index_id_finds_github_index() -> None:
    indices = [
        {"name": "generic-index", "indexId": "gen"},
        {"name": GITHUB_INDEX_NAME, "indexId": "gh"},
    ]
    assert _pick_github_index_id(indices) == "gh"


def test_pick_github_index_id_returns_none_when_missing() -> None:
    assert _pick_github_index_id([{"name": "generic-index", "indexId": "gen"}]) is None


def test_first_search_hit_extracts_source() -> None:
    body = {
        "hits": {
            "total": {"value": 1},
            "hits": [{"_source": {"type": "PushEvent", "__onedata": {"fileName": "a.dat"}}}],
        }
    }
    hit = first_search_hit(body)
    assert hit is not None
    assert indexed_event_type(hit_source(hit)) == "PushEvent"
    assert onedata_meta(hit_source(hit))["fileName"] == "a.dat"
    assert indexed_repo_name({"repo": {"name": "o/r"}}) == "o/r"


def test_schema_declares_field_in_json_string() -> None:
    payload = {"schema": '{"mappings":{"properties":{"type":{"type":"keyword"}}}}'}
    assert schema_declares_field(payload, "type")
    assert harvester_index_schema_properties(payload) == {"type": {"type": "keyword"}}


def test_harvester_index_schema_properties_parses_index_detail_wrapper() -> None:
    payload = {
        "name": "github-index",
        "indexId": "da1711974e2ebe7ff974369fe80ccf8dchbd10",
        "schema": (
            '{"mappings":{"properties":{"type":{"type":"keyword"},"__onedata":{"properties":{}}}}}'
        ),
    }
    properties = harvester_index_schema_properties(payload)
    assert set(properties) == {"type", "__onedata"}
    assert schema_declares_field(payload, "__onedata")
    assert not schema_declares_field(payload, "eventType")


def test_aggregate_org_push_counts_sums_by_owner() -> None:
    repos = [
        ("stdlib-js/foo", 10),
        ("stdlib-js/bar", 5),
        ("other/baz", 3),
    ]
    assert _aggregate_org_push_counts(repos) == {"stdlib-js": 15, "other": 3}


def test_search_hits_list_rank_selection() -> None:
    body = {
        "hits": {
            "hits": [
                {"_source": {"__onedata": {"fileName": "a.dat"}}},
                {"_source": {"__onedata": {"fileName": "b.dat"}}},
            ]
        }
    }
    hits = _search_hits_list(body)
    assert onedata_meta(hit_source(hits[1]))["fileName"] == "b.dat"


def test_indexed_actor_login() -> None:
    source = {
        "type": "PushEvent",
        "actor": {"login": "octocat"},
    }
    assert indexed_actor_login(source) == "octocat"
    assert indexed_event_type(source) == "PushEvent"

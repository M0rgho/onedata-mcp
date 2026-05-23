"""Unit tests for E2E isolated_helpers (no live Onedata)."""

from __future__ import annotations

from isolated_helpers import es_hits_total, harvester_index_for_space


def test_es_hits_total_nested_value() -> None:
    body = {"hits": {"total": {"value": 42}}}
    assert es_hits_total(body) == 42


def test_es_hits_total_int() -> None:
    assert es_hits_total({"hits": {"total": 3}}) == 3


def test_es_hits_total_unwraps_harvester_query_response() -> None:
    wrapped = {
        "code": 200,
        "headers": {},
        "body": '{"hits":{"total":{"value":1}}}',
    }
    assert es_hits_total(wrapped) == 1


def test_harvester_index_for_space_matches_attached_space() -> None:
    harvesters = [
        {
            "harvesterId": "h1",
            "attached_spaces": [{"space_id": "sp-a", "space_name": "a"}],
            "indices": [{"indexId": "idx1"}],
        }
    ]
    assert harvester_index_for_space(harvesters, space_id="sp-a") == ("h1", "idx1")

"""Unit tests for E2E oracle helpers (test/support/e2e_oracles.py)."""

from __future__ import annotations

from e2e_oracles import (
    assert_list_spaces_oracle,
    space_ids_from_listing,
    space_names_from_listing,
)


def test_space_names_and_ids_from_listing() -> None:
    rows = [
        {"spaceId": "sp-1", "name": "Alpha"},
        {"spaceId": "sp-2", "name": "Beta"},
    ]
    assert space_names_from_listing(rows) == {"Alpha", "Beta"}
    assert space_ids_from_listing(rows) == {"sp-1", "sp-2"}


def test_assert_list_spaces_oracle_accepts_single_space() -> None:
    rows = [{"spaceId": "sp-1", "name": "mcp-e2e-demo"}]
    assert_list_spaces_oracle(
        rows,
        expected_name="mcp-e2e-demo",
        expected_id="sp-1",
    )


def test_assert_list_spaces_oracle_rejects_wrong_name() -> None:
    rows = [{"spaceId": "sp-1", "name": "wrong"}]
    try:
        assert_list_spaces_oracle(rows, expected_name="right", expected_id="sp-1")
    except AssertionError as exc:
        assert "expected names" in str(exc)
    else:
        raise AssertionError("expected AssertionError for wrong name")


def test_assert_list_spaces_oracle_rejects_multiple_rows() -> None:
    rows = [
        {"spaceId": "sp-1", "name": "only"},
        {"spaceId": "sp-2", "name": "only"},
    ]
    try:
        assert_list_spaces_oracle(rows, expected_name="only", expected_id="sp-1")
    except AssertionError as exc:
        assert "exactly one space row" in str(exc)
    else:
        raise AssertionError("expected AssertionError for multiple rows")

"""Pure post-condition helpers for isolated E2E scenarios (no live Onedata)."""

from __future__ import annotations


def space_names_from_listing(rows: object) -> set[str]:
    """Extract space names from a ``list_available_spaces`` payload."""

    if not isinstance(rows, list):
        msg = f"list_available_spaces must return a list, got {type(rows).__name__}"
        raise AssertionError(msg)
    names: set[str] = set()
    for item in rows:
        if isinstance(item, dict) and isinstance(item.get("name"), str):
            names.add(item["name"])
    return names


def space_ids_from_listing(rows: object) -> set[str]:
    """Extract space ids from a ``list_available_spaces`` payload."""

    if not isinstance(rows, list):
        msg = f"list_available_spaces must return a list, got {type(rows).__name__}"
        raise AssertionError(msg)
    ids: set[str] = set()
    for item in rows:
        if isinstance(item, dict) and isinstance(item.get("spaceId"), str):
            ids.add(item["spaceId"])
    return ids


def assert_list_spaces_oracle(
    rows: object,
    *,
    expected_name: str,
    expected_id: str,
) -> None:
    """``list-spaces``: confined token sees exactly one expected space."""

    if not isinstance(rows, list):
        msg = f"list_available_spaces must return a list, got {type(rows).__name__}"
        raise AssertionError(msg)
    assert len(rows) == 1, f"expected exactly one space row, got {len(rows)}"
    names = space_names_from_listing(rows)
    ids = space_ids_from_listing(rows)
    assert names == {expected_name}, f"expected names {{{expected_name!r}}}, got {names!r}"
    assert ids == {expected_id}, f"expected ids {{{expected_id!r}}}, got {ids!r}"


def assert_paths_under_prefix(paths: list[str], prefix: str) -> None:
    for path in paths:
        assert path.startswith(prefix), f"path {path!r} does not start with {prefix!r}"

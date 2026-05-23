"""Unit tests for E2E harvester provisioning helpers."""

from __future__ import annotations

from e2e_isolated_space import isolated_scope_needs_harvester, resource_id_from_location


def test_resource_id_from_location_trailing_segment() -> None:
    location = "https://zone.example/api/v3/onezone/harvesters/abc123def456/indices/idx789"
    assert resource_id_from_location(location) == "idx789"


def test_isolated_scope_needs_harvester() -> None:
    assert isolated_scope_needs_harvester("read-state")
    assert isolated_scope_needs_harvester("harvester")
    assert not isolated_scope_needs_harvester("write-state")
    assert not isolated_scope_needs_harvester("robustness")

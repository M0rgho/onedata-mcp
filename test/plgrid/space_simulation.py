"""Shared stub payloads for simulated list_user_spaces tool calls."""

from __future__ import annotations

from typing import Any

SIMULATED_USER_SPACES: list[dict[str, Any]] = [
    {
        "name": "aurora-shared",
        "spaceId": "00000000000000000000000000000000chbbbb",
        "tags": [],
    },
    {
        "name": "polaris-archive",
        "spaceId": "00000000000000000000000000000000chcccc",
        "tags": [],
    },
]

SIMULATED_SPACE_NAMES = [entry["name"] for entry in SIMULATED_USER_SPACES]


def simulate_list_user_spaces(_args: dict[str, Any]) -> list[dict[str, Any]]:
    return SIMULATED_USER_SPACES

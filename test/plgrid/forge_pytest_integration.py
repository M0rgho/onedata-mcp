"""Hooks between pytest outcomes and Forge trace files."""

from __future__ import annotations

import pytest

# Populated after run_forge_scenario; consumed in plgrid conftest makereport hook.
LAST_FORGE_RUN = pytest.StashKey[object]()

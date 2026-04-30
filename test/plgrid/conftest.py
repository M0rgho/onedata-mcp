from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

import pytest
from dotenv import load_dotenv

_REPO_ROOT = Path(__file__).resolve().parents[2]
# So skipif + fixtures see the same vars as runtime (pytest does not load .env by itself).
load_dotenv(_REPO_ROOT / ".env")

_PLGRID_DIR = Path(__file__).resolve().parent
if str(_PLGRID_DIR) not in sys.path:
    sys.path.insert(0, str(_PLGRID_DIR))

from forge_logging import patch_forge_trace_test_result  # noqa: E402
from forge_pytest_integration import LAST_FORGE_RUN  # noqa: E402


@pytest.hookimpl(wrapper=True)
def pytest_runtest_makereport(item, call):
    hooked = yield
    rep = hooked.get_result() if hasattr(hooked, "get_result") else hooked
    if rep.when != "call":
        return hooked
    if rep.skipped:
        return hooked
    run = item.stash.get(LAST_FORGE_RUN, None)
    if run is None or run.trace_path_written is None:
        return hooked
    patch_forge_trace_test_result(run.trace_path_written, passed=bool(rep.passed))
    return hooked


@pytest.fixture(scope="session")
def forge_api_key() -> str:
    key = os.getenv("PLGRID_FORGE_API_KEY", "").strip()
    if not key:
        pytest.skip("PLGRID_FORGE_API_KEY is not set")
    return key


@pytest.fixture(scope="session")
def forge_model() -> str:
    model = os.getenv("PLGRID_FORGE_MODEL", "").strip()
    if not model:
        pytest.skip("PLGRID_FORGE_MODEL is not set")
    return model


@pytest.fixture(scope="session")
def forge_base_url() -> str:
    return os.getenv("PLGRID_FORGE_BASE_URL", "https://llmlab.plgrid.pl/api/v1").rstrip("/")


@pytest.fixture(scope="session")
def mcp_application() -> Any:
    from onedata_mcp.main import mcp

    return mcp

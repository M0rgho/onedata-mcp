from __future__ import annotations

import logging
import os
import sys
from pathlib import Path
from typing import Any

import pytest
import pytest_asyncio
from dotenv import load_dotenv

_REPO_ROOT = Path(__file__).resolve().parents[1]
# So skipif + fixtures see the same vars as runtime (pytest does not load .env by itself).
load_dotenv(_REPO_ROOT / ".env")

_SUPPORT_DIR = Path(__file__).resolve().parent / "support"
if str(_SUPPORT_DIR) not in sys.path:
    sys.path.insert(0, str(_SUPPORT_DIR))

from forge_logging import (  # noqa: E402
    flush_forge_trace_summary_csvs,
    patch_forge_trace_test_result,
)
from env_checks import onedata_credentials_available  # noqa: E402
from forge_pytest_integration import LAST_FORGE_RUN  # noqa: E402


class _SuppressFastMCPValidationExceptionLogs(logging.Filter):
    """Drop fastmcp's logger.exception() for Pydantic tool-arg validation (very noisy in e2e)."""

    def filter(self, record: logging.LogRecord) -> bool:
        return not (record.exc_info and record.getMessage().startswith("Error validating tool "))


def pytest_configure(config: pytest.Config) -> None:  # noqa: ARG001
    for name in ("httpx", "httpcore"):
        logging.getLogger(name).setLevel(logging.WARNING)
    logging.getLogger("fastmcp.server.server").addFilter(_SuppressFastMCPValidationExceptionLogs())


def _e2e_delete_spaces_after_test() -> bool:
    return os.getenv("ONEDATA_E2E_DELETE_SPACE", "").strip().lower() in {"1", "true", "yes"}


def pytest_sessionfinish(session, exitstatus):  # noqa: ARG001
    flush_forge_trace_summary_csvs()
    if _e2e_delete_spaces_after_test():
        import asyncio

        from e2e_isolated_space import delete_user_space, session_created_space_ids

        async def _cleanup() -> None:
            for space_id in session_created_space_ids():
                await delete_user_space(space_id)

        asyncio.run(_cleanup())


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


@pytest.fixture
def onedata_admin_token() -> str:
    """Admin Oneprovider token (not the confined MCP token applied by ``isolated_e2e_space``)."""
    from e2e_isolated_space import e2e_admin_oneprovider_token

    if not onedata_credentials_available():
        pytest.skip("Full Onedata credentials required for isolated E2E spaces")
    try:
        return e2e_admin_oneprovider_token()
    except ValueError:
        pytest.skip(
            "ONEDATA_E2E_ADMIN_TOKEN or ONEDATA_ONEPROVIDER_TOKEN required for isolated E2E"
        )


@pytest_asyncio.fixture
async def isolated_e2e_space(request: pytest.FixtureRequest, onedata_admin_token: str):
    """Per-test space (or shared group) with tree reset and confined Oneprovider token."""
    from e2e_isolated_space import (
        IsolatedE2ESpace,
        delete_user_space,
        ensure_isolated_space_harvester,
        isolated_scope_needs_harvester,
        provision_isolated_space,
        reset_space_contents,
    )

    if not onedata_credentials_available():
        pytest.skip("Full Onedata credentials required for isolated E2E spaces")

    group_marker = request.node.get_closest_marker("e2e_isolated_space_group")
    scope = str(group_marker.args[0]) if group_marker and group_marker.args else "function"
    confined_write = request.node.get_closest_marker("e2e_isolated_confined_write") is not None
    space = await provision_isolated_space(scope=scope, confined_write=confined_write)

    assert isinstance(space, IsolatedE2ESpace)
    if isolated_scope_needs_harvester(scope):
        await ensure_isolated_space_harvester(space)
    await reset_space_contents(space, admin_token=onedata_admin_token)

    previous_provider = os.environ.get("ONEDATA_ONEPROVIDER_TOKEN")
    os.environ["ONEDATA_ONEPROVIDER_TOKEN"] = space.confined_token_for_mcp(write=confined_write)

    yield space

    await reset_space_contents(space, admin_token=onedata_admin_token)
    if _e2e_delete_spaces_after_test() and not space.reused:
        await delete_user_space(space.space_id)

    if previous_provider is None:
        os.environ.pop("ONEDATA_ONEPROVIDER_TOKEN", None)
    else:
        os.environ["ONEDATA_ONEPROVIDER_TOKEN"] = previous_provider


@pytest_asyncio.fixture
async def mcp_application_isolated(isolated_e2e_space, mcp_application: Any) -> Any:
    """MCP app while ONEDATA_ONEPROVIDER_TOKEN is the confined token (read-only by default)."""
    _ = isolated_e2e_space
    return mcp_application

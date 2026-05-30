"""Forge LLM runs on isolated spaces: setup, trace checks, and state verification."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from assertions_lib import (
    assert_isolated_forge_trace,
    assert_tool_arguments_stay_in_isolated_space,
)
from e2e_isolated_space import IsolatedE2ESpace, use_admin_oneprovider_token
from e2e_types import E2EScenario, ForgeRunResult
from fastmcp import FastMCP
from forge_harness import run_forge_scenario

SetupHook = Callable[[IsolatedE2ESpace, str], Awaitable[None]]
VerifyStateHook = Callable[[IsolatedE2ESpace, FastMCP], Awaitable[None]]


async def run_isolated_forge_scenario(
    *,
    scenario: E2EScenario,
    space: IsolatedE2ESpace,
    mcp_app: FastMCP,
    forge_api_key: str,
    forge_base_url: str,
    model: str,
    pytest_request: Any,
    admin_token: str | None = None,
    setup: SetupHook | None = None,
    verify_state: VerifyStateHook | None = None,
    assert_trace: bool = True,
) -> ForgeRunResult:
    """Run an LLM + MCP scenario on ``mcp_application_isolated``.

    - ``setup``: optional seed (admin token); runs before the Forge loop.
    - ``verify_state``: post-run Onedata probes (confined token via ``mcp_app``).
    - ``assert_trace``: required/forbidden tools, successful dispatch, isolated paths.
    """

    if setup is not None:
        if not admin_token:
            msg = "admin_token is required when setup is provided"
            raise ValueError(msg)
        async with use_admin_oneprovider_token(admin_token):
            await setup(space, admin_token)

    run = await run_forge_scenario(
        scenario=scenario,
        mcp_app=mcp_app,
        forge_api_key=forge_api_key,
        forge_base_url=forge_base_url,
        model=model,
        pytest_request=pytest_request,
        isolated_space_id=space.space_id,
        isolated_space_name=space.space_name,
    )

    if assert_trace:
        assert_isolated_forge_trace(run)
        assert_tool_arguments_stay_in_isolated_space(run, space)

    if verify_state is not None:
        await verify_state(space, mcp_app)

    return run

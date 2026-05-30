"""Forge harness helpers for shared-tenant (legacy) E2E — read-only by policy."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from assertions_lib import assert_forbidden_tools
from e2e_types import E2EScenario, ForgeRunResult
from fastmcp import FastMCP
from forge_harness import run_forge_scenario
from shared_tenant import shared_readonly_scenario

VerifyStateHook = Callable[[FastMCP], Awaitable[None]]


async def run_legacy_forge_scenario(
    *,
    scenario: E2EScenario,
    mcp_app: FastMCP,
    forge_api_key: str,
    forge_base_url: str,
    model: str,
    pytest_request: Any = None,
) -> ForgeRunResult:
    """Run Forge on a shared tenant; enforce no mutating MCP tools were called."""

    readonly = shared_readonly_scenario(
        name=scenario.name,
        user_prompt=scenario.user_prompt,
        required_tools=scenario.required_tools,
        model=scenario.model,
        system_prompt=scenario.system_prompt,
        temperature=scenario.temperature,
        max_tokens=scenario.max_tokens,
        max_tool_rounds=scenario.max_tool_rounds,
        require_no_extra_tool_calls=scenario.require_no_extra_tool_calls,
        forbidden_tools=scenario.forbidden_tools,
        allowed_write_tools=scenario.allowed_write_tools,
    )
    run = await run_forge_scenario(
        scenario=readonly,
        mcp_app=mcp_app,
        forge_api_key=forge_api_key,
        forge_base_url=forge_base_url,
        model=model,
        pytest_request=pytest_request,
    )
    assert_forbidden_tools(run)
    return run


async def run_shared_forge_scenario(
    *,
    scenario: E2EScenario,
    mcp_app: FastMCP,
    forge_api_key: str,
    forge_base_url: str,
    model: str,
    pytest_request: Any = None,
    verify_state: VerifyStateHook | None = None,
    require_all_tool_calls_ok: bool = False,
) -> ForgeRunResult:
    """Forge on shared tenant, then optional MCP state probes (no hardcoded oracles in prompts).

    By default, failed exploratory tool calls (e.g. wrong ES ``path``) do not fail the run.
    Pass/fail is determined by the test's post-run checks (``verify_state``, required-tool
    policy, optional answer fragments) — not ``metrics.all_tool_calls_ok``.
    """

    run = await run_legacy_forge_scenario(
        scenario=scenario,
        mcp_app=mcp_app,
        forge_api_key=forge_api_key,
        forge_base_url=forge_base_url,
        model=model,
        pytest_request=pytest_request,
    )
    if require_all_tool_calls_ok:
        assert run.metrics.all_tool_calls_ok, (
            f"MCP tool errors: "
            f"{[(c.tool_name, c.error) for c in run.metrics.tool_calls if not c.ok]}"
        )
    if verify_state is not None:
        await verify_state(mcp_app)
    return run

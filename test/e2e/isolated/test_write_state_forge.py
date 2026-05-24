"""Isolated Forge E2E: write-state scenarios (read-write confined MCP token)."""

from __future__ import annotations

from typing import Any

import pytest
from e2e_isolated_space import IsolatedE2ESpace
from e2e_types import E2EScenario
from env_checks import forge_credentials_available, onedata_credentials_available
from forge_isolated_harness import run_isolated_forge_scenario
from isolated_helpers import child_names, seed_file
from plgrid_ground_truth import ground_truth_file_size_bytes, mcp_tool_json_result

from onedata_mcp.api.files import get_file_metadata, set_file_metadata, set_file_xattrs

WRITE_STATE_SPACE_GROUP = "write-state"

_ISOLATED_SYSTEM = (
    "You are a careful assistant with Onedata MCP tools. Use tools for factual answers "
    "and mutations on the connected Oneprovider. Do not invent space names, paths, or file ids. "
    "Only use paths under the isolated space you are connected to."
)

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.e2e,
    pytest.mark.e2e_isolated,
    pytest.mark.e2e_isolated_confined_write,
    pytest.mark.onedata_integration,
    pytest.mark.e2e_isolated_space_group(WRITE_STATE_SPACE_GROUP),
    pytest.mark.skipif(
        not onedata_credentials_available(),
        reason=(
            "ONEDATA_ONEZONE_* and ONEDATA_ONEPROVIDER_* required (see docs/e2e-isolated-spaces.md)"
        ),
    ),
    pytest.mark.skipif(
        not forge_credentials_available(),
        reason="PLGRID_FORGE_API_KEY and PLGRID_FORGE_MODEL required",
    ),
]


@pytest.mark.e2e_scenario("create-xattr-delete")
async def test_forge_create_xattr_delete(
    request: Any,
    mcp_application_isolated: Any,
    isolated_e2e_space: IsolatedE2ESpace,
    onedata_admin_token: str,
    forge_api_key: str,
    forge_model: str,
    forge_base_url: str,
) -> None:
    path = f"{isolated_e2e_space.root_path}/e2e-write/run-file.txt"
    parent = path.rsplit("/", 1)[0]
    basename = "run-file.txt"
    run_id = "e2e-run-001"
    write_tools = frozenset(
        {
            "create_file",
            "list_files",
            "set_file_xattrs",
            "get_file_metadata",
            "delete_file",
        }
    )

    async def verify(space: IsolatedE2ESpace, app: Any) -> None:
        _ = space
        listing = await mcp_tool_json_result(
            app,
            "list_files",
            {"parent_id_or_path": parent, "limit": 50},
        )
        assert basename not in child_names(listing)

    scenario = E2EScenario(
        name="isolated-forge-create-xattr-delete",
        system_prompt=_ISOLATED_SYSTEM,
        user_prompt=(
            f"On this Oneprovider: create file {path!r} with content 'lifecycle\\n' "
            f"(create_parents=true), list children of {parent!r} to confirm {basename!r} "
            f"exists, set xattr testRunId={run_id!r} on that file, verify with "
            "get_file_metadata (xattrs only), then delete the file and list the parent again."
        ),
        required_tools=write_tools,
        allowed_tools_for_minimal_context=write_tools,
        require_no_extra_tool_calls=False,
    )

    await run_isolated_forge_scenario(
        scenario=scenario,
        space=isolated_e2e_space,
        mcp_app=mcp_application_isolated,
        tool_context_mode="full",
        forge_api_key=forge_api_key,
        forge_base_url=forge_base_url,
        model=forge_model,
        pytest_request=request,
        admin_token=onedata_admin_token,
        verify_state=verify,
    )


@pytest.mark.e2e_scenario("create-nested")
async def test_forge_create_nested(
    request: Any,
    mcp_application_isolated: Any,
    isolated_e2e_space: IsolatedE2ESpace,
    onedata_admin_token: str,
    forge_api_key: str,
    forge_model: str,
    forge_base_url: str,
) -> None:
    nested_path = f"{isolated_e2e_space.root_path}/deep/new-dir/leaf.txt"
    expected_content = "forge-nested-leaf\n"
    write_tools = frozenset({"create_file", "download_file", "get_file_id"})

    async def verify(space: IsolatedE2ESpace, app: Any) -> None:
        _ = space
        file_id = await mcp_tool_json_result(app, "get_file_id", {"path": nested_path})
        assert isinstance(file_id, str) and file_id

        size = await ground_truth_file_size_bytes(app, nested_path)
        assert size == len(expected_content.encode())

        grep_out = await mcp_tool_json_result(
            app,
            "grep_file_content",
            {"file_id_or_path": nested_path, "pattern": "forge-nested-leaf"},
        )
        assert isinstance(grep_out, str)
        assert "forge-nested-leaf" in grep_out

    scenario = E2EScenario(
        name="isolated-forge-create-nested",
        system_prompt=_ISOLATED_SYSTEM,
        user_prompt=(
            f"Create file {nested_path!r} with exact content {expected_content!r}. "
            "The parent directories do not exist yet — use create_parents=true. "
            "Then download the file and confirm the bytes match what you wrote."
        ),
        required_tools=write_tools,
        allowed_tools_for_minimal_context=write_tools,
        require_no_extra_tool_calls=False,
    )

    await run_isolated_forge_scenario(
        scenario=scenario,
        space=isolated_e2e_space,
        mcp_app=mcp_application_isolated,
        tool_context_mode="full",
        forge_api_key=forge_api_key,
        forge_base_url=forge_base_url,
        model=forge_model,
        pytest_request=request,
        admin_token=onedata_admin_token,
        verify_state=verify,
    )


@pytest.mark.e2e_scenario("xattrs-only")
async def test_forge_xattrs_only(
    request: Any,
    mcp_application_isolated: Any,
    isolated_e2e_space: IsolatedE2ESpace,
    onedata_admin_token: str,
    forge_api_key: str,
    forge_model: str,
    forge_base_url: str,
) -> None:
    path = f"{isolated_e2e_space.root_path}/e2e-meta/xattrs-only.txt"
    meta_tools = frozenset({"set_file_xattrs", "get_file_metadata"})
    oracle: dict[str, Any] = {}

    async def setup(space: IsolatedE2ESpace, admin: str) -> None:
        _ = space
        await seed_file(path, "meta\n", admin_token=admin)
        await set_file_metadata(path, "json", {"seed": "baseline"})
        before = await get_file_metadata(path, ["json"])
        oracle["json_before"] = before.get("json") if isinstance(before, dict) else None

    async def verify(space: IsolatedE2ESpace, app: Any) -> None:
        _ = space
        after = await mcp_tool_json_result(
            app,
            "get_file_metadata",
            {"file_id_or_path": path, "metadata_types": ["json", "xattrs"]},
        )
        assert isinstance(after, dict)
        assert after.get("json") == oracle["json_before"]
        xattrs = after.get("xattrs")
        assert isinstance(xattrs, dict)
        assert xattrs.get("license") == "CC-0"
        assert xattrs.get("provenance") == "e2e"

    scenario = E2EScenario(
        name="isolated-forge-xattrs-only",
        system_prompt=_ISOLATED_SYSTEM,
        user_prompt=(
            f"On file {path!r}: set extended attributes license=CC-0 and provenance=e2e. "
            "Do not change JSON or RDF metadata. Confirm with get_file_metadata."
        ),
        required_tools=meta_tools,
        allowed_tools_for_minimal_context=meta_tools,
        require_no_extra_tool_calls=False,
        forbidden_tools=frozenset({"set_file_metadata", "delete_file", "create_file"}),
    )

    await run_isolated_forge_scenario(
        scenario=scenario,
        space=isolated_e2e_space,
        mcp_app=mcp_application_isolated,
        tool_context_mode="full",
        forge_api_key=forge_api_key,
        forge_base_url=forge_base_url,
        model=forge_model,
        pytest_request=request,
        admin_token=onedata_admin_token,
        setup=setup,
        verify_state=verify,
    )


@pytest.mark.e2e_scenario("json-metadata")
async def test_forge_json_metadata(
    request: Any,
    mcp_application_isolated: Any,
    isolated_e2e_space: IsolatedE2ESpace,
    onedata_admin_token: str,
    forge_api_key: str,
    forge_model: str,
    forge_base_url: str,
) -> None:
    path = f"{isolated_e2e_space.root_path}/e2e-meta/json-expand.txt"
    baseline_json = {
        "dataset": "e2e-baseline",
        "version": 1,
        "tags": ["alpha", "beta"],
    }
    expected_json = {
        **baseline_json,
        "version": 2,
        "title": "E2E Forge",
        "status": "published",
    }
    meta_tools = frozenset({"set_file_metadata", "get_file_metadata"})

    async def setup(space: IsolatedE2ESpace, admin: str) -> None:
        _ = space
        await seed_file(path, "json-expand\n", admin_token=admin)
        await set_file_metadata(path, "json", baseline_json)
        await set_file_xattrs(path, {"keep": "yes"})

    async def verify(space: IsolatedE2ESpace, app: Any) -> None:
        _ = space
        after = await mcp_tool_json_result(
            app,
            "get_file_metadata",
            {"file_id_or_path": path, "metadata_types": ["json", "xattrs"]},
        )
        assert isinstance(after, dict)
        assert after.get("json") == expected_json
        xattrs = after.get("xattrs")
        assert isinstance(xattrs, dict)
        assert xattrs.get("keep") == "yes"

    scenario = E2EScenario(
        name="isolated-forge-json-metadata",
        system_prompt=_ISOLATED_SYSTEM,
        user_prompt=(
            f"On file {path!r}: read the current JSON metadata with get_file_metadata, "
            "then update it so title is 'E2E Forge', version is 2, and status is 'published', "
            "while keeping dataset and tags exactly as they are. "
            "Call set_file_metadata with metadata_type json and the full merged JSON object "
            "(set_file_metadata replaces the whole JSON document). "
            "Do not change extended attributes. Confirm the result with get_file_metadata."
        ),
        required_tools=meta_tools,
        allowed_tools_for_minimal_context=meta_tools,
        require_no_extra_tool_calls=False,
        forbidden_tools=frozenset({"set_file_xattrs", "create_file", "delete_file"}),
    )

    await run_isolated_forge_scenario(
        scenario=scenario,
        space=isolated_e2e_space,
        mcp_app=mcp_application_isolated,
        tool_context_mode="full",
        forge_api_key=forge_api_key,
        forge_base_url=forge_base_url,
        model=forge_model,
        pytest_request=request,
        admin_token=onedata_admin_token,
        setup=setup,
        verify_state=verify,
    )

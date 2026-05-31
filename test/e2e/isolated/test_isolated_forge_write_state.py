"""Isolated Forge E2E: write-state scenarios (read-write confined MCP token)."""

from __future__ import annotations

import json
from typing import Any

import pytest
from assertions_lib import assert_forge_scenario_outcome
from e2e_isolated_space import IsolatedE2ESpace
from e2e_types import E2EScenario, ForgeRunResult, ToolCallMetric
from env_checks import forge_credentials_available, onedata_credentials_available
from forge_isolated_harness import run_isolated_forge_scenario
from isolated_helpers import child_names, recursive_paths, seed_file
from plgrid_ground_truth import ground_truth_file_size_bytes, mcp_tool_json_result

from onedata_mcp.api.files import set_file_metadata, set_file_xattrs

WRITE_STATE_SPACE_GROUP = "write-state"

_ISOLATED_SYSTEM = (
    "You are a careful assistant with Onedata MCP tools. Use tools for factual answers "
    "and mutations on the connected Oneprovider. Do not invent space names, paths, or file ids. "
    "Only use paths under the isolated space you are connected to."
)


def _targets_path(call: ToolCallMetric, logical_path: str) -> bool:
    return str(call.arguments.get("file_id_or_path", "")) == logical_path


def _metadata_types_include_json(arguments: dict[str, Any]) -> bool:
    types = arguments.get("metadata_types")
    if types is None:
        return True
    if isinstance(types, list):
        return "json" in types
    return False


def _parse_json_metadata_arg(raw: object) -> dict[str, Any] | None:
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            return None
        return parsed if isinstance(parsed, dict) else None
    return None


def _assert_json_metadata_read_merge_verify(
    run: ForgeRunResult,
    logical_path: str,
    *,
    expected_written_json: dict[str, Any],
) -> None:
    """Trace must read JSON, write merged JSON, then read again to verify."""

    calls = run.metrics.tool_calls
    read_indexes = [
        index
        for index, call in enumerate(calls)
        if call.tool_name == "get_file_metadata"
        and call.ok
        and _targets_path(call, logical_path)
        and _metadata_types_include_json(call.arguments)
    ]
    write_indexes = [
        index
        for index, call in enumerate(calls)
        if call.tool_name == "set_file_metadata"
        and call.ok
        and _targets_path(call, logical_path)
        and call.arguments.get("metadata_type") == "json"
    ]
    assert read_indexes, (
        "Expected successful get_file_metadata including json; "
        f"tool_calls={[(c.tool_name, c.ok, c.arguments) for c in calls]}"
    )
    assert write_indexes, (
        "Expected successful set_file_metadata for json; "
        f"tool_calls={[(c.tool_name, c.ok, c.arguments) for c in calls]}"
    )
    first_read, first_write = read_indexes[0], write_indexes[0]
    assert first_read < first_write, "get_file_metadata (json) must run before set_file_metadata"
    assert any(index > first_write for index in read_indexes), (
        "Expected get_file_metadata after set_file_metadata to verify the update"
    )
    written = _parse_json_metadata_arg(calls[first_write].arguments.get("metadata"))
    assert written == expected_written_json, (
        "set_file_metadata must send the full merged JSON (baseline fields preserved); "
        f"got {written!r}"
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


@pytest.mark.e2e_scenario("create-file-with-xattr")
async def test_forge_create_file_with_xattr(
    request: Any,
    mcp_application_isolated: Any,
    isolated_e2e_space: IsolatedE2ESpace,
    onedata_admin_token: str,
    forge_api_key: str,
    forge_model: str,
    forge_base_url: str,
) -> None:
    path = f"{isolated_e2e_space.root_path}/e2e-write/run-file.txt"
    basename = "run-file.txt"
    parent = path.rsplit("/", 1)[0]
    run_id = "e2e-run-001"
    write_tools = frozenset({"create_file", "set_file_xattrs"})

    async def verify(space: IsolatedE2ESpace, app: Any) -> None:
        _ = space
        listing = await mcp_tool_json_result(
            app,
            "list_files",
            {"parent_id_or_path": parent, "limit": 50},
        )
        assert child_names(listing) == {basename}
        recursive_listing = await mcp_tool_json_result(
            app,
            "list_files_recursive",
            {"parent_id_or_path": parent, "limit": 50},
        )
        paths = recursive_paths(recursive_listing)
        assert len(paths) == 1
        assert paths[0].split("/")[-1] == basename
        meta = await mcp_tool_json_result(
            app,
            "get_file_metadata",
            {"file_id_or_path": path, "metadata_types": ["xattrs"]},
        )
        assert isinstance(meta, dict)
        xattrs = meta.get("xattrs")
        assert isinstance(xattrs, dict)
        assert xattrs.get("testRunId") == run_id

    scenario = E2EScenario(
        name="isolated-forge-create-file-with-xattr",
        system_prompt=_ISOLATED_SYSTEM,
        user_prompt=(
            f"Create file {path!r} with content 'first line\\nsecond line',"
            f" then set extended attribute testRunId={run_id!r} on that file."
        ),
        required_tools=write_tools,
        require_no_extra_tool_calls=True,
    )

    await run_isolated_forge_scenario(
        scenario=scenario,
        space=isolated_e2e_space,
        mcp_app=mcp_application_isolated,
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
    expected_content = "forge-nested-leaf"
    write_tools = frozenset({"create_file", "download_file"})

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
            "Then download the file and verify the file content."
        ),
        required_tools=write_tools,
        require_no_extra_tool_calls=False,
    )

    await run_isolated_forge_scenario(
        scenario=scenario,
        space=isolated_e2e_space,
        mcp_app=mcp_application_isolated,
        forge_api_key=forge_api_key,
        forge_base_url=forge_base_url,
        model=forge_model,
        pytest_request=request,
        admin_token=onedata_admin_token,
        verify_state=verify,
    )


@pytest.mark.e2e_scenario("modify-file-xattrs")
async def test_forge_modify_file_xattrs(
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

    async def setup(space: IsolatedE2ESpace, admin: str) -> None:
        _ = space
        await seed_file(path, "meta\n", admin_token=admin)

    async def verify(space: IsolatedE2ESpace, app: Any) -> None:
        _ = space
        after = await mcp_tool_json_result(
            app,
            "get_file_metadata",
            {"file_id_or_path": path, "metadata_types": ["xattrs"]},
        )
        assert isinstance(after, dict)
        xattrs = after.get("xattrs")
        assert isinstance(xattrs, dict)
        assert xattrs.get("license") == "CC-0"
        assert xattrs.get("provenance") == "e2e"

    scenario = E2EScenario(
        name="isolated-forge-modify-file-xattrs",
        system_prompt=_ISOLATED_SYSTEM,
        user_prompt=(
            f"On file {path!r}: set extended attributes license=CC-0 and provenance=e2e. "
            "Afterwards verify if the xattrs were updated successfully. "
            "Use get_file_metadata for verification."
        ),
        required_tools=meta_tools,
        require_no_extra_tool_calls=True,
        forbidden_tools=frozenset({"set_file_metadata", "delete_file", "create_file"}),
    )

    run = await run_isolated_forge_scenario(
        scenario=scenario,
        space=isolated_e2e_space,
        mcp_app=mcp_application_isolated,
        forge_api_key=forge_api_key,
        forge_base_url=forge_base_url,
        model=forge_model,
        pytest_request=request,
        admin_token=onedata_admin_token,
        setup=setup,
        verify_state=verify,
    )
    assert_forge_scenario_outcome(
        run,
        answer_fragments=("CC-0", "e2e"),
        answer_hint="Final reply should report both xattr values after verification.",
    )


@pytest.mark.e2e_scenario("delete-marked-files")
async def test_forge_delete_marked_files(
    request: Any,
    mcp_application_isolated: Any,
    isolated_e2e_space: IsolatedE2ESpace,
    onedata_admin_token: str,
    forge_api_key: str,
    forge_model: str,
    forge_base_url: str,
) -> None:
    batch_dir = f"{isolated_e2e_space.root_path}/e2e-delete-batch"
    all_basenames = {f"file-{index:02d}.txt" for index in range(1, 11)}
    marked_basenames = frozenset({"file-02.txt", "file-05.txt", "file-07.txt", "file-09.txt"})
    kept_basenames = all_basenames - marked_basenames
    delete_tools = frozenset({"delete_file"})
    read_xattr_tools = frozenset({"get_file_metadata", "get_file_attributes"})

    async def setup(space: IsolatedE2ESpace, admin: str) -> None:
        _ = space
        for index in range(1, 11):
            basename = f"file-{index:02d}.txt"
            path = f"{batch_dir}/{basename}"
            await seed_file(path, f"batch-{index}\n", admin_token=admin)
            if basename in marked_basenames:
                await set_file_xattrs(path, {"toDelete": "true"})

    async def verify(space: IsolatedE2ESpace, app: Any) -> None:
        _ = space
        recursive_listing = await mcp_tool_json_result(
            app,
            "list_files_recursive",
            {"parent_id_or_path": batch_dir, "limit": 50},
        )
        remaining = {path.split("/")[-1] for path in recursive_paths(recursive_listing)}
        assert remaining == kept_basenames
        for basename in kept_basenames:
            meta = await mcp_tool_json_result(
                app,
                "get_file_metadata",
                {
                    "file_id_or_path": f"{batch_dir}/{basename}",
                    "metadata_types": ["xattrs"],
                },
            )
            assert isinstance(meta, dict)
            xattrs = meta.get("xattrs")
            if isinstance(xattrs, dict):
                assert xattrs.get("toDelete") != "true"

    scenario = E2EScenario(
        name="isolated-forge-delete-marked-files",
        system_prompt=_ISOLATED_SYSTEM,
        user_prompt=(
            f"In folder {batch_dir!r} there are ten text files. "
            "Delete every file whose extended attribute toDelete is true. "
            "Report how many files you deleted."
        ),
        required_tools=delete_tools,
        require_no_extra_tool_calls=False,
        forbidden_tools=frozenset({"create_file", "set_file_xattrs", "set_file_metadata"}),
    )

    run = await run_isolated_forge_scenario(
        scenario=scenario,
        space=isolated_e2e_space,
        mcp_app=mcp_application_isolated,
        forge_api_key=forge_api_key,
        forge_base_url=forge_base_url,
        model=forge_model,
        pytest_request=request,
        admin_token=onedata_admin_token,
        setup=setup,
        verify_state=verify,
    )
    assert_forge_scenario_outcome(
        run,
        answer_fragments=("4",),
        answer_hint="Final reply should state that four files were deleted.",
        any_of=(
            read_xattr_tools,
            frozenset({"list_files", "list_files_recursive"}),
        ),
    )


@pytest.mark.e2e_scenario("update-json-metadata")
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
        name="isolated-forge-update-json-metadata",
        system_prompt=_ISOLATED_SYSTEM,
        user_prompt=(
            f"On file {path!r}: read the current JSON metadata, "
            "then update it so title is 'E2E Forge', version is 2, and status is 'published', "
            "then verify if the JSON metadata was updated successfully."
        ),
        required_tools=meta_tools,
        require_no_extra_tool_calls=False,
        forbidden_tools=frozenset({"set_file_xattrs", "create_file", "delete_file"}),
    )

    run = await run_isolated_forge_scenario(
        scenario=scenario,
        space=isolated_e2e_space,
        mcp_app=mcp_application_isolated,
        forge_api_key=forge_api_key,
        forge_base_url=forge_base_url,
        model=forge_model,
        pytest_request=request,
        admin_token=onedata_admin_token,
        setup=setup,
        verify_state=verify,
    )
    _assert_json_metadata_read_merge_verify(run, path, expected_written_json=expected_json)
    assert_forge_scenario_outcome(
        run,
        answer_fragments=("E2E Forge", "published", "e2e-baseline"),
        answer_hint=(
            "Final reply should mention the new title, version, and status, and preserved dataset and tags."
        ),
    )

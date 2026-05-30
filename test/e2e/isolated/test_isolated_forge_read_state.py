"""Isolated Forge E2E: read-state scenarios (LLM + MCP trace + Onedata state probes)."""

from __future__ import annotations

from typing import Any

import pytest
from assertions_lib import assert_forge_scenario_outcome
from e2e_isolated_space import IsolatedE2ESpace, use_admin_oneprovider_token
from e2e_oracles import assert_list_spaces_oracle
from e2e_types import E2EScenario, ForgeRunResult
from env_checks import forge_credentials_available, onedata_credentials_available
from forge_isolated_harness import run_isolated_forge_scenario
from isolated_grep_documents import (
    DOCUMENTS_DIR_NAME,
    GREP_DECOY_BASENAME,
    GREP_MULTI_FILE_NEEDLE,
    GREP_TARGET_BASENAME,
    grep_multi_file_documents,
)
from isolated_helpers import (
    basenames_with_posix_777,
    require_harvester_index,
    seed_file,
    set_file_posix_permissions,
)
from plgrid_ground_truth import ground_truth_file_size_bytes, mcp_tool_json_result

from onedata_mcp.api.files import get_file_attributes, get_file_id

READ_STATE_SPACE_GROUP = "read-state"


def _assert_get_file_id_used_path(run: ForgeRunResult, logical_path: str) -> None:
    matched = [
        call
        for call in run.metrics.tool_calls
        if call.tool_name == "get_file_id"
        and call.ok
        and str(call.arguments.get("path", "")) == logical_path
    ]
    assert matched, (
        f"Expected successful get_file_id with path {logical_path!r}; "
        f"tool_calls={[(c.tool_name, c.ok, c.arguments) for c in run.metrics.tool_calls]}"
    )


_ISOLATED_SYSTEM_PROMPT = (
    "You are a careful assistant with Onedata MCP tools. Use tools for factual answers "
    "about the connected Oneprovider. Do not invent space names, paths, or file ids."
    "Do not format dates or numbers in the answers unless specifically asked."
)

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.e2e,
    pytest.mark.e2e_isolated,
    pytest.mark.onedata_integration,
    pytest.mark.e2e_isolated_space_group(READ_STATE_SPACE_GROUP),
    pytest.mark.skipif(
        not onedata_credentials_available(),
        reason="ONEDATA_ONEZONE_* and ONEDATA_ONEPROVIDER_* required (see docs/e2e-isolated-spaces.md)",
    ),
    pytest.mark.skipif(
        not forge_credentials_available(),
        reason="PLGRID_FORGE_API_KEY and PLGRID_FORGE_MODEL required",
    ),
]


async def _verify_list_spaces(space: IsolatedE2ESpace, app: Any) -> None:
    data = await mcp_tool_json_result(app, "list_available_spaces", {})
    assert_list_spaces_oracle(
        data,
        expected_name=space.space_name,
        expected_id=space.space_id,
    )


@pytest.mark.e2e_scenario("list-spaces")
async def test_forge_list_spaces(
    request: Any,
    mcp_application_isolated: Any,
    isolated_e2e_space: IsolatedE2ESpace,
    onedata_admin_token: str,
    forge_api_key: str,
    forge_model: str,
    forge_base_url: str,
) -> None:
    scenario = E2EScenario(
        name="isolated-forge-list-spaces",
        system_prompt=_ISOLATED_SYSTEM_PROMPT,
        user_prompt="List every available Onedata space name.",
        required_tools=frozenset({"list_available_spaces"}),
        require_no_extra_tool_calls=True,
        forbidden_tools=frozenset({"list_files", "get_file_id", "create_file"}),
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
        verify_state=_verify_list_spaces,
    )


@pytest.mark.e2e_scenario("find-file-creation-time")
async def test_forge_file_creation_time(
    request: Any,
    mcp_application_isolated: Any,
    isolated_e2e_space: IsolatedE2ESpace,
    onedata_admin_token: str,
    forge_api_key: str,
    forge_model: str,
    forge_base_url: str,
) -> None:
    logical_path = f"{isolated_e2e_space.root_path}/e2e-creation-time/hello.txt"
    oracle: dict[str, int] = {}

    async def setup(space: IsolatedE2ESpace, admin: str) -> None:
        await seed_file(logical_path, "creation-time-body\n", admin_token=admin)
        async with use_admin_oneprovider_token(admin):
            attrs = await get_file_attributes(logical_path, attributes=["creationTime"])
        creation_time = attrs.get("creationTime")
        assert isinstance(creation_time, int)
        oracle["creation_time"] = creation_time

    async def verify(space: IsolatedE2ESpace, app: Any) -> None:
        attrs = await mcp_tool_json_result(
            app,
            "get_file_attributes",
            {
                "file_id_or_path": logical_path,
                "attributes": ["creationTime"],
            },
        )
        assert isinstance(attrs, dict)
        assert attrs.get("creationTime") == oracle["creation_time"]

    scenario = E2EScenario(
        name="isolated-forge-file-creation-time",
        system_prompt=_ISOLATED_SYSTEM_PROMPT,
        user_prompt=(f"What is the Onedata file creation time for {logical_path!r}? "),
        required_tools=frozenset({"get_file_attributes"}),
        require_no_extra_tool_calls=True,
        forbidden_tools=frozenset({"download_file", "create_file"}),
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
        setup=setup,
        verify_state=verify,
    )


@pytest.mark.e2e_scenario("find-file-by-path")
async def test_forge_find_file_by_path(
    request: Any,
    mcp_application_isolated: Any,
    isolated_e2e_space: IsolatedE2ESpace,
    onedata_admin_token: str,
    forge_api_key: str,
    forge_model: str,
    forge_base_url: str,
) -> None:
    file_basename = "target.txt"
    dir_path = f"{isolated_e2e_space.root_path}/e2e-find-by-path/nested-directory"
    logical_path = f"{dir_path}/{file_basename}"
    oracle: dict[str, str] = {}

    async def setup(space: IsolatedE2ESpace, admin: str) -> None:
        await seed_file(logical_path, "find-by-path\n", admin_token=admin)
        async with use_admin_oneprovider_token(admin):
            oracle["file_id"] = await get_file_id(logical_path)

    async def verify(space: IsolatedE2ESpace, app: Any) -> None:
        resolved_id = await mcp_tool_json_result(
            app,
            "get_file_id",
            {"path": logical_path},
        )
        assert isinstance(resolved_id, str) and resolved_id
        assert resolved_id == oracle["file_id"]

        attrs = await mcp_tool_json_result(
            app,
            "get_file_attributes",
            {
                "file_id_or_path": resolved_id,
                "attributes": ["path", "fileId", "name"],
            },
        )
        assert isinstance(attrs, dict)
        assert attrs.get("fileId") == oracle["file_id"]
        assert attrs.get("name") == file_basename
        reported_path = attrs.get("path")
        assert isinstance(reported_path, str)
        assert reported_path == logical_path

    scenario = E2EScenario(
        name="isolated-forge-find-file-by-path",
        system_prompt=_ISOLATED_SYSTEM_PROMPT,
        user_prompt=(
            f"The file {file_basename!r} lives under {dir_path!r}. What is its Onedata file id?"
        ),
        required_tools=frozenset({"get_file_id"}),
        require_no_extra_tool_calls=True,
        forbidden_tools=frozenset({"list_files", "list_files_recursive", "create_file"}),
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
    _assert_get_file_id_used_path(run, logical_path)


@pytest.mark.e2e_scenario("list-children")
async def test_forge_list_children(
    request: Any,
    mcp_application_isolated: Any,
    isolated_e2e_space: IsolatedE2ESpace,
    onedata_admin_token: str,
    forge_api_key: str,
    forge_model: str,
    forge_base_url: str,
) -> None:
    parent_path = f"{isolated_e2e_space.root_path}/e2e-children"
    child_basenames = tuple(f"child-{label}.txt" for label in ("a", "b", "c", "d", "e"))
    probe_basename = child_basenames[0]

    async def setup(space: IsolatedE2ESpace, admin: str) -> None:
        for basename in child_basenames:
            await seed_file(
                f"{parent_path}/{basename}",
                f"{basename}\n",
                admin_token=admin,
            )

    async def verify(space: IsolatedE2ESpace, app: Any) -> None:
        listing = await mcp_tool_json_result(
            app,
            "list_files",
            {"parent_id_or_path": parent_path, "limit": 50},
        )
        assert isinstance(listing, dict)
        children = listing.get("children")
        assert isinstance(children, list)
        names = {
            entry.get("name")
            for entry in children
            if isinstance(entry, dict) and isinstance(entry.get("name"), str)
        }
        missing = set(child_basenames) - names
        assert not missing, f"list_files missing seeded children: {sorted(missing)}"
        assert probe_basename in names

    scenario = E2EScenario(
        name="isolated-forge-list-children",
        system_prompt=_ISOLATED_SYSTEM_PROMPT,
        user_prompt=(f"List all files names in directory {parent_path!r}."),
        required_tools=frozenset({"list_files"}),
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
        setup=setup,
        verify_state=verify,
    )


@pytest.mark.e2e_scenario("find-posix-777")
async def test_forge_find_posix_777(
    request: Any,
    mcp_application_isolated: Any,
    isolated_e2e_space: IsolatedE2ESpace,
    onedata_admin_token: str,
    forge_api_key: str,
    forge_model: str,
    forge_base_url: str,
) -> None:
    perm_dir = f"{isolated_e2e_space.root_path}/e2e-posix-777"
    file_basenames = (
        "audit.log",
        "budget.csv",
        "quota-note.txt",
        "readme.md",
        "summary.txt",
    )
    target_basename = "quota-note.txt"

    async def setup(space: IsolatedE2ESpace, admin: str) -> None:
        _ = space
        for basename in file_basenames:
            path = f"{perm_dir}/{basename}"
            await seed_file(path, f"{basename}\n", admin_token=admin)
            if basename == target_basename:
                await set_file_posix_permissions(path, "0777", admin_token=admin)

    async def verify(space: IsolatedE2ESpace, app: Any) -> None:
        _ = space
        listing = await mcp_tool_json_result(
            app,
            "list_files",
            {
                "parent_id_or_path": perm_dir,
                "limit": 50,
                "attributes": ["name", "posixPermissions"],
            },
        )
        marked = basenames_with_posix_777(listing)
        assert marked == {target_basename}

    scenario = E2EScenario(
        name="isolated-forge-find-posix-777",
        system_prompt=_ISOLATED_SYSTEM_PROMPT,
        user_prompt=(
            f"In directory {perm_dir!r} find the file with POSIX permissions 0777, return it's filename"
        ),
        required_tools=frozenset(),
        require_no_extra_tool_calls=False,
        forbidden_tools=frozenset(
            {"create_file", "delete_file", "set_file_xattrs", "set_file_metadata"}
        ),
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
        answer_fragments=(target_basename,),
        answer_hint="Final reply must name the sole file with mode 0777.",
        any_of=(frozenset({"get_file_attributes", "list_files"}),),
    )


@pytest.mark.e2e_scenario("grep-multi-file")
async def test_forge_grep_multi_file(
    request: Any,
    mcp_application_isolated: Any,
    isolated_e2e_space: IsolatedE2ESpace,
    onedata_admin_token: str,
    forge_api_key: str,
    forge_model: str,
    forge_base_url: str,
) -> None:
    documents_dir = f"{isolated_e2e_space.root_path}/{DOCUMENTS_DIR_NAME}"
    target_path = f"{documents_dir}/{GREP_TARGET_BASENAME}"

    async def setup(space: IsolatedE2ESpace, admin: str) -> None:
        _ = space
        for basename, body in grep_multi_file_documents():
            await seed_file(f"{documents_dir}/{basename}", body, admin_token=admin)

    async def verify(space: IsolatedE2ESpace, app: Any) -> None:
        _ = space
        target_grep = await mcp_tool_json_result(
            app,
            "grep_file_content",
            {"file_id_or_path": target_path, "pattern": GREP_MULTI_FILE_NEEDLE},
        )
        assert isinstance(target_grep, str)
        assert GREP_MULTI_FILE_NEEDLE in target_grep

        decoy_grep = await mcp_tool_json_result(
            app,
            "grep_file_content",
            {
                "file_id_or_path": f"{documents_dir}/{GREP_DECOY_BASENAME}",
                "pattern": GREP_MULTI_FILE_NEEDLE,
            },
        )
        assert isinstance(decoy_grep, str)
        assert GREP_MULTI_FILE_NEEDLE not in decoy_grep

    scenario = E2EScenario(
        name="isolated-forge-grep-multi-file",
        system_prompt=_ISOLATED_SYSTEM_PROMPT,
        user_prompt=(
            f"I keep working notes in the documents folder at {documents_dir!r}. "
            f"Find which file contains the text {GREP_MULTI_FILE_NEEDLE!r} and tell me its filename."
        ),
        required_tools=frozenset({"grep_file_content"}),
        require_no_extra_tool_calls=False,
        forbidden_tools=frozenset({"download_file", "create_file"}),
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
        setup=setup,
        verify_state=verify,
    )


@pytest.mark.e2e_scenario("find-file-size")
async def test_forge_file_size_bytes(
    request: Any,
    mcp_application_isolated: Any,
    isolated_e2e_space: IsolatedE2ESpace,
    onedata_admin_token: str,
    forge_api_key: str,
    forge_model: str,
    forge_base_url: str,
) -> None:
    size_dir = f"{isolated_e2e_space.root_path}/e2e-forge-size"
    logical_path = f"{size_dir}/payload.txt"
    content = "forge-size-probe"
    expected_bytes = len(content.encode())

    async def setup(space: IsolatedE2ESpace, admin: str) -> None:
        await seed_file(
            f"{size_dir}/readme.txt",
            "Unrelated readme — not the file you were asked about.\n" * 12,
            admin_token=admin,
        )
        await seed_file(
            f"{size_dir}/changelog.txt",
            "Distraction changelog with a different byte length entirely.\n" * 8,
            admin_token=admin,
        )
        await seed_file(logical_path, content, admin_token=admin)

    async def verify(space: IsolatedE2ESpace, app: Any) -> None:
        size = await ground_truth_file_size_bytes(app, logical_path)
        assert size == expected_bytes

    scenario = E2EScenario(
        name="isolated-forge-file-size-bytes",
        system_prompt=_ISOLATED_SYSTEM_PROMPT,
        user_prompt=(f"What is the size in bytes of {logical_path!r}?"),
        required_tools=frozenset({"get_file_attributes"}),
        require_no_extra_tool_calls=True,
        forbidden_tools=frozenset({"grep_file_content", "download_file"}),
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
        answer_fragments=(str(expected_bytes),),
        answer_hint=f"Final reply must include byte size {expected_bytes}.",
    )


@pytest.mark.e2e_scenario("list-harvester-indexes")
async def test_forge_list_harvester_indexes(
    request: Any,
    mcp_application_isolated: Any,
    isolated_e2e_space: IsolatedE2ESpace,
    onedata_admin_token: str,
    forge_api_key: str,
    forge_model: str,
    forge_base_url: str,
) -> None:
    harvester_id, index_id = await require_harvester_index(isolated_e2e_space)

    async def verify(space: IsolatedE2ESpace, app: Any) -> None:
        rows = await mcp_tool_json_result(
            app,
            "list_user_harvesters",
            {"space_name": space.space_name},
        )
        assert isinstance(rows, list)
        harvester_ids = {
            row.get("harvesterId")
            for row in rows
            if isinstance(row, dict) and isinstance(row.get("harvesterId"), str)
        }
        assert harvester_id in harvester_ids
        match = next(
            row for row in rows if isinstance(row, dict) and row.get("harvesterId") == harvester_id
        )
        indices = match.get("indices")
        assert isinstance(indices, list) and indices, "expected at least one index"
        index_ids = {
            idx.get("indexId")
            for idx in indices
            if isinstance(idx, dict) and isinstance(idx.get("indexId"), str)
        }
        assert index_id in index_ids

    scenario = E2EScenario(
        name="isolated-forge-list-harvester-indexes",
        system_prompt=_ISOLATED_SYSTEM_PROMPT,
        user_prompt=("List every search index exposed by user harvesters."),
        required_tools=frozenset({"list_user_harvesters"}),
        require_no_extra_tool_calls=True,
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
        verify_state=verify,
    )
    assert_forge_scenario_outcome(
        run,
        answer_fragments=(index_id,),
        answer_hint=f"Final reply must mention the harvester index id {index_id!r}.",
    )

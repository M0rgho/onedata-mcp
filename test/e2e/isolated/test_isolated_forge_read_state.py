"""Isolated Forge E2E: read-state scenarios (LLM + MCP trace + Onedata state probes)."""

from __future__ import annotations

from typing import Any

import pytest
from e2e_isolated_space import IsolatedE2ESpace
from e2e_oracles import assert_list_spaces_oracle
from e2e_types import E2EScenario
from env_checks import forge_credentials_available, onedata_credentials_available
from forge_isolated_harness import run_isolated_forge_scenario
from isolated_helpers import (
    es_hits_total,
    require_harvester_index,
    seed_file,
    wait_for_harvester_hits,
)
from plgrid_ground_truth import ground_truth_file_size_bytes, mcp_tool_json_result

from onedata_mcp.api.files import get_file_id
from onedata_mcp.api.harvesters import harvester_es_search_query, harvester_index_query

READ_STATE_SPACE_GROUP = "read-state"

_ISOLATED_SYSTEM_PROMPT = (
    "You are a careful assistant with Onedata MCP tools. Use tools for factual answers "
    "about the connected Oneprovider. Do not invent space names, paths, or file ids."
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
        user_prompt="List every Onedata space name available on this Oneprovider.",
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


@pytest.mark.e2e_scenario("file-id-roundtrip")
async def test_forge_file_id_roundtrip(
    request: Any,
    mcp_application_isolated: Any,
    isolated_e2e_space: IsolatedE2ESpace,
    onedata_admin_token: str,
    forge_api_key: str,
    forge_model: str,
    forge_base_url: str,
) -> None:
    logical_path = f"{isolated_e2e_space.root_path}/e2e-roundtrip/hello.txt"
    expected_name = "hello.txt"
    oracle: dict[str, str] = {}

    async def setup(space: IsolatedE2ESpace, admin: str) -> None:
        await seed_file(logical_path, "roundtrip-body\n", admin_token=admin)
        oracle["file_id"] = await get_file_id(logical_path)

    async def verify(space: IsolatedE2ESpace, app: Any) -> None:
        attrs = await mcp_tool_json_result(
            app,
            "get_file_attributes",
            {
                "file_id_or_path": oracle["file_id"],
                "attributes": ["fileId", "name", "path"],
            },
        )
        assert isinstance(attrs, dict)
        assert attrs.get("fileId") == oracle["file_id"]
        assert attrs.get("name") == expected_name
        assert attrs.get("path") in {
            logical_path.lstrip("/"),
            logical_path,
        }

    scenario = E2EScenario(
        name="isolated-forge-file-id-roundtrip",
        system_prompt=_ISOLATED_SYSTEM_PROMPT,
        user_prompt=(
            f"Find {logical_path!r} call get_file_id, then get_file_attributes "
            "using only the returned file id (include fileId, name, and path attributes)."
        ),
        required_tools=frozenset[str]({"get_file_id", "get_file_attributes"}),
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


@pytest.mark.e2e_scenario("path-by-file-id")
async def test_forge_path_by_file_id(
    request: Any,
    mcp_application_isolated: Any,
    isolated_e2e_space: IsolatedE2ESpace,
    onedata_admin_token: str,
    forge_api_key: str,
    forge_model: str,
    forge_base_url: str,
) -> None:
    logical_path = f"{isolated_e2e_space.root_path}/e2e-path-by-id/target.txt"
    expected_path = logical_path.lstrip("/")
    oracle: dict[str, str] = {}

    async def setup(space: IsolatedE2ESpace, admin: str) -> None:
        await seed_file(logical_path, "path-by-id\n", admin_token=admin)
        oracle["file_id"] = await get_file_id(logical_path)

    async def verify(space: IsolatedE2ESpace, app: Any) -> None:
        attrs = await mcp_tool_json_result(
            app,
            "get_file_attributes",
            {"file_id_or_path": oracle["file_id"], "attributes": ["path", "fileId"]},
        )
        assert isinstance(attrs, dict)
        reported = attrs.get("path")
        assert isinstance(reported, str)
        assert reported in {expected_path, logical_path}

    scenario = E2EScenario(
        name="isolated-forge-path-by-file-id",
        system_prompt=_ISOLATED_SYSTEM_PROMPT,
        user_prompt=(
            f"Resolve the file id for {logical_path!r}, then call get_file_attributes "
            "on that id only and report the path field."
        ),
        required_tools=frozenset({"get_file_id", "get_file_attributes"}),
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
    child_basename = "child-a.txt"

    async def setup(space: IsolatedE2ESpace, admin: str) -> None:
        await seed_file(f"{parent_path}/{child_basename}", "child-a\n", admin_token=admin)
        await seed_file(f"{parent_path}/child-b.txt", "child-b\n", admin_token=admin)

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
        assert child_basename in names

    scenario = E2EScenario(
        name="isolated-forge-list-children",
        system_prompt=_ISOLATED_SYSTEM_PROMPT,
        user_prompt=(
            f"Under parent path {parent_path!r}, list children (one level) and confirm "
            f"{child_basename!r} is present. Use list_files."
        ),
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
    parent = f"{isolated_e2e_space.root_path}/e2e-grep-multi"
    needle = "E2E_FORGE_GREP_MARKER"
    target_basename = "has-marker.txt"
    target_path = f"{parent}/{target_basename}"

    async def setup(space: IsolatedE2ESpace, admin: str) -> None:
        _ = space
        await seed_file(f"{parent}/plain-a.txt", "alpha only\n", admin_token=admin)
        await seed_file(target_path, f"before\n{needle}\nafter\n", admin_token=admin)
        await seed_file(f"{parent}/plain-b.txt", "beta only\n", admin_token=admin)

    async def verify(space: IsolatedE2ESpace, app: Any) -> None:
        _ = space
        grep_out = await mcp_tool_json_result(
            app,
            "grep_file_content",
            {"file_id_or_path": target_path, "pattern": needle},
        )
        assert isinstance(grep_out, str)
        assert needle in grep_out

    scenario = E2EScenario(
        name="isolated-forge-grep-multi-file",
        system_prompt=_ISOLATED_SYSTEM_PROMPT,
        user_prompt=(
            f"Under {parent!r} there are three text files: plain-a.txt, {target_basename}, "
            f"and plain-b.txt. Use grep_file_content to find which file contains the literal "
            f"{needle!r} and report its basename."
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


@pytest.mark.e2e_scenario("file-size-bytes")
async def test_forge_file_size_bytes(
    request: Any,
    mcp_application_isolated: Any,
    isolated_e2e_space: IsolatedE2ESpace,
    onedata_admin_token: str,
    forge_api_key: str,
    forge_model: str,
    forge_base_url: str,
) -> None:
    logical_path = f"{isolated_e2e_space.root_path}/e2e-forge-size/payload.txt"
    content = "forge-size-probe"

    async def setup(space: IsolatedE2ESpace, admin: str) -> None:
        await seed_file(logical_path, content, admin_token=admin)

    async def verify(space: IsolatedE2ESpace, app: Any) -> None:
        size = await ground_truth_file_size_bytes(app, logical_path)
        assert size == len(content.encode())

    scenario = E2EScenario(
        name="isolated-forge-file-size-bytes",
        system_prompt=_ISOLATED_SYSTEM_PROMPT,
        user_prompt=(
            f"What is the size in bytes of {logical_path!r}? "
            "Use get_file_attributes and return only the number."
        ),
        required_tools=frozenset({"get_file_attributes"}),
        require_no_extra_tool_calls=True,
        forbidden_tools=frozenset({"grep_file_content", "download_file"}),
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


@pytest.mark.e2e_scenario("schema-match-all")
async def test_forge_schema_match_all(
    request: Any,
    mcp_application_isolated: Any,
    isolated_e2e_space: IsolatedE2ESpace,
    onedata_admin_token: str,
    forge_api_key: str,
    forge_model: str,
    forge_base_url: str,
) -> None:
    harvester_id, index_id = await require_harvester_index(isolated_e2e_space)
    probe_path = f"{isolated_e2e_space.root_path}/e2e-harvest/probe.txt"

    async def setup(space: IsolatedE2ESpace, admin: str) -> None:
        await seed_file(probe_path, "harvest-probe\n", admin_token=admin)
        await wait_for_harvester_hits(harvester_id, index_id)

    async def verify(space: IsolatedE2ESpace, app: Any) -> None:
        _ = space
        body = await mcp_tool_json_result(
            app,
            "query_harvester_index",
            {
                "harvester_id": harvester_id,
                "index_id": index_id,
                "query": harvester_index_query(
                    "post",
                    "_search",
                    harvester_es_search_query({"size": 1, "query": {"match_all": {}}}),
                ),
            },
        )
        total = es_hits_total(body)
        assert total is not None and total >= 1

    scenario = E2EScenario(
        name="isolated-forge-schema-match-all",
        system_prompt=_ISOLATED_SYSTEM_PROMPT,
        user_prompt=(
            f"On harvester {harvester_id!r} index {index_id!r}: load the index schema, "
            "then run a match_all query with size=1."
        ),
        required_tools=frozenset({"get_harvester_index_schema", "query_harvester_index"}),
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
        setup=setup,
        verify_state=verify,
    )

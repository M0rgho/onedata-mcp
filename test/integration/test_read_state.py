"""Isolated E2E: section 1 read-state scenarios (confined token; datasets omitted)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from e2e_isolated_space import IsolatedE2ESpace
from e2e_oracles import assert_list_spaces_oracle, assert_paths_under_prefix
from env_checks import onedata_credentials_available
from isolated_helpers import child_names, recursive_paths, seed_file
from onedata_mcp.api.spaces import list_available_spaces
from plgrid_ground_truth import ground_truth_file_size_bytes, mcp_tool_json_result

READ_STATE_SPACE_GROUP = "read-state"

_BINARY_256_FIXTURE = Path(__file__).resolve().parent / "fixtures" / "binary_256.bin"

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.e2e_isolated,
    pytest.mark.onedata_integration,
    pytest.mark.e2e_isolated_space_group(READ_STATE_SPACE_GROUP),
    pytest.mark.skipif(
        not onedata_credentials_available(),
        reason="ONEDATA_ONEZONE_* and ONEDATA_ONEPROVIDER_* required (see docs/e2e-isolated-spaces.md)",
    ),
]


@pytest.mark.e2e_scenario("list-spaces")
async def test_list_spaces(
    mcp_application_isolated: Any,
    isolated_e2e_space: IsolatedE2ESpace,
) -> None:
    """`list-spaces`: confined token sees only the shared isolated space."""
    expected_name = isolated_e2e_space.space_name
    expected_id = isolated_e2e_space.space_id

    via_mcp = await mcp_tool_json_result(mcp_application_isolated, "list_available_spaces", {})
    assert_list_spaces_oracle(
        via_mcp,
        expected_name=expected_name,
        expected_id=expected_id,
    )

    via_api = await list_available_spaces()
    assert_list_spaces_oracle(
        via_api,
        expected_name=expected_name,
        expected_id=expected_id,
    )


@pytest.mark.e2e_scenario("file-id-roundtrip")
async def test_file_id_roundtrip(
    mcp_application_isolated: Any,
    isolated_e2e_space: IsolatedE2ESpace,
    onedata_admin_token: str,
) -> None:
    """`file-id-roundtrip`: path → id → attributes by id."""
    logical_path = f"{isolated_e2e_space.root_path}/e2e-roundtrip/hello.txt"
    expected_name = "hello.txt"

    await seed_file(logical_path, "roundtrip-body\n", admin_token=onedata_admin_token)
    file_id = await mcp_tool_json_result(
        mcp_application_isolated,
        "get_file_id",
        {"path": logical_path},
    )
    assert isinstance(file_id, str) and file_id

    attrs = await mcp_tool_json_result(
        mcp_application_isolated,
        "get_file_attributes",
        {"file_id_or_path": file_id, "attributes": ["fileId", "name", "path"]},
    )
    assert isinstance(attrs, dict)
    assert attrs.get("fileId") == file_id
    assert attrs.get("name") == expected_name
    assert attrs.get("path") in {logical_path.lstrip("/"), logical_path}


@pytest.mark.e2e_scenario("path-by-file-id")
async def test_path_by_file_id(
    mcp_application_isolated: Any,
    isolated_e2e_space: IsolatedE2ESpace,
    onedata_admin_token: str,
) -> None:
    """`path-by-file-id`: attributes by opaque id report the logical path."""
    logical_path = f"{isolated_e2e_space.root_path}/e2e-path-by-id/target.txt"
    expected_path = logical_path.lstrip("/")

    await seed_file(logical_path, "path-by-id\n", admin_token=onedata_admin_token)
    file_id = await mcp_tool_json_result(
        mcp_application_isolated,
        "get_file_id",
        {"path": logical_path},
    )
    assert isinstance(file_id, str) and file_id

    attrs = await mcp_tool_json_result(
        mcp_application_isolated,
        "get_file_attributes",
        {"file_id_or_path": file_id, "attributes": ["path", "fileId"]},
    )
    assert isinstance(attrs, dict)
    reported = attrs.get("path")
    assert isinstance(reported, str)
    assert reported in {expected_path, logical_path}


@pytest.mark.e2e_scenario("list-children")
async def test_list_children(
    mcp_application_isolated: Any,
    isolated_e2e_space: IsolatedE2ESpace,
    onedata_admin_token: str,
) -> None:
    """`list-children`: shallow listing includes the expected child basename."""
    parent_path = f"{isolated_e2e_space.root_path}/e2e-children"
    child_basename = "child-a.txt"

    await seed_file(f"{parent_path}/{child_basename}", "child-a\n", admin_token=onedata_admin_token)
    await seed_file(f"{parent_path}/child-b.txt", "child-b\n", admin_token=onedata_admin_token)

    listing = await mcp_tool_json_result(
        mcp_application_isolated,
        "list_files",
        {"parent_id_or_path": parent_path, "limit": 50},
    )
    assert child_basename in child_names(listing)


@pytest.mark.e2e_scenario("recursive-prefix")
async def test_recursive_prefix(
    mcp_application_isolated: Any,
    isolated_e2e_space: IsolatedE2ESpace,
    onedata_admin_token: str,
) -> None:
    """`recursive-prefix`: every returned path starts with the prefix."""
    root = f"{isolated_e2e_space.root_path}/e2e-recursive"
    prefix = "nested/"
    await seed_file(f"{root}/{prefix}leaf.txt", "leaf\n", admin_token=onedata_admin_token)
    await seed_file(f"{root}/other.txt", "other\n", admin_token=onedata_admin_token)

    listing = await mcp_tool_json_result(
        mcp_application_isolated,
        "list_files_recursive",
        {
            "parent_id_or_path": root,
            "prefix": prefix,
            "limit": 50,
        },
    )
    paths = recursive_paths(listing)
    assert paths, "expected at least one file under prefix"
    assert_paths_under_prefix(paths, prefix)


@pytest.mark.e2e_scenario("recursive-continue")
async def test_recursive_continue(
    mcp_application_isolated: Any,
    isolated_e2e_space: IsolatedE2ESpace,
    onedata_admin_token: str,
) -> None:
    """`recursive-continue`: start_after skips lexicographically earlier paths."""
    root = f"{isolated_e2e_space.root_path}/e2e-continue"
    await seed_file(f"{root}/aaa.txt", "a\n", admin_token=onedata_admin_token)
    await seed_file(f"{root}/zzz.txt", "z\n", admin_token=onedata_admin_token)

    listing = await mcp_tool_json_result(
        mcp_application_isolated,
        "list_files_recursive",
        {"parent_id_or_path": root, "start_after": "mmm", "limit": 50},
    )
    paths = recursive_paths(listing)
    assert all(path > "mmm" for path in paths)


@pytest.mark.e2e_scenario("file-size-bytes")
async def test_file_size_bytes(
    mcp_application_isolated: Any,
    isolated_e2e_space: IsolatedE2ESpace,
    onedata_admin_token: str,
) -> None:
    """`file-size-bytes`: attribute size matches seeded content length."""
    logical_path = f"{isolated_e2e_space.root_path}/e2e-size/payload.bin"
    content = "exact-size-body"
    expected_bytes = len(content.encode())

    await seed_file(logical_path, content, admin_token=onedata_admin_token)
    size = await ground_truth_file_size_bytes(mcp_application_isolated, logical_path)
    assert size == expected_bytes


@pytest.mark.e2e_scenario("grep-needle")
async def test_grep_needle(
    mcp_application_isolated: Any,
    isolated_e2e_space: IsolatedE2ESpace,
    onedata_admin_token: str,
) -> None:
    """`grep-needle`: grep output contains the literal needle."""
    logical_path = f"{isolated_e2e_space.root_path}/e2e-grep/needle.txt"
    needle = "UNIQUE_NEEDLE_42"

    await seed_file(logical_path, f"before\n{needle}\nafter\n", admin_token=onedata_admin_token)
    grep_out = await mcp_tool_json_result(
        mcp_application_isolated,
        "grep_file_content",
        {"file_id_or_path": logical_path, "pattern": needle},
    )
    assert isinstance(grep_out, str)
    assert needle in grep_out


@pytest.mark.e2e_scenario("grep-header")
async def test_grep_header(
    mcp_application_isolated: Any,
    isolated_e2e_space: IsolatedE2ESpace,
    onedata_admin_token: str,
) -> None:
    """`grep-header`: grep finds a header line substring."""
    logical_path = f"{isolated_e2e_space.root_path}/e2e-grep/header.log"
    header = "X-E2E-HEADER: ok"

    await seed_file(logical_path, f"{header}\nbody\n", admin_token=onedata_admin_token)
    grep_out = await mcp_tool_json_result(
        mcp_application_isolated,
        "grep_file_content",
        {"file_id_or_path": logical_path, "pattern": header},
    )
    assert isinstance(grep_out, str) and header in grep_out


@pytest.mark.e2e_scenario("first-line")
async def test_first_line(
    mcp_application_isolated: Any,
    isolated_e2e_space: IsolatedE2ESpace,
    onedata_admin_token: str,
) -> None:
    """`first-line`: first line of file matches oracle via grep."""
    logical_path = f"{isolated_e2e_space.root_path}/e2e-grep/first.txt"
    first_line = "FIRST_LINE_ORACLE"

    await seed_file(logical_path, f"{first_line}\nsecond\n", admin_token=onedata_admin_token)
    grep_out = await mcp_tool_json_result(
        mcp_application_isolated,
        "grep_file_content",
        {"file_id_or_path": logical_path, "pattern": first_line},
    )
    assert grep_out.strip() == first_line


@pytest.mark.e2e_scenario("size-and-grep")
async def test_size_and_grep(
    mcp_application_isolated: Any,
    isolated_e2e_space: IsolatedE2ESpace,
    onedata_admin_token: str,
) -> None:
    """`size-and-grep`: size and grep needle both match oracle."""
    logical_path = f"{isolated_e2e_space.root_path}/e2e-size-grep/combo.txt"
    content = "combo-SIZE_AND_GREP_MARKER\n"
    needle = "SIZE_AND_GREP_MARKER"

    await seed_file(logical_path, content, admin_token=onedata_admin_token)
    size = await ground_truth_file_size_bytes(mcp_application_isolated, logical_path)
    assert size == len(content.encode())
    grep_out = await mcp_tool_json_result(
        mcp_application_isolated,
        "grep_file_content",
        {"file_id_or_path": logical_path, "pattern": needle},
    )
    assert isinstance(grep_out, str) and needle in grep_out


@pytest.mark.e2e_scenario("find-doi")
async def test_find_doi(
    mcp_application_isolated: Any,
    isolated_e2e_space: IsolatedE2ESpace,
    onedata_admin_token: str,
) -> None:
    """`find-doi`: recursive grep under root finds DOI substring."""
    root = f"{isolated_e2e_space.root_path}/e2e-doi"
    target = f"{root}/paper.txt"
    doi = "10.1234/e2e-isolated-doi"

    await seed_file(target, f"metadata doi:{doi}\n", admin_token=onedata_admin_token)
    grep_out = await mcp_tool_json_result(
        mcp_application_isolated,
        "grep_file_content",
        {"file_id_or_path": target, "pattern": doi},
    )
    assert isinstance(grep_out, str) and doi in grep_out


@pytest.mark.e2e_scenario("binary-size-only")
async def test_binary_size_only(
    mcp_application_isolated: Any,
    isolated_e2e_space: IsolatedE2ESpace,
    onedata_admin_token: str,
) -> None:
    """`binary-size-only`: size probe without grep (read path)."""
    logical_path = f"{isolated_e2e_space.root_path}/e2e-binary/blob.bin"
    payload = _BINARY_256_FIXTURE.read_bytes()
    assert len(payload) == 256

    await seed_file(logical_path, payload, admin_token=onedata_admin_token)
    size = await ground_truth_file_size_bytes(mcp_application_isolated, logical_path)
    assert size == len(payload)

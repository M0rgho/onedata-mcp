"""Isolated E2E: section 2 write-state scenarios (read-write confined MCP token)."""

from __future__ import annotations

import json
from typing import Any

import pytest
from e2e_isolated_space import IsolatedE2ESpace
from env_checks import onedata_credentials_available
from isolated_helpers import child_names, recursive_paths, seed_file
from plgrid_ground_truth import mcp_tool_json_result

WRITE_STATE_SPACE_GROUP = "write-state"

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.e2e_isolated,
    pytest.mark.e2e_isolated_confined_write,
    pytest.mark.onedata_integration,
    pytest.mark.e2e_isolated_space_group(WRITE_STATE_SPACE_GROUP),
    pytest.mark.skipif(
        not onedata_credentials_available(),
        reason="ONEDATA_ONEZONE_* and ONEDATA_ONEPROVIDER_* required (see docs/e2e-isolated-spaces.md)",
    ),
]


@pytest.mark.e2e_scenario("create-xattr-delete")
async def test_create_xattr_delete(
    mcp_application_isolated: Any,
    isolated_e2e_space: IsolatedE2ESpace,
) -> None:
    """`create-xattr-delete`: create, xattr, list, delete lifecycle under confined write token."""
    path = f"{isolated_e2e_space.root_path}/e2e-write/run-file.txt"
    run_id = "e2e-run-001"
    parent = path.rsplit("/", 1)[0]
    basename = "run-file.txt"

    await mcp_tool_json_result(
        mcp_application_isolated,
        "create_file",
        {"path": path, "content": "lifecycle\n", "create_parents": True},
    )
    listing = await mcp_tool_json_result(
        mcp_application_isolated,
        "list_files",
        {"parent_id_or_path": parent, "limit": 50},
    )
    assert basename in child_names(listing)

    await mcp_tool_json_result(
        mcp_application_isolated,
        "set_file_xattrs",
        {"file_id_or_path": path, "xattrs": {"testRunId": run_id}},
    )
    meta = await mcp_tool_json_result(
        mcp_application_isolated,
        "get_file_metadata",
        {"file_id_or_path": path, "metadata_types": ["xattrs"]},
    )
    assert isinstance(meta, dict)
    xattrs = meta.get("xattrs")
    assert isinstance(xattrs, dict)
    assert xattrs.get("testRunId") == run_id

    await mcp_tool_json_result(mcp_application_isolated, "delete_file", {"file_id_or_path": path})
    listing_after = await mcp_tool_json_result(
        mcp_application_isolated,
        "list_files",
        {"parent_id_or_path": parent, "limit": 50},
    )
    assert basename not in child_names(listing_after)


@pytest.mark.e2e_scenario("create-nested")
async def test_create_nested(
    mcp_application_isolated: Any,
    isolated_e2e_space: IsolatedE2ESpace,
) -> None:
    """`create-nested`: create_parents + download matches content."""
    nested_path = f"{isolated_e2e_space.root_path}/deep/nested/leaf.txt"
    content = "nested-content"

    file_id = await mcp_tool_json_result(
        mcp_application_isolated,
        "create_file",
        {"path": nested_path, "content": content, "create_parents": True},
    )
    assert isinstance(file_id, str) and file_id

    resolved = await mcp_tool_json_result(
        mcp_application_isolated,
        "get_file_id",
        {"path": nested_path},
    )
    assert resolved == file_id

    attrs = await mcp_tool_json_result(
        mcp_application_isolated,
        "get_file_attributes",
        {"file_id_or_path": file_id, "attributes": ["size", "fileId"]},
    )
    assert isinstance(attrs, dict)
    assert attrs.get("fileId") == file_id
    assert attrs.get("size") == len(content.encode())


@pytest.mark.e2e_scenario("xattrs-only")
async def test_xattrs_only(
    mcp_application_isolated: Any,
    isolated_e2e_space: IsolatedE2ESpace,
    onedata_admin_token: str,
) -> None:
    """`xattrs-only`: set xattrs without changing json/rdf blobs."""
    path = f"{isolated_e2e_space.root_path}/e2e-meta/xattrs-only.txt"
    await seed_file(path, "meta\n", admin_token=onedata_admin_token)

    await mcp_tool_json_result(
        mcp_application_isolated,
        "set_file_metadata",
        {
            "file_id_or_path": path,
            "metadata_type": "json",
            "metadata": {"seed": "baseline"},
        },
    )
    before = await mcp_tool_json_result(
        mcp_application_isolated,
        "get_file_metadata",
        {"file_id_or_path": path, "metadata_types": ["json", "xattrs"]},
    )
    json_before = before.get("json") if isinstance(before, dict) else None

    await mcp_tool_json_result(
        mcp_application_isolated,
        "set_file_xattrs",
        {"file_id_or_path": path, "xattrs": {"license": "CC-0", "provenance": "e2e"}},
    )
    after = await mcp_tool_json_result(
        mcp_application_isolated,
        "get_file_metadata",
        {"file_id_or_path": path, "metadata_types": ["json", "xattrs"]},
    )
    assert isinstance(after, dict)
    assert after.get("json") == json_before
    xattrs = after.get("xattrs")
    assert isinstance(xattrs, dict)
    assert xattrs.get("license") == "CC-0"
    assert xattrs.get("provenance") == "e2e"


@pytest.mark.e2e_scenario("json-metadata")
async def test_json_metadata(
    mcp_application_isolated: Any,
    isolated_e2e_space: IsolatedE2ESpace,
    onedata_admin_token: str,
) -> None:
    """`json-metadata`: replace JSON metadata; xattrs unchanged."""
    path = f"{isolated_e2e_space.root_path}/e2e-meta/json-target.txt"
    await seed_file(path, "body\n", admin_token=onedata_admin_token)

    await mcp_tool_json_result(
        mcp_application_isolated,
        "set_file_xattrs",
        {"file_id_or_path": path, "xattrs": {"keep": "yes"}},
    )
    doc = {"title": "e2e-json", "version": 2}
    await mcp_tool_json_result(
        mcp_application_isolated,
        "set_file_metadata",
        {"file_id_or_path": path, "metadata_type": "json", "metadata": doc},
    )
    meta = await mcp_tool_json_result(
        mcp_application_isolated,
        "get_file_metadata",
        {"file_id_or_path": path, "metadata_types": ["json", "xattrs"]},
    )
    assert isinstance(meta, dict)
    assert meta.get("json") == doc
    xattrs = meta.get("xattrs")
    assert isinstance(xattrs, dict)
    assert xattrs.get("keep") == "yes"


@pytest.mark.e2e_scenario("create-recursive-delete")
async def test_create_recursive_delete(
    mcp_application_isolated: Any,
    isolated_e2e_space: IsolatedE2ESpace,
) -> None:
    """`create-recursive-delete`: file appears in recursive list then is removed."""
    parent = f"{isolated_e2e_space.root_path}/e2e-rec-delete"
    path = f"{parent}/visible.txt"
    basename = "visible.txt"

    await mcp_tool_json_result(
        mcp_application_isolated,
        "create_file",
        {"path": path, "content": "tmp\n", "create_parents": True},
    )
    listing = await mcp_tool_json_result(
        mcp_application_isolated,
        "list_files_recursive",
        {"parent_id_or_path": parent, "limit": 50},
    )
    assert basename in {p.split("/")[-1] for p in recursive_paths(listing)}

    await mcp_tool_json_result(mcp_application_isolated, "delete_file", {"file_id_or_path": path})
    listing_after = await mcp_tool_json_result(
        mcp_application_isolated,
        "list_files_recursive",
        {"parent_id_or_path": parent, "limit": 50},
    )
    assert basename not in {p.split("/")[-1] for p in recursive_paths(listing_after)}


@pytest.mark.e2e_scenario("xattrs-merge-formats")
async def test_xattrs_merge_formats(
    mcp_application_isolated: Any,
    isolated_e2e_space: IsolatedE2ESpace,
) -> None:
    """`xattrs-merge-formats`: dict then JSON string merge to expected xattrs."""
    path = f"{isolated_e2e_space.root_path}/e2e-xattr-merge/target.txt"
    await mcp_tool_json_result(
        mcp_application_isolated,
        "create_file",
        {"path": path, "content": "x\n", "create_parents": True},
    )

    await mcp_tool_json_result(
        mcp_application_isolated,
        "set_file_xattrs",
        {"file_id_or_path": path, "xattrs": {"a": "1", "b": "2"}},
    )
    await mcp_tool_json_result(
        mcp_application_isolated,
        "set_file_xattrs",
        {"file_id_or_path": path, "xattrs": json.dumps({"b": "updated", "c": "3"})},
    )
    meta = await mcp_tool_json_result(
        mcp_application_isolated,
        "get_file_metadata",
        {"file_id_or_path": path, "metadata_types": ["xattrs"]},
    )
    xattrs = meta.get("xattrs") if isinstance(meta, dict) else None
    assert isinstance(xattrs, dict)
    assert xattrs.get("a") == "1"
    assert xattrs.get("b") == "updated"
    assert xattrs.get("c") == "3"

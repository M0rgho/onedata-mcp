"""Shared helpers for isolated E2E tests (confined token + admin seeding)."""

from __future__ import annotations

from typing import Any

from e2e_isolated_space import (
    IsolatedE2ESpace,
    ensure_isolated_space_harvester,
    use_admin_oneprovider_token,
)

from onedata_mcp.api.files import create_file, create_file_bytes
from onedata_mcp.api.harvesters import (
    harvester_es_search_query,
    harvester_index_query,
    list_user_harvesters,
    unwrap_harvester_query_response,
)


async def seed_file(
    path: str,
    content: str | bytes,
    *,
    admin_token: str,
    create_parents: bool = True,
) -> None:
    """Create a file using the admin token (not the confined MCP macaroon)."""

    async with use_admin_oneprovider_token(admin_token):
        if isinstance(content, bytes):
            await create_file_bytes(path, content, create_parents=create_parents)
        else:
            await create_file(path, content, create_parents=create_parents)


def harvester_index_for_space(
    harvesters: list[dict[str, Any]],
    *,
    space_id: str,
) -> tuple[str, str] | None:
    """Return ``(harvester_id, index_id)`` for a harvester attached to ``space_id``."""

    for row in harvesters:
        if not isinstance(row, dict):
            continue
        attached = row.get("attached_spaces")
        if not isinstance(attached, list):
            continue
        space_ids = {
            entry.get("space_id")
            for entry in attached
            if isinstance(entry, dict) and isinstance(entry.get("space_id"), str)
        }
        if space_id not in space_ids:
            continue
        harvester_id = row.get("harvesterId")
        indices = row.get("indices")
        if not isinstance(harvester_id, str) or not isinstance(indices, list) or not indices:
            continue
        first = indices[0]
        if not isinstance(first, dict):
            continue
        index_id = first.get("indexId") or first.get("index_id")
        if isinstance(index_id, str):
            return harvester_id, index_id
    return None


async def pick_harvester_index(
    space: IsolatedE2ESpace,
) -> tuple[str, str] | None:
    rows = await list_user_harvesters()
    return harvester_index_for_space(rows, space_id=space.space_id)


async def require_harvester_index(space: IsolatedE2ESpace) -> tuple[str, str]:
    """Return harvester/index for ``space``; provision attachment if the fixture missed it."""
    pair = await pick_harvester_index(space)
    if pair is not None:
        return pair
    await ensure_isolated_space_harvester(space)
    pair = await pick_harvester_index(space)
    if pair is None:
        msg = (
            "No harvester index attached to the isolated E2E space "
            f"{space.space_name!r} ({space.space_id}) after ensure_isolated_space_harvester"
        )
        raise AssertionError(msg)
    return pair


def es_hits_total(body: object) -> int | None:
    body = unwrap_harvester_query_response(body)
    if not isinstance(body, dict):
        return None
    hits = body.get("hits")
    if not isinstance(hits, dict):
        return None
    total = hits.get("total")
    if isinstance(total, dict):
        value = total.get("value")
        return int(value) if isinstance(value, int) else None
    if isinstance(total, int):
        return total
    return None


def child_names(listing: object) -> set[str]:
    if not isinstance(listing, dict):
        return set()
    children = listing.get("children")
    if not isinstance(children, list):
        return set()
    return {
        entry.get("name")
        for entry in children
        if isinstance(entry, dict) and isinstance(entry.get("name"), str)
    }


def recursive_paths(listing: object) -> list[str]:
    if not isinstance(listing, dict):
        return []
    files = listing.get("files")
    if not isinstance(files, list):
        return []
    paths: list[str] = []
    for entry in files:
        if isinstance(entry, dict) and isinstance(entry.get("path"), str):
            paths.append(entry["path"])
    return paths


async def wait_for_harvester_hits(
    harvester_id: str,
    index_id: str,
    *,
    min_hits: int = 1,
    timeout_s: float = 120.0,
    poll_interval_s: float = 3.0,
) -> int:
    """Poll ``match_all`` until the index reports at least ``min_hits`` documents."""
    import asyncio
    import time

    from onedata_mcp.api.harvesters import query_harvester_index

    deadline = time.monotonic() + timeout_s
    last_total: int | None = None
    while time.monotonic() < deadline:
        body = await query_harvester_index(
            harvester_id,
            index_id,
            harvester_index_query(
                "post",
                "_search",
                harvester_es_search_query({"size": 0, "query": {"match_all": {}}}),
            ),
        )
        last_total = es_hits_total(body)
        if last_total is not None and last_total >= min_hits:
            return last_total
        await asyncio.sleep(poll_interval_s)
    msg = (
        f"Harvester index {index_id} on {harvester_id} had {last_total!r} hits after {timeout_s}s; "
        f"expected >={min_hits} (harvesting may be slow — seed a file and retry)"
    )
    raise TimeoutError(msg)

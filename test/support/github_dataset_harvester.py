"""Discover github_dataset harvester fixtures via live MCP (no hardcoded oracles)."""

from __future__ import annotations

import json
import re
from typing import Any

# Internal nicknames for Forge prompts; must not appear in the matched repository slug.
_CONCEPT_ALIASES = ("pet", "portal", "hub", "stack", "core", "cloud")

from fastmcp import FastMCP
from onedata_mcp.api.harvesters import (
    harvester_es_search_query,
    harvester_index_query,
    unwrap_harvester_query_response,
)
from isolated_helpers import es_hits_total
from plgrid_ground_truth import mcp_tool_json_result

GITHUB_DATASET_SPACE = "github_dataset"
GITHUB_DATASET_DIR = f"/{GITHUB_DATASET_SPACE}/{GITHUB_DATASET_SPACE}"
GITHUB_INDEX_NAME = "github-index"


class GithubDatasetHarvesterNotFoundError(RuntimeError):
    """Raised when the shared tenant has no Github harvester / github-index."""


async def discover_github_dataset_space_id(app: FastMCP) -> str:
    spaces = await mcp_tool_json_result(app, "list_available_spaces", {})
    if not isinstance(spaces, list):
        msg = "list_available_spaces did not return a list"
        raise AssertionError(msg)
    for row in spaces:
        if isinstance(row, dict) and row.get("name") == GITHUB_DATASET_SPACE:
            space_id = row.get("spaceId")
            if isinstance(space_id, str) and space_id:
                return space_id
    msg = f"Space {GITHUB_DATASET_SPACE!r} not found on provider"
    raise AssertionError(msg)


async def discover_github_harvester_bundle(app: FastMCP) -> tuple[str, str, str]:
    """Return ``(harvester_id, github_index_id, space_id)`` from MCP."""

    space_id = await discover_github_dataset_space_id(app)
    rows = await mcp_tool_json_result(
        app,
        "list_user_harvesters",
        {"space_name": GITHUB_DATASET_SPACE},
    )
    if not isinstance(rows, list) or not rows:
        raise GithubDatasetHarvesterNotFoundError(
            f"No harvesters attached to {GITHUB_DATASET_SPACE!r}"
        )

    harvester: dict[str, Any] | None = None
    for row in rows:
        if not isinstance(row, dict):
            continue
        name = row.get("name")
        if isinstance(name, str) and "github" in name.lower():
            harvester = row
            break
    if harvester is None:
        harvester = rows[0] if isinstance(rows[0], dict) else None
    if not harvester:
        raise GithubDatasetHarvesterNotFoundError("No harvester row in list_user_harvesters")

    harvester_id = harvester.get("harvesterId")
    indices = harvester.get("indices")
    if not isinstance(harvester_id, str) or not isinstance(indices, list):
        raise GithubDatasetHarvesterNotFoundError("Harvester row missing harvesterId or indices")

    index_id = _pick_github_index_id(indices)
    if index_id is None:
        raise GithubDatasetHarvesterNotFoundError(
            f"No index named {GITHUB_INDEX_NAME!r} on harvester {harvester_id!r}"
        )

    attached = harvester.get("attached_spaces")
    if isinstance(attached, list):
        attached_ids = {
            entry.get("space_id")
            for entry in attached
            if isinstance(entry, dict) and isinstance(entry.get("space_id"), str)
        }
        if space_id not in attached_ids:
            msg = (
                f"Harvester {harvester_id!r} attached_spaces {sorted(attached_ids)} "
                f"does not include discovered space_id {space_id!r}"
            )
            raise AssertionError(msg)

    return harvester_id, index_id, space_id


def _pick_github_index_id(indices: list[Any]) -> str | None:
    for entry in indices:
        if not isinstance(entry, dict):
            continue
        if entry.get("name") == GITHUB_INDEX_NAME:
            index_id = entry.get("indexId") or entry.get("index_id")
            if isinstance(index_id, str):
                return index_id
    return None


async def discover_listed_event_file(app: FastMCP) -> tuple[str, str]:
    """Return ``(basename, logical_path)`` for one ``.dat`` file under the dataset tree."""

    listing = await mcp_tool_json_result(
        app,
        "list_files",
        {"parent_id_or_path": GITHUB_DATASET_DIR, "limit": 100},
    )
    if not isinstance(listing, dict):
        msg = "list_files returned non-object"
        raise AssertionError(msg)
    children = listing.get("children")
    if not isinstance(children, list):
        msg = "list_files children missing"
        raise AssertionError(msg)

    for child in children:
        if not isinstance(child, dict):
            continue
        if child.get("type") != "REG":
            continue
        name = child.get("name")
        path = child.get("path")
        if isinstance(name, str) and name.endswith(".dat") and isinstance(path, str):
            return name, path

    msg = f"No .dat files under {GITHUB_DATASET_DIR} in first list_files page"
    raise AssertionError(msg)


async def mcp_harvester_search(
    app: FastMCP,
    harvester_id: str,
    index_id: str,
    es_body: dict[str, Any],
) -> dict[str, Any]:
    raw = await mcp_tool_json_result(
        app,
        "query_harvester_index",
        {
            "harvester_id": harvester_id,
            "index_id": index_id,
            "query": harvester_index_query("post", "_search", harvester_es_search_query(es_body)),
        },
    )
    parsed = unwrap_harvester_query_response(raw)
    return parsed if isinstance(parsed, dict) else {}


def first_search_hit(body: dict[str, Any]) -> dict[str, Any] | None:
    hits = body.get("hits")
    if not isinstance(hits, dict):
        return None
    items = hits.get("hits")
    if not isinstance(items, list) or not items:
        return None
    first = items[0]
    return first if isinstance(first, dict) else None


def hit_source(hit: dict[str, Any]) -> dict[str, Any]:
    source = hit.get("_source")
    return source if isinstance(source, dict) else {}


def onedata_meta(source: dict[str, Any]) -> dict[str, Any]:
    meta = source.get("__onedata")
    return meta if isinstance(meta, dict) else {}


def indexed_event_type(source: dict[str, Any]) -> str | None:
    value = source.get("type")
    return value if isinstance(value, str) and value else None


def indexed_repo_slug(source: dict[str, Any]) -> str | None:
    repo = source.get("repo")
    if not isinstance(repo, dict):
        return None
    name = repo.get("name")
    return name if isinstance(name, str) and name else None


def indexed_actor_login(source: dict[str, Any]) -> str | None:
    actor = source.get("actor")
    if not isinstance(actor, dict):
        return None
    login = actor.get("login")
    return login if isinstance(login, str) and login else None


def schema_declares_field(schema_payload: object, field_name: str) -> bool:
    if not isinstance(schema_payload, dict):
        return False
    raw = schema_payload.get("schema")
    if isinstance(raw, str):
        return field_name in raw
    if isinstance(raw, dict):
        return field_name in json.dumps(raw)
    return field_name in json.dumps(schema_payload)


async def discover_indexed_event_with_repo(
    app: FastMCP,
    harvester_id: str,
    index_id: str,
    *,
    sample_size: int = 25,
) -> tuple[str, str, str]:
    """Return ``(event_type, repo_slug, basename)`` from a row that has all three."""

    body = await mcp_harvester_search(
        app,
        harvester_id,
        index_id,
        {
            "size": sample_size,
            "query": {"match_all": {}},
            "_source": ["type", "repo", "__onedata"],
        },
    )
    hits = body.get("hits")
    if not isinstance(hits, dict):
        msg = "match_all response missing hits"
        raise AssertionError(msg)
    items = hits.get("hits")
    if not isinstance(items, list):
        msg = "match_all response missing hits.hits"
        raise AssertionError(msg)

    for item in items:
        if not isinstance(item, dict):
            continue
        source = hit_source(item)
        event_type = indexed_event_type(source)
        repo_slug = indexed_repo_slug(source)
        basename = onedata_meta(source).get("fileName")
        if event_type and repo_slug and isinstance(basename, str) and basename:
            return event_type, repo_slug, basename

    msg = (
        f"No github-index row with type, repo.name, and __onedata.fileName in "
        f"first {sample_size} match_all hits"
    )
    raise AssertionError(msg)


async def discover_push_event_actor_login(
    app: FastMCP,
    harvester_id: str,
    index_id: str,
    *,
    sample_size: int = 40,
) -> str:
    """Return ``actor.login`` for a row with ``type: PushEvent``."""

    body = await mcp_harvester_search(
        app,
        harvester_id,
        index_id,
        {
            "size": sample_size,
            "query": {"term": {"type": "PushEvent"}},
            "_source": ["type", "actor"],
        },
    )
    hits = body.get("hits")
    if not isinstance(hits, dict):
        msg = "PushEvent sample response missing hits"
        raise AssertionError(msg)
    items = hits.get("hits")
    if not isinstance(items, list):
        msg = "PushEvent sample response missing hits.hits"
        raise AssertionError(msg)
    for item in items:
        if not isinstance(item, dict):
            continue
        login = indexed_actor_login(hit_source(item))
        if login:
            return login

    msg = f"No PushEvent with actor.login in first {sample_size} hits"
    raise AssertionError(msg)


async def discover_top_push_event_actor(
    app: FastMCP,
    harvester_id: str,
    index_id: str,
    *,
    terms_size: int = 3,
) -> tuple[str, int]:
    """Return ``(actor.login, push_count)`` for the top PushEvent contributor."""

    body = await mcp_harvester_search(
        app,
        harvester_id,
        index_id,
        {
            "size": 0,
            "query": {"term": {"type": "PushEvent"}},
            "aggs": {
                "top_actors": {
                    "terms": {
                        "field": "actor.login",
                        "size": terms_size,
                        "order": {"_count": "desc"},
                    }
                }
            },
        },
    )
    aggs = body.get("aggregations")
    if not isinstance(aggs, dict):
        msg = "top PushEvent actor aggregation missing aggregations"
        raise AssertionError(msg)
    top_actors = aggs.get("top_actors")
    if not isinstance(top_actors, dict):
        msg = "top PushEvent actor aggregation missing top_actors"
        raise AssertionError(msg)
    buckets = top_actors.get("buckets")
    if not isinstance(buckets, list) or not buckets:
        msg = "No PushEvent actor buckets in terms aggregation"
        raise AssertionError(msg)
    first = buckets[0]
    if not isinstance(first, dict):
        msg = "Invalid top actor bucket"
        raise AssertionError(msg)
    login = first.get("key")
    count = first.get("doc_count")
    if not isinstance(login, str) or not login or not isinstance(count, int):
        msg = f"Unexpected top actor bucket shape: {first!r}"
        raise AssertionError(msg)
    return login, count


def _search_hits_list(body: dict[str, Any]) -> list[dict[str, Any]]:
    hits = body.get("hits")
    if not isinstance(hits, dict):
        return []
    items = hits.get("hits")
    if not isinstance(items, list):
        return []
    return [item for item in items if isinstance(item, dict)]


async def discover_actor_repo_push_pair(
    app: FastMCP,
    harvester_id: str,
    index_id: str,
    *,
    min_pushes: int = 5,
    actor_sample: int = 30,
    repo_sample: int = 30,
) -> tuple[str, str, int]:
    """Return ``(actor.login, repo.name, push_count)`` with at least ``min_pushes`` PushEvents."""

    body = await mcp_harvester_search(
        app,
        harvester_id,
        index_id,
        {
            "size": 0,
            "query": {"term": {"type": "PushEvent"}},
            "aggs": {
                "by_actor": {
                    "terms": {"field": "actor.login", "size": actor_sample},
                    "aggs": {
                        "by_repo": {
                            "terms": {
                                "field": "repo.name",
                                "size": repo_sample,
                                "min_doc_count": min_pushes,
                            }
                        }
                    },
                }
            },
        },
    )
    aggs = body.get("aggregations")
    if not isinstance(aggs, dict):
        msg = "actor/repo PushEvent aggregation missing aggregations"
        raise AssertionError(msg)
    by_actor = aggs.get("by_actor")
    if not isinstance(by_actor, dict):
        msg = "actor/repo PushEvent aggregation missing by_actor"
        raise AssertionError(msg)
    actor_buckets = by_actor.get("buckets")
    if not isinstance(actor_buckets, list):
        msg = "actor/repo PushEvent aggregation missing by_actor.buckets"
        raise AssertionError(msg)

    for actor_bucket in actor_buckets:
        if not isinstance(actor_bucket, dict):
            continue
        login = actor_bucket.get("key")
        if not isinstance(login, str) or not login:
            continue
        by_repo = actor_bucket.get("by_repo")
        if not isinstance(by_repo, dict):
            continue
        repo_buckets = by_repo.get("buckets")
        if not isinstance(repo_buckets, list):
            continue
        for repo_bucket in repo_buckets:
            if not isinstance(repo_bucket, dict):
                continue
            repo_slug = repo_bucket.get("key")
            count = repo_bucket.get("doc_count")
            if (
                isinstance(repo_slug, str)
                and repo_slug
                and isinstance(count, int)
                and count >= min_pushes
            ):
                return login, repo_slug, count

    msg = (
        f"No (actor, repo) PushEvent pair with at least {min_pushes} rows in "
        f"nested terms aggregation"
    )
    raise AssertionError(msg)


async def push_event_file_at_chronology_rank(
    app: FastMCP,
    harvester_id: str,
    index_id: str,
    actor_login: str,
    repo_slug: str,
    rank: int,
) -> tuple[str, str, Any]:
    """Return ``(basename, logical_path, mtime)`` for the ``rank``-th PushEvent (1-based, asc)."""

    if rank < 1:
        msg = f"rank must be >= 1, got {rank}"
        raise ValueError(msg)

    body = await mcp_harvester_search(
        app,
        harvester_id,
        index_id,
        {
            "size": rank,
            "query": {
                "bool": {
                    "must": [
                        {"term": {"type": "PushEvent"}},
                        {"term": {"actor.login": actor_login}},
                        {"term": {"repo.name": repo_slug}},
                    ]
                }
            },
            "sort": [{"created_at": {"order": "asc"}}],
            "_source": ["__onedata", "created_at", "type", "actor", "repo"],
        },
    )
    hits = _search_hits_list(body)
    if len(hits) < rank:
        msg = (
            f"Only {len(hits)} PushEvent rows for {actor_login!r} on {repo_slug!r}, "
            f"need rank {rank}"
        )
        raise AssertionError(msg)
    hit = hits[rank - 1]
    basename = onedata_meta(hit_source(hit)).get("fileName")
    if not isinstance(basename, str) or not basename:
        msg = f"PushEvent rank {rank} missing __onedata.fileName"
        raise AssertionError(msg)
    logical_path = f"{GITHUB_DATASET_DIR}/{basename}"
    attrs = await mcp_tool_json_result(
        app,
        "get_file_attributes",
        {
            "file_id_or_path": logical_path,
            "attributes": ["mtime", "name", "path"],
        },
    )
    if not isinstance(attrs, dict):
        msg = "get_file_attributes returned non-object"
        raise AssertionError(msg)
    mtime = attrs.get("mtime")
    if mtime is None:
        msg = f"No mtime on {logical_path!r}"
        raise AssertionError(msg)
    return basename, logical_path, mtime


async def discover_actor_repo_push_chronology_files(
    app: FastMCP,
    harvester_id: str,
    index_id: str,
    actor_login: str,
    repo_slug: str,
    *,
    fifth_rank: int = 5,
) -> tuple[str, Any, str, Any]:
    """Return ``(first_basename, first_mtime, fifth_basename, fifth_mtime)``."""

    first_base, _first_path, first_mtime = await push_event_file_at_chronology_rank(
        app, harvester_id, index_id, actor_login, repo_slug, 1
    )
    fifth_base, _fifth_path, fifth_mtime = await push_event_file_at_chronology_rank(
        app, harvester_id, index_id, actor_login, repo_slug, fifth_rank
    )
    return first_base, first_mtime, fifth_base, fifth_mtime


async def discover_earliest_push_event_file_mtime(
    app: FastMCP,
    harvester_id: str,
    index_id: str,
    actor_login: str,
) -> tuple[str, str, Any]:
    """Return ``(basename, logical_path, mtime)`` for the actor's earliest PushEvent row."""

    body = await mcp_harvester_search(
        app,
        harvester_id,
        index_id,
        {
            "size": 1,
            "query": {
                "bool": {
                    "must": [
                        {"term": {"type": "PushEvent"}},
                        {"term": {"actor.login": actor_login}},
                    ]
                }
            },
            "sort": [{"created_at": {"order": "asc"}}],
            "_source": ["__onedata", "created_at", "type", "actor"],
        },
    )
    hit = first_search_hit(body)
    if hit is None:
        msg = f"No PushEvent rows for actor {actor_login!r}"
        raise AssertionError(msg)
    basename = onedata_meta(hit_source(hit)).get("fileName")
    if not isinstance(basename, str) or not basename:
        msg = "Earliest PushEvent hit missing __onedata.fileName"
        raise AssertionError(msg)
    logical_path = f"{GITHUB_DATASET_DIR}/{basename}"
    attrs = await mcp_tool_json_result(
        app,
        "get_file_attributes",
        {
            "file_id_or_path": logical_path,
            "attributes": ["mtime", "name", "path"],
        },
    )
    if not isinstance(attrs, dict):
        msg = "get_file_attributes returned non-object"
        raise AssertionError(msg)
    mtime = attrs.get("mtime")
    if mtime is None:
        msg = f"No mtime on {logical_path!r}"
        raise AssertionError(msg)
    return basename, logical_path, mtime


def _push_event_repo_buckets(body: dict[str, Any]) -> list[tuple[str, int]]:
    aggs = body.get("aggregations")
    if not isinstance(aggs, dict):
        return []
    repos = aggs.get("repos")
    if not isinstance(repos, dict):
        return []
    buckets = repos.get("buckets")
    if not isinstance(buckets, list):
        return []
    out: list[tuple[str, int]] = []
    for bucket in buckets:
        if not isinstance(bucket, dict):
            continue
        slug = bucket.get("key")
        count = bucket.get("doc_count")
        if isinstance(slug, str) and slug and isinstance(count, int):
            out.append((slug, count))
    return out


def _tokens_from_repo_slug(repo_slug: str) -> list[str]:
    return [part for part in re.split(r"[/_.-]+", repo_slug) if len(part) >= 3]


def _repos_matching_substring(repos: list[tuple[str, int]], fragment: str) -> list[tuple[str, int]]:
    needle = fragment.lower()
    return [(slug, count) for slug, count in repos if needle in slug.lower()]


async def discover_concept_slug_mismatch_pair(
    app: FastMCP,
    harvester_id: str,
    index_id: str,
    *,
    min_pushes: int = 10,
    repo_terms_size: int = 500,
    concept_aliases: tuple[str, ...] = _CONCEPT_ALIASES,
) -> tuple[str, str, str, int]:
    """Return ``(concept_alias, slug_fragment, repo_slug, push_count)`` for an unambiguous partial match.

      The concept word (e.g. ``pet``) must not occur in ``repo_slug``; exactly one indexed repo
    must match the slug fragment (e.g. ``dog``) among PushEvent rows.
    """

    body = await mcp_harvester_search(
        app,
        harvester_id,
        index_id,
        {
            "size": 0,
            "query": {"term": {"type": "PushEvent"}},
            "aggs": {
                "repos": {
                    "terms": {
                        "field": "repo.name",
                        "size": repo_terms_size,
                        "min_doc_count": min_pushes,
                    }
                }
            },
        },
    )
    repos = _push_event_repo_buckets(body)
    if not repos:
        msg = "No PushEvent repositories in terms aggregation"
        raise AssertionError(msg)

    candidates: list[tuple[int, str, str, str, int]] = []
    for concept in concept_aliases:
        concept_l = concept.lower()
        if any(concept_l in slug.lower() for slug, _ in repos):
            continue
        for repo_slug, count in repos:
            if concept_l in repo_slug.lower():
                continue
            for token in _tokens_from_repo_slug(repo_slug):
                token_l = token.lower()
                if token_l == concept_l or len(token_l) < 3:
                    continue
                matches = _repos_matching_substring(repos, token)
                if len(matches) == 1 and matches[0][0] == repo_slug:
                    candidates.append((count, concept, token, repo_slug, count))

    if not candidates:
        msg = (
            "No unambiguous concept/slug-fragment pair "
            f"(concept not in slug; one repo per fragment; min_pushes={min_pushes})"
        )
        raise AssertionError(msg)

    candidates.sort(key=lambda row: row[0], reverse=True)
    _rank, concept, token, repo_slug, count = candidates[0]
    return concept, token, repo_slug, count


def _aggregate_org_push_counts(repos: list[tuple[str, int]]) -> dict[str, int]:
    org_counts: dict[str, int] = {}
    for slug, count in repos:
        if "/" not in slug:
            continue
        org = slug.split("/", 1)[0]
        if org:
            org_counts[org] = org_counts.get(org, 0) + count
    return org_counts


async def discover_org_prefix_with_min_pushes(
    app: FastMCP,
    harvester_id: str,
    index_id: str,
    *,
    min_pushes: int = 100,
    repo_terms_size: int = 500,
) -> tuple[str, int, int]:
    """Return ``(org_login, push_count, repo_count)`` for a busy ``owner/`` prefix."""

    body = await mcp_harvester_search(
        app,
        harvester_id,
        index_id,
        {
            "size": 0,
            "query": {"term": {"type": "PushEvent"}},
            "aggs": {
                "repos": {
                    "terms": {
                        "field": "repo.name",
                        "size": repo_terms_size,
                        "min_doc_count": 1,
                    }
                }
            },
        },
    )
    repos = _push_event_repo_buckets(body)
    org_counts = _aggregate_org_push_counts(repos)
    if not org_counts:
        msg = "No PushEvent org prefixes from repository terms aggregation"
        raise AssertionError(msg)

    ranked = sorted(org_counts.items(), key=lambda item: item[1], reverse=True)
    for org, push_count in ranked:
        if push_count < min_pushes:
            break
        prefix_count = await count_push_events_by_org_prefix(app, harvester_id, index_id, org)
        if prefix_count < min_pushes:
            continue
        repo_count = await count_repos_with_push_events_under_org(app, harvester_id, index_id, org)
        if repo_count < 1:
            continue
        return org, prefix_count, repo_count

    msg = f"No GitHub org prefix with at least {min_pushes} PushEvent rows"
    raise AssertionError(msg)


async def count_push_events_by_org_prefix(
    app: FastMCP,
    harvester_id: str,
    index_id: str,
    org_login: str,
) -> int:
    prefix = f"{org_login}/"
    body = await mcp_harvester_search(
        app,
        harvester_id,
        index_id,
        {
            "size": 0,
            "track_total_hits": True,
            "query": {
                "bool": {
                    "must": [
                        {"term": {"type": "PushEvent"}},
                        {"prefix": {"repo.name": prefix}},
                    ]
                }
            },
        },
    )
    total = es_hits_total(body)
    if total is None:
        msg = f"PushEvent org prefix count query returned no hits.total for {prefix!r}"
        raise AssertionError(msg)
    return total


async def count_repos_with_push_events_under_org(
    app: FastMCP,
    harvester_id: str,
    index_id: str,
    org_login: str,
) -> int:
    prefix = f"{org_login}/"
    body = await mcp_harvester_search(
        app,
        harvester_id,
        index_id,
        {
            "size": 0,
            "query": {
                "bool": {
                    "must": [
                        {"term": {"type": "PushEvent"}},
                        {"prefix": {"repo.name": prefix}},
                    ]
                }
            },
            "aggs": {"repos": {"terms": {"field": "repo.name", "size": 500}}},
        },
    )
    return len(_push_event_repo_buckets(body))


async def count_push_events_by_repo_slug(
    app: FastMCP,
    harvester_id: str,
    index_id: str,
    repo_slug: str,
) -> int:
    body = await mcp_harvester_search(
        app,
        harvester_id,
        index_id,
        {
            "size": 0,
            "track_total_hits": True,
            "query": {
                "bool": {
                    "must": [
                        {"term": {"type": "PushEvent"}},
                        {"term": {"repo.name": repo_slug}},
                    ]
                }
            },
        },
    )
    total = es_hits_total(body)
    if total is None:
        msg = "PushEvent repo count query returned no hits.total"
        raise AssertionError(msg)
    return total


async def count_push_events_by_actor_login(
    app: FastMCP,
    harvester_id: str,
    index_id: str,
    actor_login: str,
) -> int:
    body = await mcp_harvester_search(
        app,
        harvester_id,
        index_id,
        {
            "size": 0,
            "track_total_hits": True,
            "query": {
                "bool": {
                    "must": [
                        {"term": {"type": "PushEvent"}},
                        {"term": {"actor.login": actor_login}},
                    ]
                }
            },
        },
    )
    total = es_hits_total(body)
    if total is None:
        msg = "PushEvent actor count query returned no hits.total"
        raise AssertionError(msg)
    return total

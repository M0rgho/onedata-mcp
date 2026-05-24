"""Fixtures and markers for ``test/e2e/github_dataset/`` Forge scenarios."""

from __future__ import annotations

from typing import Any

import pytest
import pytest_asyncio
from github_dataset_harvester import (
    GithubDatasetHarvesterNotFoundError,
    discover_actor_repo_push_chronology_files,
    discover_actor_repo_push_pair,
    discover_concept_slug_mismatch_pair,
    discover_earliest_push_event_file_mtime,
    discover_github_harvester_bundle,
    discover_listed_event_file,
    discover_org_prefix_with_min_pushes,
    discover_top_push_event_actor,
)


@pytest_asyncio.fixture
async def github_harvester_bundle(mcp_application: Any) -> tuple[str, str, str]:
    try:
        return await discover_github_harvester_bundle(mcp_application)
    except GithubDatasetHarvesterNotFoundError as exc:
        pytest.skip(str(exc))


@pytest_asyncio.fixture
async def github_sample_event_basename(mcp_application: Any) -> str:
    basename, _path = await discover_listed_event_file(mcp_application)
    return basename


@pytest_asyncio.fixture
async def github_top_push_actor_oracle(
    mcp_application: Any,
    github_harvester_bundle: tuple[str, str, str],
) -> tuple[str, int]:
    harvester_id, index_id, _space_id = github_harvester_bundle
    login, count = await discover_top_push_event_actor(mcp_application, harvester_id, index_id)
    if count < 1:
        pytest.skip(f"No PushEvent rows for top actor {login!r}")
    return login, count


@pytest_asyncio.fixture
async def github_earliest_push_mtime_oracle(
    mcp_application: Any,
    github_harvester_bundle: tuple[str, str, str],
    github_top_push_actor_oracle: tuple[str, int],
) -> tuple[str, str, str, Any]:
    harvester_id, index_id, _space_id = github_harvester_bundle
    actor_login, _count = github_top_push_actor_oracle
    basename, logical_path, mtime = await discover_earliest_push_event_file_mtime(
        mcp_application, harvester_id, index_id, actor_login
    )
    return actor_login, basename, logical_path, mtime


@pytest_asyncio.fixture
async def github_actor_repo_chronology_oracle(
    mcp_application: Any,
    github_harvester_bundle: tuple[str, str, str],
) -> tuple[str, str, int, str, Any, str, Any]:
    harvester_id, index_id, _space_id = github_harvester_bundle
    try:
        login, repo, count = await discover_actor_repo_push_pair(
            mcp_application, harvester_id, index_id, min_pushes=5
        )
    except AssertionError as exc:
        pytest.skip(str(exc))
    (
        first_base,
        first_mtime,
        fifth_base,
        fifth_mtime,
    ) = await discover_actor_repo_push_chronology_files(
        mcp_application, harvester_id, index_id, login, repo
    )
    return login, repo, count, first_base, first_mtime, fifth_base, fifth_mtime


@pytest_asyncio.fixture
async def github_concept_slug_mismatch_oracle(
    mcp_application: Any,
    github_harvester_bundle: tuple[str, str, str],
) -> tuple[str, str, str, int]:
    harvester_id, index_id, _space_id = github_harvester_bundle
    try:
        return await discover_concept_slug_mismatch_pair(mcp_application, harvester_id, index_id)
    except AssertionError as exc:
        pytest.skip(str(exc))


@pytest_asyncio.fixture
async def github_org_prefix_oracle(
    mcp_application: Any,
    github_harvester_bundle: tuple[str, str, str],
) -> tuple[str, int, int]:
    harvester_id, index_id, _space_id = github_harvester_bundle
    try:
        return await discover_org_prefix_with_min_pushes(
            mcp_application, harvester_id, index_id, min_pushes=100
        )
    except AssertionError as exc:
        pytest.skip(str(exc))

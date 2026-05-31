"""Forge: JSON metadata field on a known event that is stored but not searchable in the index."""

from __future__ import annotations

from typing import Any

import pytest
from assertions_lib import assert_forge_scenario_outcome
from e2e_types import E2EScenario
from github_dataset_harvester import (
    GITHUB_DATASET_DIR,
    GITHUB_DATASET_SPACE,
    mcp_harvester_search,
)
from github_forge_e2e import (
    GITHUB_FORGE_MAX_TOKENS,
    GITHUB_FORGE_PYTESTMARK,
    GITHUB_FORGE_USER_SYSTEM,
    GITHUB_JSON_FIELD_NOT_INDEXED_EXAMPLE,
    assert_successful_harvester_queries,
)
from isolated_helpers import es_hits_total
from legacy_forge import run_shared_forge_scenario
from plgrid_ground_truth import mcp_tool_json_result

pytestmark = GITHUB_FORGE_PYTESTMARK

_EX = GITHUB_JSON_FIELD_NOT_INDEXED_EXAMPLE
_EVENT_PATH = f"{GITHUB_DATASET_DIR}/{_EX['event_basename']}"


def _commit_author_email(json_meta: dict[str, Any]) -> str:
    commits = json_meta.get("payload", {}).get("commits")
    assert isinstance(commits, list) and commits
    author = commits[0].get("author")
    assert isinstance(author, dict)
    email = author.get("email")
    assert isinstance(email, str) and email
    return email


@pytest.mark.e2e_scenario("find-github-author-email-not-indexed")
async def test_find_github_author_email_not_indexed(
    request: Any,
    mcp_application: Any,
    forge_api_key: str,
    forge_model: str,
    forge_base_url: str,
    github_harvester_bundle: tuple[str, str, str],
) -> None:
    harvester_id, index_id, _space_id = github_harvester_bundle
    actor_login = _EX["actor_login"]
    repo_name = _EX["repo_name"]
    commit_message = _EX["commit_message"]
    expected_email = _EX["json_value"]
    expected_creation_epoch = _EX["file_creation_epoch"]

    async def verify(app: Any) -> None:
        attrs = await mcp_tool_json_result(
            app,
            "get_file_attributes",
            {"file_id_or_path": _EVENT_PATH, "attributes": ["creationTime", "path"]},
        )
        assert isinstance(attrs, dict)
        assert attrs.get("creationTime") == expected_creation_epoch

        meta = await mcp_tool_json_result(
            app,
            "get_file_metadata",
            {"file_id_or_path": _EVENT_PATH, "metadata_types": ["json"]},
        )
        assert isinstance(meta, dict)
        json_meta = meta.get("json")
        assert isinstance(json_meta, dict)
        assert json_meta.get("type") == "PushEvent"
        assert _commit_author_email(json_meta) == expected_email
        actor = json_meta.get("actor")
        assert isinstance(actor, dict)
        assert actor.get("login") == actor_login
        repo = json_meta.get("repo")
        assert isinstance(repo, dict)
        assert repo.get("name") == repo_name

        term_email = await mcp_harvester_search(
            app,
            harvester_id,
            index_id,
            {
                "size": 0,
                "track_total_hits": True,
                "query": {"term": {_EX["index_term_field"]: expected_email}},
            },
        )
        assert es_hits_total(term_email) == 0

    scenario = E2EScenario(
        name="find-github-author-email-not-indexed",
        system_prompt=GITHUB_FORGE_USER_SYSTEM,
        user_prompt=(
            f"In {GITHUB_DATASET_SPACE} space find and report the commit author email for the "
            f"push to {repo_name!r} by {actor_login!r} where the commit message is {commit_message!r}"
            "Also report the unformatted file creation timestamp"
        ),
        required_tools=frozenset(
            {"get_file_metadata", "get_file_attributes", "query_harvester_index"}
        ),
        max_tokens=GITHUB_FORGE_MAX_TOKENS,
        max_tool_rounds=12,
    )
    run = await run_shared_forge_scenario(
        scenario=scenario,
        mcp_app=mcp_application,
        forge_api_key=forge_api_key,
        forge_base_url=forge_base_url,
        model=forge_model,
        pytest_request=request,
        verify_state=verify,
    )
    assert_successful_harvester_queries(run)
    assert_forge_scenario_outcome(
        run,
        answer_fragments=(expected_email, str(expected_creation_epoch)),
        answer_hint="Answer should include commit author email and file creationTime epoch seconds.",
    )

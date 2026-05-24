"""Forge E2E for Github Harvester ``github-index`` (Onedata file rows + GH events)."""

from __future__ import annotations

from typing import Any

import pytest
from assertions_lib import assert_forge_scenario_outcome
from e2e_types import E2EScenario, ForgeRunResult
from env_checks import forge_credentials_available, onedata_credentials_available
from forge_harness import run_forge_scenario

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.legacy,
    pytest.mark.e2e,
    pytest.mark.onedata_integration,
    pytest.mark.skipif(
        not forge_credentials_available(),
        reason="PLGRID_FORGE_API_KEY and PLGRID_FORGE_MODEL required",
    ),
    pytest.mark.skipif(
        not onedata_credentials_available(),
        reason="Full Onedata credentials required",
    ),
]

_GITHUB_FORGE_TOOLS = frozenset(
    {
        "list_user_harvesters",
        "get_harvester_index_schema",
        "query_harvester_index",
    }
)

_GITHUB_COMPLEX_MAX_TOKENS = 8192
_GITHUB_COMPLEX_MAX_TOOL_ROUNDS = 24

_ANSWER_TAIL = (
    " After tools succeed: reply in one plain line under 120 characters (no pasted JSON)."
)


def _assert_successful_harvester_queries(run: ForgeRunResult) -> None:
    """Allow failed exploratory calls — require at least one good ``query_harvester_index``."""

    assert any(c.ok for c in run.metrics.tool_calls), "No successful MCP tool calls: " + "; ".join(
        f"{m.tool_name} err={m.error!r}" for m in run.metrics.tool_calls
    )
    es_ok = [m for m in run.metrics.tool_calls if m.tool_name == "query_harvester_index" and m.ok]
    assert es_ok, "Expected at least one successful query_harvester_index: " + "; ".join(
        f"{m.tool_name}(ok={m.ok}, err={m.error!r})" for m in run.metrics.tool_calls
    )


async def test_e2e_github_index_reports_event_type_for_named_event_file(
    request: Any,
    mcp_application: Any,
    forge_api_key: str,
    forge_model: str,
    forge_base_url: str,
) -> None:
    """Model locates Github Harvester github-index and reads ``type`` for a known ``.dat`` row."""
    event_file = "github_event_11898.dat"
    expected_event_type = "PullRequestReviewEvent"

    scenario = E2EScenario(
        name="github-harvester-pr-review-event-type",
        user_prompt=(
            "Using Onedata harvester tools: find the harvester whose name mentions GitHub "
            "and its index usually called github-index for search. Run an index query "
            f"that returns the document backed by Onedata file name "
            f'"{event_file}". '
            "Prefer tightening the Elasticsearch `_search` body so `_source` only "
            "includes fields you need (small payload). "
            "From the hit, report the GitHub **event type** field exactly "
            "as stored (not a guess). Reply in plain text." + _ANSWER_TAIL
        ),
        required_tools=frozenset({"query_harvester_index"}),
        allowed_tools_for_minimal_context=_GITHUB_FORGE_TOOLS,
        max_tokens=_GITHUB_COMPLEX_MAX_TOKENS,
        max_tool_rounds=_GITHUB_COMPLEX_MAX_TOOL_ROUNDS,
    )
    run = await run_forge_scenario(
        scenario=scenario,
        mcp_app=mcp_application,
        tool_context_mode="full",
        forge_api_key=forge_api_key,
        forge_base_url=forge_base_url,
        model=forge_model,
        pytest_request=request,
    )
    _assert_successful_harvester_queries(run)
    assert_forge_scenario_outcome(
        run,
        answer_fragments=(expected_event_type,),
        answer_hint="Answer must cite the PullRequestReview event type from tool output.",
    )


async def test_e2e_github_index_reports_repo_slug_for_named_event_file(
    request: Any,
    mcp_application: Any,
    forge_api_key: str,
    forge_model: str,
    forge_base_url: str,
) -> None:
    """Same document as PR-review test — forces reading ``repo.name`` (owner/repo slug)."""
    event_file = "github_event_11898.dat"
    expected_repo_slug = "Unknown-Studios/react-sitemap-generator"

    scenario = E2EScenario(
        name="github-harvester-pr-review-repo-slug",
        user_prompt=(
            "Use harvester query tools against the Github harvester's github-index. "
            f"Fetch the indexed row tied to Onedata file "
            f'"{event_file}" '
            "and reply with the **repository full name** in owner/repo form as stored "
            "under repo metadata (verbatim from the hit)." + _ANSWER_TAIL
        ),
        required_tools=frozenset({"query_harvester_index"}),
        allowed_tools_for_minimal_context=_GITHUB_FORGE_TOOLS,
        max_tokens=_GITHUB_COMPLEX_MAX_TOKENS,
        max_tool_rounds=_GITHUB_COMPLEX_MAX_TOOL_ROUNDS,
    )
    run = await run_forge_scenario(
        scenario=scenario,
        mcp_app=mcp_application,
        tool_context_mode="full",
        forge_api_key=forge_api_key,
        forge_base_url=forge_base_url,
        model=forge_model,
        pytest_request=request,
    )
    _assert_successful_harvester_queries(run)
    assert_forge_scenario_outcome(
        run,
        answer_fragments=(expected_repo_slug,),
        answer_hint="Answer must contain the slug from the Elasticsearch _source.repo.name field.",
    )


async def test_e2e_github_index_finds_push_event_for_repo_slug(
    request: Any,
    mcp_application: Any,
    forge_api_key: str,
    forge_model: str,
    forge_base_url: str,
) -> None:
    """Different query shape: filter by ``PushEvent`` + ``repo.name`` (not filename oracle)."""
    push_repo_slug = "rafnixg/rafnixg"
    expected_event_type = "PushEvent"

    scenario = E2EScenario(
        name="github-harvester-push-event-by-repo",
        user_prompt=(
            "On the github-index of my Github Harvester, search for indexed GitHub records "
            f"whose event kind is PushEvent on repository `{push_repo_slug}`. "
            "Briefly confirm what you matched: mention both **PushEvent** and that repo slug "
            "exactly once in your answer, quoting tool output semantics." + _ANSWER_TAIL
        ),
        required_tools=frozenset({"query_harvester_index", "list_user_harvesters"}),
        allowed_tools_for_minimal_context=_GITHUB_FORGE_TOOLS,
        max_tokens=_GITHUB_COMPLEX_MAX_TOKENS,
        max_tool_rounds=_GITHUB_COMPLEX_MAX_TOOL_ROUNDS,
    )
    run = await run_forge_scenario(
        scenario=scenario,
        mcp_app=mcp_application,
        tool_context_mode="full",
        forge_api_key=forge_api_key,
        forge_base_url=forge_base_url,
        model=forge_model,
        pytest_request=request,
    )
    _assert_successful_harvester_queries(run)
    assert_forge_scenario_outcome(
        run,
        answer_fragments=(expected_event_type, push_repo_slug),
        answer_hint="Must reflect a PushEvent hit for rafnixg/rafnixg from elasticsearch results.",
    )

from __future__ import annotations

from collections.abc import Iterable
from typing import TYPE_CHECKING

from e2e_types import ForgeRunResult, ToolCallMetric

if TYPE_CHECKING:
    from e2e_isolated_space import IsolatedE2ESpace

from shared_tenant import SHARED_TENANT_SPACE_NAMES as _SHARED_TENANT_SPACE_NAMES

_PATH_ARGUMENT_KEYS = (
    "path",
    "parent_id_or_path",
    "file_id_or_path",
    "space_id_or_name",
)


def recall_for_names_in_text(names: frozenset[str], answer: str | None) -> float:
    if not names:
        return 1.0
    if not answer:
        return 0.0
    lowered = answer.lower()
    found = sum(1 for n in names if n.lower() in lowered)
    return found / len(names)


def assert_forbidden_tools(result: ForgeRunResult) -> None:
    forbidden = result.scenario.forbidden_tools
    if not forbidden:
        return
    called = result.metrics.forbidden_tools_called
    assert not called, (
        f"Forbidden tools were called: {sorted(called)} (forbidden={sorted(forbidden)})"
    )


def summarize_failed_tool_calls(
    result: ForgeRunResult | None = None,
    *,
    tool_calls: Iterable[ToolCallMetric] | None = None,
) -> list[dict[str, str | None]]:
    """Failed MCP invocations (for traces and assertion messages; does not fail the test)."""

    calls = (
        list(tool_calls)
        if tool_calls is not None
        else (result.metrics.tool_calls if result is not None else [])
    )
    return [{"tool_name": call.tool_name, "error": call.error} for call in calls if not call.ok]


def _assert_required_tools_successfully_used(result: ForgeRunResult) -> None:
    """Each required tool must succeed at least once (retries after validation errors are ok)."""

    required = result.scenario.required_tools
    if not required:
        return
    successful = result.metrics.successful_tools_called
    missing = required - successful
    assert not missing, (
        f"Required tools never succeeded: {sorted(missing)} "
        f"(successful={sorted(successful)}; failed_calls={summarize_failed_tool_calls(result)})"
    )
    if result.scenario.require_no_extra_tool_calls:
        permitted = required | result.scenario.optional_tools
        extras = successful - permitted
        assert not extras, (
            f"Unexpected successful tools {sorted(extras)} (scenario forbids extras); "
            f"failed_calls={summarize_failed_tool_calls(result)}"
        )


def assert_isolated_forge_trace(result: ForgeRunResult) -> None:
    """Trace checks for isolated Forge: final reply + policy; failed calls are counted only."""

    assert (result.final_assistant_text or "").strip(), (
        "Expected a non-empty final assistant message"
    )
    assert_forbidden_tools(result)
    _assert_required_tools_successfully_used(result)


def assert_tool_arguments_stay_in_isolated_space(
    result: ForgeRunResult,
    space: IsolatedE2ESpace,
) -> None:
    """Tool path arguments must target the isolated space, not shared tenants."""

    allowed_prefixes = (
        space.root_path,
        space.root_path.lstrip("/"),
        f"/{space.space_id}",
        space.space_id,
        space.space_name,
    )

    for call in result.metrics.tool_calls:
        args = call.arguments
        if not isinstance(args, dict):
            continue
        for key in _PATH_ARGUMENT_KEYS:
            value = args.get(key)
            if not isinstance(value, str) or not value.strip():
                continue
            if value in _SHARED_TENANT_SPACE_NAMES:
                msg = (
                    f"{call.tool_name} argument {key!r} references shared tenant space "
                    f"{value!r}; isolated tests must use {space.space_name!r} only"
                )
                raise AssertionError(msg)
            if value.startswith("/"):
                first_segment = value.strip("/").split("/", 1)[0]
                if first_segment in _SHARED_TENANT_SPACE_NAMES:
                    msg = (
                        f"{call.tool_name} argument {key!r} references shared tenant space "
                        f"/{first_segment!r}; isolated tests must use {space.space_name!r} only"
                    )
                    raise AssertionError(msg)
            if key == "space_id_or_name":
                if value not in (space.space_id, space.space_name):
                    msg = (
                        f"{call.tool_name} space_id_or_name={value!r} does not match "
                        f"isolated space {space.space_id!r} / {space.space_name!r}"
                    )
                    raise AssertionError(msg)
                continue
            if value.startswith("/") and not any(
                value == prefix or value.startswith(f"{prefix}/") for prefix in allowed_prefixes
            ):
                msg = (
                    f"{call.tool_name} argument {key!r}={value!r} is outside isolated "
                    f"space root {space.root_path!r}"
                )
                raise AssertionError(msg)


def _text_contains_fragment(haystack: str, fragment: str) -> bool:
    if fragment.lower() in haystack.lower():
        return True
    digits = "".join(ch for ch in fragment if ch.isdigit())
    if digits:
        normalized = "".join(ch for ch in haystack if ch.isdigit())
        return digits in normalized
    return False


def _answer_contains_all_fragments(result: ForgeRunResult, fragments: Iterable[str]) -> bool:
    text = result.final_assistant_text or ""
    if not text.strip():
        return False
    return all(_text_contains_fragment(text, fragment) for fragment in fragments)


def assert_final_answer_contains_all(
    result: ForgeRunResult,
    fragments: Iterable[str],
    *,
    hint: str = "",
) -> None:
    """Each fragment must appear in the assistant's final reply (case-insensitive)."""

    text = result.final_assistant_text or ""
    assert text.strip(), "Expected a non-empty final assistant message"
    missing = [f for f in fragments if not _text_contains_fragment(text, f)]
    note = f" {hint}" if hint else ""
    assert not missing, f"Final answer missing {missing!s}.{note} Reply excerpt: {text[:900]!r}"


def _assert_any_of_tool_groups(
    result: ForgeRunResult,
    any_of: tuple[frozenset[str], ...],
) -> None:
    called = result.metrics.unique_tools_called
    for index, group in enumerate(any_of, start=1):
        if not (called & group):
            msg = (
                f"Expected at least one of {sorted(group)} (group {index}); called {sorted(called)}"
            )
            raise AssertionError(msg)
    if result.scenario.require_no_extra_tool_calls:
        assert not result.metrics.unnecessary_tools_called, (
            f"Unexpected extras {sorted(result.metrics.unnecessary_tools_called)} "
            "(scenario forbids them)"
        )


def assert_required_tools_and_optional_policy(
    result: ForgeRunResult,
    *,
    any_of: tuple[frozenset[str], ...] = (),
    relax_required_if_answer_contains: Iterable[str] | None = None,
) -> None:
    """Enforce ``required_tools`` unless the final answer already matches all fragments.

    When ``relax_required_if_answer_contains`` is set and every fragment appears in
    ``final_assistant_text``, missing ``required_tools`` does not fail the run (e.g.
    ``download_file`` instead of ``grep_file_content`` on a README task). ``any_of``
    groups and ``require_no_extra_tool_calls`` still apply.
    """

    if relax_required_if_answer_contains and _answer_contains_all_fragments(
        result, relax_required_if_answer_contains
    ):
        _assert_any_of_tool_groups(result, any_of)
        return

    assert result.metrics.required_tools_satisfied, (
        f"Missing tools {sorted(result.metrics.missing_required_tools)} "
        f"— called {sorted(result.metrics.unique_tools_called)}"
    )
    _assert_any_of_tool_groups(result, any_of)


def assert_forge_scenario_outcome(
    result: ForgeRunResult,
    *,
    answer_fragments: Iterable[str] = (),
    answer_hint: str = "",
    any_of: tuple[frozenset[str], ...] = (),
) -> None:
    """Post-run checks: optional answer fragments, then tool policy (with relax)."""

    if answer_fragments:
        assert_final_answer_contains_all(result, answer_fragments, hint=answer_hint)
    assert_required_tools_and_optional_policy(
        result,
        any_of=any_of,
        relax_required_if_answer_contains=answer_fragments or None,
    )

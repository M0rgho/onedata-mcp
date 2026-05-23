from __future__ import annotations

from collections.abc import Iterable
from typing import TYPE_CHECKING, Any

from e2e_types import ForgeRunResult

if TYPE_CHECKING:
    from e2e_isolated_space import IsolatedE2ESpace

_SHARED_TENANT_SPACE_NAMES = frozenset({"krk-p", "krk-iu", "europeana", "openfoodfacts-images"})
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


def assert_isolated_forge_trace(result: ForgeRunResult) -> None:
    """Standard trace-layer checks for isolated Forge scenarios."""

    assert_required_tools_and_optional_policy(result)
    assert_forbidden_tools(result)
    assert result.metrics.all_tool_calls_ok, (
        f"MCP tool errors: "
        f"{[(c.tool_name, c.error) for c in result.metrics.tool_calls if not c.ok]}"
    )


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
            if value.startswith("/"):
                if not any(
                    value == prefix or value.startswith(f"{prefix}/") for prefix in allowed_prefixes
                ):
                    msg = (
                        f"{call.tool_name} argument {key!r}={value!r} is outside isolated "
                        f"space root {space.root_path!r}"
                    )
                    raise AssertionError(msg)


def assert_required_tools_and_optional_policy(result: ForgeRunResult) -> None:
    assert result.metrics.required_tools_satisfied, (
        f"Missing tools {sorted(result.metrics.missing_required_tools)} "
        f"— called {sorted(result.metrics.unique_tools_called)}"
    )
    if result.scenario.require_no_extra_tool_calls:
        assert not result.metrics.unnecessary_tools_called, (
            f"Unexpected extras {sorted(result.metrics.unnecessary_tools_called)} "
            "(scenario forbids them)"
        )


def assert_final_answer_contains_all(
    result: ForgeRunResult,
    fragments: Iterable[str],
    *,
    hint: str = "",
) -> None:
    """Each fragment must appear in the assistant's final reply (case-insensitive)."""

    text = result.final_assistant_text or ""
    assert text.strip(), "Expected a non-empty final assistant message"
    haystack = text.lower()
    missing = [f for f in fragments if f.lower() not in haystack]
    note = f" {hint}" if hint else ""
    assert not missing, f"Final answer missing {missing!s}.{note} Reply excerpt: {text[:900]!r}"

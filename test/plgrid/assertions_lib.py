from __future__ import annotations

from collections.abc import Iterable

from e2e_types import ForgeRunResult


def recall_for_names_in_text(names: frozenset[str], answer: str | None) -> float:
    if not names:
        return 1.0
    if not answer:
        return 0.0
    lowered = answer.lower()
    found = sum(1 for n in names if n.lower() in lowered)
    return found / len(names)


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

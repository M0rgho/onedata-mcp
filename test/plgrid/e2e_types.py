from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

ToolContextMode = Literal["minimal", "full"]
ToolDispatchMode = Literal["mcp"]


@dataclass(frozen=True)
class E2EScenario:
    """Describes one LLM + tools run against Forge and optional MCP dispatch."""

    name: str
    user_prompt: str
    required_tools: frozenset[str]
    allowed_tools_for_minimal_context: frozenset[str]
    model: str | None = None
    system_prompt: str | None = None
    temperature: float = 0.0
    max_tokens: int = 2048
    max_tool_rounds: int = 8
    require_no_extra_tool_calls: bool = False

    def __post_init__(self) -> None:
        if not self.required_tools.issubset(self.allowed_tools_for_minimal_context):
            raise ValueError("required_tools must be a subset of allowed_tools_for_minimal_context")


@dataclass
class ToolCallMetric:
    tool_name: str
    duration_ms: float
    ok: bool
    error: str | None = None


@dataclass
class RunMetrics:
    tools_in_context_count: int
    tool_call_count: int
    tool_calls: list[ToolCallMetric] = field(default_factory=list)
    unique_tools_called: frozenset[str] = frozenset()
    required_tools_satisfied: bool = False
    missing_required_tools: frozenset[str] = frozenset()
    unnecessary_tools_called: frozenset[str] = frozenset()
    forge_loop_wall_time_ms: float = 0.0
    mcp_tools_context_stats: dict[str, Any] = field(default_factory=dict)
    chat_context_peak_stats: dict[str, Any] = field(default_factory=dict)
    forge_token_usage_totals: dict[str, int] = field(default_factory=dict)
    forge_token_usage_rounds: list[dict[str, Any]] = field(default_factory=list)
    estimated_prompt_footprint_utf8_peak_bytes: int = 0

    def recompute_tool_sets(self, required: frozenset[str]) -> None:
        names = [c.tool_name for c in self.tool_calls]
        self.tool_call_count = len(names)
        self.unique_tools_called = frozenset(names)
        self.missing_required_tools = required - self.unique_tools_called
        self.required_tools_satisfied = self.missing_required_tools == frozenset()
        self.unnecessary_tools_called = self.unique_tools_called - required

    @property
    def all_tool_calls_ok(self) -> bool:
        return all(call.ok for call in self.tool_calls)

    def tool_calls_echo_counts(self) -> dict[str, int]:
        """Totals for forge trace ``metrics_echo`` (MCP dispatch, one row per invocation)."""

        calls = self.tool_calls
        return {
            "tool_calls_total": len(calls),
            "tool_calls_successful": sum(1 for c in calls if c.ok),
        }


@dataclass
class ForgeRunResult:
    scenario: E2EScenario
    tool_context_mode: ToolContextMode
    dispatch_mode: ToolDispatchMode
    metrics: RunMetrics
    final_assistant_text: str | None
    finish_reason: str | None
    raw_tool_names_in_order: list[str]
    trace_path_written: Path | None = None

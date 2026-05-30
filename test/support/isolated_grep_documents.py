"""Seed content for isolated Forge ``grep-multi-file`` (documents folder)."""

from __future__ import annotations

DOCUMENTS_DIR_NAME = "documents"

GREP_MULTI_FILE_NEEDLE = "E2E_FORGE_GREP_MARKER"

GREP_TARGET_BASENAME = "future_plans.txt"
GREP_DECOY_BASENAME = "notes.txt"

GREP_DOCUMENT_BASENAMES: tuple[str, ...] = (
    "notes.txt",
    "future_plans.txt",
    "meeting_log.txt",
    "budget_draft.txt",
    "reading_list.txt",
)

NOTES_TXT = """\
Personal notes — workspace sync
Reminder: back up the harvester index export.
Contact: lab admin about quota bump.
Todo: review MCP tool descriptions for clarity.
Snippet: prefer grep over full download for logs.
Archive old experiment runs after thesis chapter 3.
Link: internal wiki /runbooks/onedata-e2e
Coffee break 14:30 — resume at desk B12
Tag: literature survey #storage #agents
End of notes block.
"""

FUTURE_PLANS_TXT = f"""\
Roadmap — next quarter
Goal: finish isolated-space Forge evaluation suite.
Stretch: add pass-rate dashboards from trace CSV.
Tracking id: {GREP_MULTI_FILE_NEEDLE}
Milestone: document five realistic grep fixtures.
Risk: model may list_files instead of grep — forbid in test.
Dependency: PLGrid Forge credentials in CI secrets.
Review with supervisor after green integration run.
Deliverable: thesis results section tables.
Parking lot: shared-tenant harvester scenarios unchanged.
"""

MEETING_LOG_TXT = """\
Meeting log — biweekly sync
Attendees: Nick, supervisor, platform engineer
Topic: Onedata MCP read-only caveats on shared spaces
Action: widen documents folder fixtures for grep E2E
Decision: keep admin token separate from confined macaroon
Note: list_files acceptable for list-children scenario only
Follow-up: refresh token cache after confine policy change
Minutes filed under /documents/meeting_log.txt
Next meeting: verify Forge traces on krk-p subset
End of log.
"""

BUDGET_DRAFT_TXT = """\
Budget draft — compute allocation
Line item: PLGrid Forge API credits for model matrix
Line item: storage support registration on dev provider
Line item: student time — test harness maintenance
Assumption: 5 models × 11 isolated scenarios
Contingency: rerun flaky Forge traces once
Exclude: legacy shared-tenant suites from default CI
Approval pending — numbers are estimates only
Revision 2 — adjust after first full isolated sweep
End of budget draft.
"""

READING_LIST_TXT = """\
Reading list — MCP and data agents
Paper: Model Context Protocol specification
Paper: tool-use evaluation methodologies
Blog: harvester indexes vs raw file metadata
Book chapter: distributed storage systems (draft)
Survey: LLM agents on scientific data platforms
Note: compare minimal vs full tool context ablations
Bookmark: Onedata REST attribute reference
To skim: pytest fixtures for isolated spaces
End of reading list.
"""


def grep_multi_file_documents() -> tuple[tuple[str, str], ...]:
    """Return ``(basename, body)`` pairs to seed under ``documents/``."""

    return (
        ("notes.txt", NOTES_TXT),
        (GREP_TARGET_BASENAME, FUTURE_PLANS_TXT),
        ("meeting_log.txt", MEETING_LOG_TXT),
        ("budget_draft.txt", BUDGET_DRAFT_TXT),
        ("reading_list.txt", READING_LIST_TXT),
    )


def grep_document_filenames_prompt() -> str:
    return ", ".join(GREP_DOCUMENT_BASENAMES)

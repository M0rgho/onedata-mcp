from __future__ import annotations

import json
from typing import Any

from fastmcp.tools.base import ToolResult


def tool_result_to_text(result: ToolResult) -> str:
    if result.structured_content is not None:
        payload = result.structured_content.get("result", result.structured_content)
        return json.dumps(payload, default=str, ensure_ascii=False)
    texts: list[str] = []
    for block in result.content:
        txt = getattr(block, "text", None)
        if isinstance(txt, str):
            texts.append(txt)
    return "\n".join(texts) if texts else "null"


def json_dumps(obj: Any) -> str:
    return json.dumps(obj, default=str, ensure_ascii=False)

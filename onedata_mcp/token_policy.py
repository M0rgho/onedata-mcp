"""Startup policy: omit write tools when the Oneprovider token is read-only."""

from __future__ import annotations

import asyncio
import logging
import os
from collections.abc import Coroutine
from concurrent.futures import ThreadPoolExecutor
from typing import TypeVar

from onedata_mcp.api.tokens import examine_access_token, token_has_data_readonly_caveat
from onedata_mcp.utils import OnedataApiError, is_valid_url

logger = logging.getLogger(__name__)

_T = TypeVar("_T")


def run_startup_coroutine(coro: Coroutine[None, None, _T]) -> _T:
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)

    with ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(asyncio.run, coro).result()


WRITE_TOOL_NAMES = frozenset(
    {
        "create_file",
        "delete_file",
        "set_file_xattrs",
        "set_file_metadata",
    }
)


def onezone_configured_for_token_check() -> bool:
    """True when Onezone host and user token are set (gate for provider token examine)."""

    host = os.getenv("ONEDATA_ONEZONE_HOST")
    token = os.getenv("ONEDATA_ONEZONE_TOKEN")
    return bool(host and is_valid_url(host) and token and token.strip())


async def resolve_register_write_tools() -> bool:
    """
    Whether to register mutating file tools on the MCP server.

    Returns ``True`` (register writers) when the check is skipped or the token is not
    read-only. Returns ``False`` when ``data.readonly`` is present on the Oneprovider token.
    """

    if not onezone_configured_for_token_check():
        return True

    provider_token = os.getenv("ONEDATA_ONEPROVIDER_TOKEN")
    if not provider_token or not provider_token.strip():
        logger.warning(
            "Onezone credentials set but ONEDATA_ONEPROVIDER_TOKEN is missing; "
            "cannot examine provider token — registering all file tools"
        )
        return True

    try:
        examined = await examine_access_token(provider_token.strip())
    except (OnedataApiError, TypeError) as exc:
        logger.warning(
            "Could not examine Oneprovider token via Onezone (%s); registering all file tools",
            exc,
        )
        return True

    if token_has_data_readonly_caveat(examined):
        logger.info(
            "Oneprovider token has data.readonly caveat; omitting write tools: %s",
            ", ".join(sorted(WRITE_TOOL_NAMES)),
        )
        return False

    return True


def resolve_register_write_tools_sync() -> bool:
    """Sync entry point for server construction (see ``run_startup_coroutine``)."""

    return run_startup_coroutine(resolve_register_write_tools())

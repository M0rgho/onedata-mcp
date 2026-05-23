"""Shared environment guards for Forge / Onedata E2E tests.

Optional Forge trace logging:
- PLGRID_E2E_TRACE_FILE — append JSON trace blob per scenario run (OpenAI-compat full context).
- PLGRID_E2E_TRACE_DIR — write forge_trace_<name>_<time>_<pid>.json under
  ``<dir>/<UTC-YYYY-MM-DD_HH-MM-SS>/`` (subdir name stamped on first trace write for that base;
  defaults ``logs`` relative to cwd). Trace JSON includes ``test_result`` (null until the test
  body finishes, then ``success`` or ``failure`` by the pytest hook), ``pytest_nodeid``, and after
  the session ends one ``forge_traces_summary__*.csv`` per pytest test directory in that same run
  folder (metrics + pass/fail + absolute path to each trace JSON).
"""

from __future__ import annotations

import os

KRK_SPACES = frozenset({"krk-iu", "krk-p"})


def _valid_url(url: str | None) -> bool:
    if not url:
        return False
    return url.startswith("http://") or url.startswith("https://")


def forge_credentials_available() -> bool:
    key = os.getenv("PLGRID_FORGE_API_KEY", "").strip()
    model = os.getenv("PLGRID_FORGE_MODEL", "").strip()
    return bool(key and model)


def onedata_admin_token_available() -> bool:
    return bool(os.getenv("ONEDATA_E2E_ADMIN_TOKEN", "").strip()) or bool(
        os.getenv("ONEDATA_ONEPROVIDER_TOKEN", "").strip()
    )


def onedata_credentials_available() -> bool:
    return (
        _valid_url(os.getenv("ONEDATA_ONEZONE_HOST"))
        and bool(os.getenv("ONEDATA_ONEZONE_TOKEN", "").strip())
        and _valid_url(os.getenv("ONEDATA_ONEPROVIDER_HOST"))
        and onedata_admin_token_available()
    )

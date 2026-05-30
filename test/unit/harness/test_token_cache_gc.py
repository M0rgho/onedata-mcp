"""Unit tests for confined-token cache garbage collection."""

from __future__ import annotations

import json
import time

import pytest
from e2e_isolated_space import (
    _is_e2e_named_token_name,
    _parse_cache_key,
    prune_token_cache,
)


def test_is_e2e_named_token_name_prefix() -> None:
    assert _is_e2e_named_token_name("mcp-e2e-base-859a3016-ab12cd")
    assert _is_e2e_named_token_name("mcp-e2e-support-859a3016-ef34gh")
    assert not _is_e2e_named_token_name("my-production-token")


def test_parse_cache_key_splits_host_with_scheme() -> None:
    key = "https://provider.example:space-id-abc:rw"
    assert _parse_cache_key(key) == ("https://provider.example", "space-id-abc", "rw")


def test_prune_drops_expired_entries(tmp_path, monkeypatch) -> None:
    cache_dir = tmp_path / ".e2e-token-cache"
    cache_dir.mkdir()
    cache_file = cache_dir / "tokens.json"
    now = int(time.time())
    payload = {
        "https://p.example:expired-space:rw": {
            "token": "t1",
            "validUntil": now - 3600,
            "spaceId": "expired-space",
            "readonly": False,
        },
        "https://p.example:live-space:rw": {
            "token": "t2",
            "validUntil": now + 3600,
            "spaceId": "live-space",
            "readonly": False,
        },
    }
    cache_file.write_text(json.dumps(payload), encoding="utf-8")
    monkeypatch.setattr("e2e_isolated_space._CACHE_DIR", cache_dir)
    monkeypatch.setattr("e2e_isolated_space._CACHE_FILE", cache_file)

    removed = prune_token_cache(drop_expired=True, now=now)
    assert removed == 1
    remaining = json.loads(cache_file.read_text(encoding="utf-8"))
    assert list(remaining) == ["https://p.example:live-space:rw"]


def test_prune_drops_deleted_space_ids(tmp_path, monkeypatch) -> None:
    cache_dir = tmp_path / ".e2e-token-cache"
    cache_dir.mkdir()
    cache_file = cache_dir / "tokens.json"
    now = int(time.time()) + 10_000
    payload = {
        "https://p.example:gone:rw": {
            "token": "t1",
            "validUntil": now,
            "spaceId": "gone",
            "readonly": False,
        },
        "https://p.example:gone:ro": {
            "token": "t2",
            "validUntil": now,
            "spaceId": "gone",
            "readonly": True,
        },
        "https://p.example:stay:rw": {
            "token": "t3",
            "validUntil": now,
            "spaceId": "stay",
            "readonly": False,
        },
    }
    cache_file.write_text(json.dumps(payload), encoding="utf-8")
    monkeypatch.setattr("e2e_isolated_space._CACHE_DIR", cache_dir)
    monkeypatch.setattr("e2e_isolated_space._CACHE_FILE", cache_file)

    removed = prune_token_cache(space_ids={"gone"}, drop_expired=False, now=now)
    assert removed == 2
    remaining = json.loads(cache_file.read_text(encoding="utf-8"))
    assert list(remaining) == ["https://p.example:stay:rw"]


def test_prune_deletes_file_when_empty(tmp_path, monkeypatch) -> None:
    cache_dir = tmp_path / ".e2e-token-cache"
    cache_dir.mkdir()
    cache_file = cache_dir / "tokens.json"
    now = int(time.time())
    cache_file.write_text(
        json.dumps(
            {
                "bad-key": {},
                "https://p.example:old:rw": {
                    "token": "t",
                    "validUntil": now - 1,
                    "spaceId": "old",
                    "readonly": False,
                },
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr("e2e_isolated_space._CACHE_DIR", cache_dir)
    monkeypatch.setattr("e2e_isolated_space._CACHE_FILE", cache_file)

    removed = prune_token_cache(drop_expired=True, now=now)
    assert removed == 2
    assert not cache_file.is_file()


def test_prune_respects_disable_flag(monkeypatch) -> None:
    monkeypatch.setenv("ONEDATA_E2E_TOKEN_CACHE_DISABLE_GC", "1")
    assert prune_token_cache(drop_expired=True) == 0


@pytest.mark.parametrize("key", ["", "nocolons", "only:one"])
def test_parse_cache_key_rejects_invalid(key: str) -> None:
    assert _parse_cache_key(key) is None

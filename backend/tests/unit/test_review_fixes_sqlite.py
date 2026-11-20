"""Codex 2차 검증 결함 3: 다중 프로세스 SQLite 캐시 갱신 (외부 API 없음, 실제 프로세스 2개)."""
from __future__ import annotations

import multiprocessing as mp
import time
from pathlib import Path

from tests.unit import sqlite_worker as w

CTX = mp.get_context("spawn")


def _builds(d: Path) -> list[str]:
    p = d / "builds.log"
    return p.read_text().split() if p.exists() else []


def test_two_processes_build_once_and_both_succeed(tmp_path):
    with CTX.Pool(2) as pool:
        results = pool.starmap(w.build, [(str(tmp_path), "A", 0.8, w.later(0)), (str(tmp_path), "B", 0.8, w.later(0))])
    assert results == ["ok", "ok"]
    assert len(_builds(tmp_path)) == 1  # 잠금 후 TTL 재확인으로 두 번째 프로세스는 수집하지 않음
    assert not list(tmp_path.glob("*.tmp"))
    assert len(w.store(str(tmp_path), w.T0).by_key("k")) == 1


def test_old_file_readable_during_rebuild_and_kept_on_failure(tmp_path):
    assert w.build(str(tmp_path), "old", 0, w.later(0)) == "ok"
    expired = w.later(48)  # TTL 24시간 지남
    # 다른 프로세스가 느리게 다시 만드는 동안 기존 데이터를 읽을 수 있다
    proc = CTX.Process(target=w.build, args=(str(tmp_path), "new", 1.5, expired))
    proc.start()
    time.sleep(0.8)
    assert w.store(str(tmp_path), w.T0).by_key("k")[0]["v"] == "old"
    proc.join(10)
    assert w.store(str(tmp_path), w.T0).by_key("k")[0]["v"] == "new"
    # 빌드가 실패하면 기존 파일을 그대로 두고 임시 파일을 남기지 않는다
    assert w.build(str(tmp_path), "broken", 0, w.later(100), fail=True) == "failed"
    assert w.store(str(tmp_path), w.T0).by_key("k")[0]["v"] == "new"
    assert not list(tmp_path.glob("*.tmp"))

"""SQLite 저장소 다중 프로세스 테스트용 작업 함수 (spawn 으로 실행되므로 모듈 최상위에 둔다)."""
from __future__ import annotations

import time
from datetime import datetime, timedelta
from pathlib import Path

from app.datasets.cache import KST, JsonCache
from app.datasets.sqlite_store import SqliteRows

T0 = datetime(2026, 11, 20, 12, 0, tzinfo=KST)


def store(directory: str, now: datetime) -> SqliteRows:
    return SqliteRows(JsonCache(Path(directory), ttl_hours=24, clock=lambda: now), "demo")


def build(directory: str, label: str, delay: float, now_iso: str, fail: bool = False) -> str:
    """느린 빌더로 ensure(). 실제로 수집했으면 counter 파일에 한 줄 남긴다."""
    def builder():
        with open(Path(directory) / "builds.log", "a") as f:
            f.write(label + "\n")

        def rows():
            time.sleep(delay)
            if fail:
                raise RuntimeError("외부 API 실패 흉내")
            yield "k", 37.5, 127.0, {"v": label}

        return rows(), lambda: {"label": label}

    try:
        store(directory, datetime.fromisoformat(now_iso)).ensure(builder)
        return "ok"
    except RuntimeError:
        return "failed"


def later(hours: float) -> str:
    return (T0 + timedelta(hours=hours)).isoformat()

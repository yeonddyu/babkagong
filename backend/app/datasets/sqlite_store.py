"""서울 전역 외부 데이터를 담는 SQLite 저장소 (JSON 캐시로는 너무 큰 데이터용).

- 데이터셋마다 파일 하나: {cache_dir}/{name}.sqlite
- 표 rows(key, lat, lng, data): key 는 출처 ID(같은 key 의 여러 행 허용 — 메뉴처럼), data 는 원본/정규화 JSON
- 다시 만들 때는 프로세스별 임시 파일에 쓴 뒤 원자적으로 교체한다 (만드는 중에도 기존 파일로 응답 가능, 실패해도 기존 파일 유지)
- 갱신은 프로세스 간 파일 잠금({name}.sqlite.lock, fcntl)과 스레드 잠금으로 한 번에 하나만. 잠금을 얻은 뒤 TTL 을 다시 확인해
  다른 프로세스가 방금 만든 데이터가 있으면 다시 수집하지 않는다. 읽기는 잠금 없이 한다.
- 신선도는 JsonCache 와 같은 TTL·시계를 쓴다 (meta 표의 fetched_at)
"""
from __future__ import annotations

import json
import math
import os
import sqlite3
import threading
import uuid
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Iterable, Iterator

from app.core.geo import haversine_m
from app.datasets.cache import JsonCache

Row = tuple[str, float | None, float | None, dict[str, Any]]

_build_locks: dict[str, threading.Lock] = {}
_locks_guard = threading.Lock()


def _lock_for(path: Path) -> threading.Lock:
    with _locks_guard:
        return _build_locks.setdefault(str(path), threading.Lock())


@contextmanager
def _process_lock(path: Path):
    """프로세스 간 배타 잠금 (POSIX fcntl). 잠금 파일은 지우지 않는다 (지우면 다른 프로세스와 다른 inode 를 잠글 수 있음)."""
    import fcntl

    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a+") as fh:
        fcntl.flock(fh.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(fh.fileno(), fcntl.LOCK_UN)


class SqliteRows:
    def __init__(self, cache: JsonCache, name: str):
        self.path = Path(cache.directory) / f"{name}.sqlite"
        self.ttl = cache.ttl
        self._clock: Callable[[], datetime] = cache._clock  # noqa: SLF001 - 같은 시계 사용

    # ------------------------------------------------------------ 연결
    def _connect(self, path: Path | None = None) -> sqlite3.Connection:
        con = sqlite3.connect(str(path or self.path), timeout=30)
        con.row_factory = sqlite3.Row
        return con

    def meta(self) -> dict[str, Any] | None:
        """신선한 데이터가 있으면 meta, 없거나 만료면 None."""
        if not self.path.exists():
            return None
        try:
            with self._connect() as con:
                row = con.execute("SELECT fetched_at, info FROM meta LIMIT 1").fetchone()
        except sqlite3.Error:
            return None
        if row is None:
            return None
        try:
            fetched_at = datetime.fromisoformat(row["fetched_at"])
        except ValueError:
            return None
        if self._clock() - fetched_at > self.ttl:
            return None
        return {"fetched_at": row["fetched_at"], **json.loads(row["info"] or "{}")}

    def ensure(self, builder: Callable[[], tuple[Iterable[Row], Callable[[], dict[str, Any]]]]) -> dict[str, Any]:
        """신선하지 않으면 builder 로 다시 만든다. builder 는 (행 iterator, 다 읽은 뒤 meta 를 돌려줄 함수)."""
        meta = self.meta()
        if meta is not None:
            return meta
        with _lock_for(self.path), _process_lock(self.path.with_suffix(".sqlite.lock")):
            meta = self.meta()  # 잠금을 기다리는 동안 다른 스레드·프로세스가 만들었을 수 있음
            if meta is not None:
                return meta
            rows, finish = builder()
            self._write(rows, finish)
        return self.meta() or {}

    def _write(self, rows: Iterable[Row], finish: Callable[[], dict[str, Any]]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_name(f"{self.path.name}.{os.getpid()}.{uuid.uuid4().hex[:8]}.tmp")  # 프로세스마다 다른 임시 파일
        con = self._connect(tmp)
        try:
            con.execute("CREATE TABLE rows (key TEXT NOT NULL, lat REAL, lng REAL, data TEXT NOT NULL)")
            con.execute("CREATE TABLE meta (fetched_at TEXT NOT NULL, info TEXT)")
            batch: list[tuple[str, float | None, float | None, str]] = []
            for key, lat, lng, data in rows:
                batch.append((key, lat, lng, json.dumps(data, ensure_ascii=False)))
                if len(batch) >= 5000:
                    con.executemany("INSERT INTO rows VALUES (?, ?, ?, ?)", batch)
                    batch.clear()
            if batch:
                con.executemany("INSERT INTO rows VALUES (?, ?, ?, ?)", batch)
            con.execute("CREATE INDEX idx_key ON rows(key)")
            con.execute("CREATE INDEX idx_lat_lng ON rows(lat, lng)")
            con.execute("INSERT INTO meta VALUES (?, ?)",
                        (self._clock().isoformat(), json.dumps(finish(), ensure_ascii=False, default=str)))
            con.commit()
        except BaseException:
            con.close()
            tmp.unlink(missing_ok=True)
            raise
        con.close()
        os.replace(tmp, self.path)

    # ------------------------------------------------------------ 조회
    def by_key(self, key: str) -> list[dict[str, Any]]:
        with self._connect() as con:
            return [json.loads(r["data"]) for r in con.execute("SELECT data FROM rows WHERE key = ? ORDER BY rowid", (key,))]

    def keys_present(self, keys: Iterable[str]) -> set[str]:
        keys = list(dict.fromkeys(keys))
        found: set[str] = set()
        with self._connect() as con:
            for i in range(0, len(keys), 900):  # SQLite 변수 개수 한도 안에서 나눠 조회
                chunk = keys[i: i + 900]
                q = f"SELECT DISTINCT key FROM rows WHERE key IN ({','.join('?' * len(chunk))})"
                found.update(r["key"] for r in con.execute(q, chunk))
        return found

    def near(self, lat: float, lng: float, radius_m: float) -> Iterator[tuple[float, dict[str, Any]]]:
        """좌표 반경 안의 (직선거리, data). 위경도 사각형으로 먼저 거른 뒤 정확한 거리로 확인한다."""
        dlat = radius_m / 111_320
        dlng = radius_m / (111_320 * max(math.cos(math.radians(lat)), 0.01))
        with self._connect() as con:
            cur = con.execute("SELECT lat, lng, data FROM rows WHERE lat BETWEEN ? AND ? AND lng BETWEEN ? AND ?",
                              (lat - dlat, lat + dlat, lng - dlng, lng + dlng))
            for r in cur:
                d = haversine_m(lat, lng, r["lat"], r["lng"])
                if d <= radius_m:
                    yield d, json.loads(r["data"])

    def all_keys(self) -> set[str]:
        with self._connect() as con:
            return {r["key"] for r in con.execute("SELECT DISTINCT key FROM rows")}

    def count_near(self, lat: float, lng: float, radius_m: float) -> int:
        return sum(1 for _ in self.near(lat, lng, radius_m))

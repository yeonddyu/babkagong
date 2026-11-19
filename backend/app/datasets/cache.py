"""외부 API 수집 결과를 로컬 JSON 파일로 보관하는 캐시.

레드테이블·서울 인허가 API 는 지역 필터가 없어 전체 페이지를 받아야 하므로,
서비스 지역 데이터만 걸러 저장하고 TTL 동안 재사용한다 (호출 한도 준수, NF3007).
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable

KST = timezone(timedelta(hours=9))


def now_kst() -> datetime:
    return datetime.now(KST)


class JsonCache:
    def __init__(self, directory: Path, ttl_hours: float, *, clock: Callable[[], datetime] = now_kst):
        self.directory = Path(directory)
        self.ttl = timedelta(hours=ttl_hours)
        self._clock = clock
        self._memory: dict[str, tuple[float, dict[str, Any]]] = {}  # 파일 mtime 기준 메모리 캐시 (NF3005)

    def _path(self, name: str) -> Path:
        return self.directory / f"{name}.json"

    def load(self, name: str) -> dict[str, Any] | None:
        path = self._path(name)
        if not path.exists():
            return None
        try:
            mtime = path.stat().st_mtime
            hit = self._memory.get(name)
            if hit and hit[0] == mtime:
                payload = hit[1]
            else:
                payload = json.loads(path.read_text(encoding="utf-8"))
                self._memory[name] = (mtime, payload)
            fetched_at = datetime.fromisoformat(payload["fetched_at"])
        except (ValueError, KeyError, OSError):
            return None
        if self._clock() - fetched_at > self.ttl:
            return None
        return payload

    def save(self, name: str, data: Any, **meta: Any) -> dict[str, Any]:
        self.directory.mkdir(parents=True, exist_ok=True)
        payload = {"fetched_at": self._clock().isoformat(), **meta, "data": data}
        tmp = self._path(name).with_suffix(".tmp")
        tmp.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        tmp.replace(self._path(name))
        self._memory.pop(name, None)
        return payload

    def get_or_build(self, name: str, builder: Callable[[], tuple[Any, dict[str, Any]]]) -> dict[str, Any]:
        cached = self.load(name)
        if cached is not None:
            return cached
        data, meta = builder()
        return self.save(name, data, **meta)

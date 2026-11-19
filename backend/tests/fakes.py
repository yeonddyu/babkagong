"""외부 HTTP 호출을 대신하는 가짜 세션 (Mock 단위 테스트 전용)."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Callable

import requests


@dataclass
class FakeResponse:
    status_code: int
    text: str


Handler = Callable[[str, dict[str, Any], dict[str, str]], FakeResponse]


@dataclass
class FakeSession:
    """URL 부분 문자열 → 핸들러. 호출 기록을 남긴다."""

    routes: list[tuple[str, Handler]] = field(default_factory=list)
    calls: list[dict[str, Any]] = field(default_factory=list)

    def route(self, url_part: str, handler: Handler) -> "FakeSession":
        self.routes.append((url_part, handler))
        return self

    def get(self, url, *, params=None, headers=None, timeout=None):
        self.calls.append({"url": url, "params": dict(params or {}), "headers": dict(headers or {}), "timeout": timeout})
        # 가장 긴(구체적인) 경로부터 매칭
        for part, handler in sorted(self.routes, key=lambda r: -len(r[0])):
            if part in url:
                return handler(url, params or {}, headers or {})
        raise AssertionError(f"예상하지 못한 URL 호출: {url}")


def json_response(payload: Any, status: int = 200) -> FakeResponse:
    return FakeResponse(status, json.dumps(payload, ensure_ascii=False))


def raise_timeout(*_args) -> FakeResponse:
    raise requests.Timeout("timed out")


def raise_connection_error(*_args) -> FakeResponse:
    raise requests.ConnectionError("conn refused")


def redtable_pages(rows: list[dict[str, Any]], page_size: int = 2) -> Handler:
    """레드테이블 pageNo 페이징을 흉내 낸다."""

    def handler(url, params, headers):
        page = int(params.get("pageNo", 1))
        chunk = rows[(page - 1) * page_size : page * page_size]
        return json_response({
            "header": {"resultCode": "00", "resultMsg": "NORMAL_SERVICE", "numOfRows": page_size, "pageNo": page, "totalCount": len(rows)},
            "body": chunk,
        })

    return handler


def seoul_rows(service: str, rows: list[dict[str, Any]]) -> Handler:
    """서울 열린데이터광장 /START/END/ 범위 조회를 흉내 낸다."""

    def handler(url, params, headers):
        parts = [p for p in url.split("/") if p]
        start, end = int(parts[-2]), int(parts[-1])
        if not rows:
            return json_response({service: {"list_total_count": 0, "RESULT": {"CODE": "INFO-200", "MESSAGE": "해당하는 데이터가 없습니다."}, "row": []}})
        return json_response({
            service: {"list_total_count": len(rows), "RESULT": {"CODE": "INFO-000", "MESSAGE": "정상 처리되었습니다"}, "row": rows[start - 1 : end]}
        })

    return handler

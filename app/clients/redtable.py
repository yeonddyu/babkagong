"""서울관광재단 음식관광 데이터베이스 OPEN API (레드테이블) Client.

- 서비스 URL: https://seoul.openapi.redtable.global
- 인증: serviceKey 쿼리 파라미터 (레드테이블 사이트에서 토큰 발급)
- 요청 파라미터: serviceKey(필수), pageNo(선택) 뿐이다. 지역/식당ID 필터가 없다
  (B161_OpenAPI정의서_레드테이블_서울관광재단.pdf 기준).
- 응답: {"header": {resultCode, resultMsg, numOfRows, pageNo, totalCount}, "body": [...]}
- 키 오류 예: HTTP 401 {"header":{"resultCode":"30","resultMsg":"SERVICE_KEY_IS_NOT_REGISTERED_ERROR"}}
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterator

import requests

from app.clients.http import HTTPSession, http_get, parse_json, raise_for_http_status
from app.core.errors import ErrorCode, ExternalAPIError

PROVIDER = "서울관광재단 음식관광 API"
BASE_URL = "https://seoul.openapi.redtable.global"

ENDPOINT_RESTAURANT = "/api/rstr"  # 식당기본정보
ENDPOINT_OPERATION = "/api/rstr/oprt"  # 식당운영정보
ENDPOINT_MENU_KOREAN = "/api/menu/korean"  # 메뉴정보 한국어

MAX_PAGES = 1000  # 무한 루프 방지 상한


@dataclass
class RedtablePage:
    page_no: int
    num_of_rows: int
    total_count: int
    rows: list[dict[str, Any]]


class RedtableClient:
    def __init__(self, api_key: str | None, *, timeout: float = 10.0, session: HTTPSession | None = None):
        self._api_key = api_key
        self._timeout = timeout
        self._session = session or requests.Session()

    def _require_key(self) -> str:
        if not self._api_key:
            raise ExternalAPIError(
                ErrorCode.MISSING_API_KEY,
                f"{PROVIDER} 키(REDTABLE_API_KEY)가 설정되지 않았습니다.",
                provider=PROVIDER,
            )
        return self._api_key

    def fetch_page(self, endpoint: str, page_no: int = 1) -> RedtablePage:
        key = self._require_key()
        status, text = http_get(
            self._session,
            BASE_URL + endpoint,
            provider=PROVIDER,
            timeout=self._timeout,
            params={"serviceKey": key, "pageNo": page_no},
        )
        payload: Any = None
        if text:
            try:
                payload = parse_json(text, PROVIDER)
            except ExternalAPIError:
                if status == 200:
                    raise
        raise_for_http_status(status, PROVIDER)
        if not isinstance(payload, dict) or not isinstance(payload.get("header"), dict):
            raise ExternalAPIError(ErrorCode.API_ERROR, f"{PROVIDER} 응답에 header 가 없습니다.", provider=PROVIDER)
        header = payload["header"]
        code = str(header.get("resultCode", ""))
        if code not in ("00", "0"):
            raise ExternalAPIError(
                ErrorCode.API_ERROR,
                f"{PROVIDER} 오류 응답입니다. (resultCode={code}, resultMsg={header.get('resultMsg')})",
                provider=PROVIDER,
            )
        body = payload.get("body") or []
        if not isinstance(body, list):
            raise ExternalAPIError(ErrorCode.API_ERROR, f"{PROVIDER} body 형식이 목록이 아닙니다.", provider=PROVIDER)
        return RedtablePage(
            page_no=int(header.get("pageNo") or page_no),
            num_of_rows=int(header.get("numOfRows") or len(body)),
            total_count=int(header.get("totalCount") or 0),
            rows=body,
        )

    def iter_all(self, endpoint: str, *, max_pages: int = MAX_PAGES) -> Iterator[RedtablePage]:
        """pageNo 를 1부터 늘리며 전체 페이지를 순회한다."""
        page_no = 1
        seen = 0
        while page_no <= max_pages:
            page = self.fetch_page(endpoint, page_no)
            if not page.rows:
                return
            yield page
            seen += len(page.rows)
            if page.total_count and seen >= page.total_count:
                return
            page_no += 1

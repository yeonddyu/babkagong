"""서울 열린데이터광장 OpenAPI Client (강남구 일반음식점 인허가 정보).

- 요청 URL: http://openapi.seoul.go.kr:8088/{KEY}/json/{SERVICE}/{START}/{END}/
- 한 번에 최대 1000건. 공개 sample 키는 1~5건만 허용된다.
- 정상: {"SERVICE": {"list_total_count": N, "RESULT": {"CODE": "INFO-000"}, "row": [...]}}
- 오류는 JSON 요청에도 HTTP 200 + XML(<RESULT><CODE>INFO-100</CODE>...) 로 오는 경우가 있다.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

import requests

from app.clients.http import HTTPSession, http_get, parse_json, raise_for_http_status
from app.core.errors import ErrorCode, ExternalAPIError

PROVIDER = "서울 열린데이터광장 API"
BASE_URL = "http://openapi.seoul.go.kr:8088"
SERVICE_GANGNAM_GENERAL_RESTAURANT = "LOCALDATA_072404_GN"  # 강남구 일반음식점 인허가 정보
SERVICE_GANGNAM_REST_FOOD = "LOCALDATA_072405_GN"  # 강남구 휴게음식점 인허가 정보 (커피숍 등)
MAX_ROWS_PER_REQUEST = 1000

_XML_CODE = re.compile(r"<CODE>\s*([A-Z]+-\d+)\s*</CODE>")
_NO_DATA_CODES = {"INFO-200"}  # 해당하는 데이터가 없습니다
_KEY_ERROR_CODES = {"INFO-100", "ERROR-300", "ERROR-301"}


@dataclass
class SeoulRowsPage:
    total_count: int
    rows: list[dict[str, Any]]


class SeoulOpenDataClient:
    def __init__(self, api_key: str | None, *, timeout: float = 10.0, session: HTTPSession | None = None):
        self._api_key = api_key
        self._timeout = timeout
        self._session = session or requests.Session()

    def fetch_rows(self, service: str, start: int, end: int) -> SeoulRowsPage:
        if not self._api_key:
            raise ExternalAPIError(
                ErrorCode.MISSING_API_KEY, f"{PROVIDER} 키(SEOUL_OPENAPI_KEY)가 설정되지 않았습니다.", provider=PROVIDER
            )
        if start < 1 or end < start or end - start + 1 > MAX_ROWS_PER_REQUEST:
            raise ExternalAPIError(ErrorCode.INVALID_INPUT, "요청 범위는 1~1000건이어야 합니다.", provider=PROVIDER)
        url = f"{BASE_URL}/{self._api_key}/json/{service}/{start}/{end}/"
        status, text = http_get(self._session, url, provider=PROVIDER, timeout=self._timeout)
        raise_for_http_status(status, PROVIDER)

        stripped = (text or "").lstrip()
        if stripped.startswith("<"):
            match = _XML_CODE.search(stripped)
            code = match.group(1) if match else "UNKNOWN"
            return self._handle_result_code(code, service)

        payload = parse_json(text, PROVIDER)
        if isinstance(payload, dict) and service not in payload and "RESULT" in payload:
            return self._handle_result_code(str(payload["RESULT"].get("CODE")), service)
        block = payload.get(service) if isinstance(payload, dict) else None
        if not isinstance(block, dict):
            raise ExternalAPIError(ErrorCode.API_ERROR, f"{PROVIDER} 응답에 {service} 항목이 없습니다.", provider=PROVIDER)
        code = str((block.get("RESULT") or {}).get("CODE", ""))
        if code != "INFO-000":
            return self._handle_result_code(code, service)
        rows = block.get("row") or []
        return SeoulRowsPage(total_count=int(block.get("list_total_count") or 0), rows=list(rows))

    @staticmethod
    def _handle_result_code(code: str, service: str) -> SeoulRowsPage:
        if code in _NO_DATA_CODES:
            return SeoulRowsPage(total_count=0, rows=[])
        if code in _KEY_ERROR_CODES:
            raise ExternalAPIError(ErrorCode.API_ERROR, f"{PROVIDER} 인증키가 유효하지 않습니다. (CODE={code})", provider=PROVIDER)
        raise ExternalAPIError(ErrorCode.API_ERROR, f"{PROVIDER} 오류 응답입니다. (service={service}, CODE={code})", provider=PROVIDER)

    def fetch_all(self, service: str, *, max_requests: int = 200) -> SeoulRowsPage:
        first = self.fetch_rows(service, 1, MAX_ROWS_PER_REQUEST)
        rows = list(first.rows)
        total = first.total_count
        start = MAX_ROWS_PER_REQUEST + 1
        requests_made = 1
        while start <= total and requests_made < max_requests:
            page = self.fetch_rows(service, start, min(start + MAX_ROWS_PER_REQUEST - 1, total))
            if not page.rows:
                break
            rows.extend(page.rows)
            start += MAX_ROWS_PER_REQUEST
            requests_made += 1
        return SeoulRowsPage(total_count=total, rows=rows)

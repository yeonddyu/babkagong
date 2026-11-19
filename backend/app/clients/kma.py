"""기상청 단기예보 조회서비스 (공공데이터포털 VilageFcstInfoService_2.0) Client.

- GET https://apis.data.go.kr/1360000/VilageFcstInfoService_2.0/getVilageFcst
- 파라미터: serviceKey(인코딩된 키), pageNo, numOfRows, dataType=JSON, base_date(YYYYMMDD), base_time(HHMM), nx, ny
- 발표: 02·05·08·11·14·17·20·23시 (API 제공은 발표 약 10분 후)
- 정상: {"response":{"header":{"resultCode":"00"},"body":{"items":{"item":[{category, fcstDate, fcstTime, fcstValue, ...}]},"totalCount":N}}}
- 오류: resultCode 03 NO_DATA, 키 오류 시 XML(OpenAPI_ServiceResponse) 응답
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Any

import requests

from app.clients.http import HTTPSession, http_get, parse_json, raise_for_http_status
from app.core.errors import ErrorCode, ExternalAPIError

PROVIDER = "기상청 단기예보 API"
BASE_URL = "https://apis.data.go.kr/1360000/VilageFcstInfoService_2.0/getVilageFcst"
BASE_HOURS = (2, 5, 8, 11, 14, 17, 20, 23)
ROWS_PER_PAGE = 1000


def latlon_to_grid(lat: float, lon: float) -> tuple[int, int]:
    """위경도 → 기상청 동네예보 격자(nx, ny). 기상청 Lambert Conformal Conic 변환식."""
    re_, grid = 6371.00877, 5.0
    slat1, slat2, olon, olat = 30.0, 60.0, 126.0, 38.0
    xo, yo = 43, 136
    degrad = math.pi / 180.0
    re_g = re_ / grid
    slat1, slat2, olon, olat = slat1 * degrad, slat2 * degrad, olon * degrad, olat * degrad
    sn = math.tan(math.pi * 0.25 + slat2 * 0.5) / math.tan(math.pi * 0.25 + slat1 * 0.5)
    sn = math.log(math.cos(slat1) / math.cos(slat2)) / math.log(sn)
    sf = math.tan(math.pi * 0.25 + slat1 * 0.5)
    sf = math.pow(sf, sn) * math.cos(slat1) / sn
    ro = math.tan(math.pi * 0.25 + olat * 0.5)
    ro = re_g * sf / math.pow(ro, sn)
    ra = math.tan(math.pi * 0.25 + lat * degrad * 0.5)
    ra = re_g * sf / math.pow(ra, sn)
    theta = lon * degrad - olon
    if theta > math.pi:
        theta -= 2.0 * math.pi
    if theta < -math.pi:
        theta += 2.0 * math.pi
    theta *= sn
    nx = math.floor(ra * math.sin(theta) + xo + 0.5)
    ny = math.floor(ro - ra * math.cos(theta) + yo + 0.5)
    return nx, ny


@dataclass
class ForecastItems:
    base_date: str
    base_time: str
    items: list[dict[str, Any]]


_XML_REASON = re.compile(r"<returnAuthMsg>([^<]+)</returnAuthMsg>|<resultMsg>([^<]+)</resultMsg>")


class KMAClient:
    def __init__(self, api_key: str | None, *, timeout: float = 10.0, session: HTTPSession | None = None):
        self._api_key = api_key
        self._timeout = timeout
        self._session = session or requests.Session()

    def fetch_forecast(self, base_date: str, base_time: str, nx: int, ny: int) -> ForecastItems:
        if not self._api_key:
            raise ExternalAPIError(ErrorCode.MISSING_API_KEY, f"{PROVIDER} 키(KMA_API_KEY)가 설정되지 않았습니다.", provider=PROVIDER)
        items: list[dict[str, Any]] = []
        page = 1
        while True:
            # 공공데이터포털 인코딩 키는 다시 인코딩되지 않도록 URL 에 직접 붙인다
            status, text = http_get(
                self._session, f"{BASE_URL}?serviceKey={self._api_key}", provider=PROVIDER, timeout=self._timeout,
                params={"pageNo": page, "numOfRows": ROWS_PER_PAGE, "dataType": "JSON", "base_date": base_date,
                        "base_time": base_time, "nx": nx, "ny": ny},
            )
            raise_for_http_status(status, PROVIDER)
            stripped = (text or "").lstrip()
            if stripped.startswith("<"):
                match = _XML_REASON.search(stripped)
                reason = next((g for g in match.groups() if g), "XML 오류 응답") if match else "XML 오류 응답"
                raise ExternalAPIError(ErrorCode.API_ERROR, f"{PROVIDER} 오류 응답입니다. ({reason})", provider=PROVIDER)
            payload = parse_json(text, PROVIDER)
            resp = payload.get("response") if isinstance(payload, dict) else None
            header = (resp or {}).get("header") or {}
            code = str(header.get("resultCode", ""))
            if code == "03":  # NO_DATA
                raise ExternalAPIError(ErrorCode.NO_RESULT, f"{PROVIDER}에 해당 발표 시각의 예보가 없습니다.", provider=PROVIDER)
            if code != "00":
                raise ExternalAPIError(ErrorCode.API_ERROR, f"{PROVIDER} 오류 응답입니다. (resultCode={code}, {header.get('resultMsg')})", provider=PROVIDER)
            body = resp.get("body") or {}
            page_items = ((body.get("items") or {}).get("item")) or []
            items.extend(page_items)
            total = int(body.get("totalCount") or 0)
            if not page_items or len(items) >= total or page >= 5:
                break
            page += 1
        return ForecastItems(base_date=base_date, base_time=base_time, items=items)

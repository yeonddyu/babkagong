"""카카오 로컬 API Client - 카테고리·키워드로 장소 검색.

- 키워드: GET https://dapi.kakao.com/v2/local/search/keyword.json (query, x, y, radius, size) — 역 출구 좌표 조회에 사용

- GET https://dapi.kakao.com/v2/local/search/category.json
- 헤더: Authorization: KakaoAK {REST_API_KEY}
- 파라미터: category_group_code(CE7=카페), x(경도), y(위도), radius(0~20000m), page(1~45), size(1~15), sort(distance|accuracy)
- 응답: {"meta": {total_count, pageable_count, is_end}, "documents": [{id, place_name, address_name, road_address_name, x, y, distance, place_url, phone, category_name, ...}]}
- 키 없음/오류 예: HTTP 401 {"errorType":"AccessDeniedError","message":"cannot find Authorization : KakaoAK header"}
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import requests

from app.clients.http import HTTPSession, http_get, parse_json, raise_for_http_status
from app.core.errors import ErrorCode, ExternalAPIError

PROVIDER = "카카오 로컬 API"
CATEGORY_URL = "https://dapi.kakao.com/v2/local/search/category.json"
KEYWORD_URL = "https://dapi.kakao.com/v2/local/search/keyword.json"
CATEGORY_CAFE = "CE7"
MAX_PAGE_SIZE = 15
MAX_PAGE = 45
MAX_RADIUS_M = 20000


@dataclass
class KakaoPage:
    documents: list[dict[str, Any]]
    total_count: int
    pageable_count: int
    is_end: bool


class KakaoLocalClient:
    def __init__(self, api_key: str | None, *, timeout: float = 10.0, session: HTTPSession | None = None):
        self._api_key = api_key
        self._timeout = timeout
        self._session = session or requests.Session()

    def search_keyword(self, query: str, *, lat: float, lng: float, radius_m: int, size: int = MAX_PAGE_SIZE) -> KakaoPage:
        """키워드로 장소 검색 (첫 페이지, 기준 좌표 반경 안)."""
        return self._get(KEYWORD_URL, {"query": query, "x": f"{lng:.7f}", "y": f"{lat:.7f}", "radius": radius_m, "size": size})

    def search_category(
        self, category: str, *, lat: float, lng: float, radius_m: int, page: int = 1, size: int = MAX_PAGE_SIZE,
        sort: str = "distance",
    ) -> KakaoPage:
        return self._get(CATEGORY_URL, {
            "category_group_code": category, "x": f"{lng:.7f}", "y": f"{lat:.7f}",
            "radius": radius_m, "page": page, "size": size, "sort": sort,
        })

    def _get(self, url: str, params: dict[str, Any]) -> KakaoPage:
        if not self._api_key:
            raise ExternalAPIError(ErrorCode.MISSING_API_KEY, f"{PROVIDER} 키(KAKAO_REST_API_KEY)가 설정되지 않았습니다.", provider=PROVIDER)
        status, text = http_get(
            self._session,
            url,
            provider=PROVIDER,
            timeout=self._timeout,
            params=params,
            headers={"Authorization": f"KakaoAK {self._api_key}"},
        )
        raise_for_http_status(status, PROVIDER)
        payload = parse_json(text, PROVIDER)
        if not isinstance(payload, dict) or not isinstance(payload.get("documents"), list):
            raise ExternalAPIError(ErrorCode.API_ERROR, f"{PROVIDER} 응답에 documents 가 없습니다.", provider=PROVIDER)
        meta = payload.get("meta") or {}
        return KakaoPage(
            documents=payload["documents"],
            total_count=int(meta.get("total_count") or 0),
            pageable_count=int(meta.get("pageable_count") or 0),
            is_end=bool(meta.get("is_end", True)),
        )

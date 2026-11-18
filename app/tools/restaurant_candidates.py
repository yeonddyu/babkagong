"""F3002 음식점 후보 조회 Tool: search_restaurant_candidates.

1순위: 서울관광재단 음식관광 API 식당기본정보 (상세정보 Tool 과 ID 로 연결 가능)
보완 : 강남구 일반음식점 인허가 정보 (1순위로 max_results 를 채우지 못할 때 보충)
"""
from __future__ import annotations

import re
from datetime import date
from typing import Callable, Literal

from pydantic import BaseModel, Field

from app.core.errors import ErrorCode, ExternalAPIError
from app.core.geo import STATIONS, haversine_m
from app.datasets.cache import now_kst
from app.datasets.restaurants import (
    SOURCE_GANGNAM_LICENSE,
    SOURCE_REDTABLE,
    GangnamLicenseDataset,
    RedtableRestaurantDataset,
    RestaurantRecord,
    license_open_on,
)
from app.tools.common import ToolError, ToolKind, ToolSpec

TOOL_NAME = "search_restaurant_candidates"
SEARCH_RADIUS_M = 700  # 역 중심 도보 약 10분
DUPLICATE_DISTANCE_M = 30

Area = Literal["강남역", "역삼역"]
FoodType = Literal["한식", "중식", "일식", "양식", "분식", "기타"]

# 출처 원본 분류값 → 정규화 음식 종류. 매핑에 없는 값은 "기타".
CATEGORY_MAP: dict[str, str] = {
    "한식": "한식", "냉면집": "한식", "식육(숯불구이)": "한식", "탕류(보신용)": "한식", "복어취급": "한식",
    "중국식": "중식", "중식": "중식",
    "일식": "일식", "횟집": "일식",
    "경양식": "양식", "양식": "양식", "패밀리레스토랑": "양식", "패스트푸드": "양식",
    "분식": "분식", "김밥(도시락)": "분식",
}
# 식당 후보에서 제외하는 카페류 분류 (카페는 F3004 에서 카카오로 검색)
CAFE_CATEGORIES = {"까페", "카페", "커피숍", "다방", "전통찻집", "키즈카페", "라이브카페", "떡카페"}


class RestaurantSearchInput(BaseModel):
    area: Area = Field(description="검색 지역. '강남역' 또는 '역삼역'")
    food_type: FoodType | None = Field(default=None, description="음식 종류. 생략하면 전체")
    reference_date: date | None = Field(
        default=None, description="영업 여부 판단 기준일(YYYY-MM-DD). 생략하면 오늘(KST)"
    )
    max_results: int = Field(default=10, ge=1, le=50, description="최대 결과 수 (1~50, 기본 10)")


class RestaurantCandidate(BaseModel):
    name: str
    source: str = Field(description="출처 코드. 상세정보 Tool 에 그대로 전달")
    source_id: str = Field(description="출처 내부 식별자. 다른 출처 ID 와 호환되지 않음")
    road_address: str | None
    jibun_address: str | None
    latitude: float | None
    longitude: float | None
    coordinate_note: str | None
    distance_m: int | None = Field(description="검색 지역 중심으로부터 직선거리(m)")
    category: str | None = Field(description="출처 원본 분류값")
    food_type: str | None = Field(description="정규화 음식 종류")
    business_status: str | None = Field(default=None, description="인허가 데이터의 현재 영업상태 (해당 출처만)")
    detail_available: bool = Field(description="get_restaurant_details 로 메뉴·운영정보 조회 가능 여부")


class QueryBasis(BaseModel):
    requested_date: date | None
    applied_date: date
    default_applied: bool = Field(description="기준일을 생략하여 기본값(오늘)을 적용했는지")
    differs_from_request: bool = Field(description="요청 기준과 실제 조회 기준이 다른지")
    notes: list[str]


class SourceStatus(BaseModel):
    source: str
    provider: str
    ok: bool
    returned: int = 0
    error_code: ErrorCode | None = None
    message: str | None = None
    data_fetched_at: str | None = None
    data_updated_at: str | None = None


class RestaurantSearchOutput(BaseModel):
    area: str
    center: dict[str, float]
    radius_m: int
    food_type: str | None
    query_basis: QueryBasis
    candidates: list[RestaurantCandidate]
    source_status: list[SourceStatus]
    skipped_possible_duplicates: int = Field(description="보완 출처에서 이름·위치가 같아 제외한 수 (ID 연결은 하지 않음)")


DESCRIPTION = (
    "강남역 또는 역삼역 주변에서 식사할 음식점 후보 목록이 필요할 때 사용한다. "
    "음식 종류(한식/중식/일식/양식/분식/기타)와 영업 기준일로 거른 후보를 거리순으로 돌려준다. "
    "각 후보의 source 와 source_id 는 get_restaurant_details 에 그대로 넘겨 메뉴·가격·영업시간을 확인한다. "
    "카페는 이 Tool 이 아니라 search_nearby_cafes 로 찾는다."
)


def _normalize_name(name: str) -> str:
    return re.sub(r"[\s()\[\]·\-_.,]", "", name).lower()


def _food_type_of(category: str | None) -> str | None:
    if not category:
        return None
    return CATEGORY_MAP.get(category, "기타")


def _to_candidate(rec: RestaurantRecord, center: tuple[float, float], distance: float) -> RestaurantCandidate:
    return RestaurantCandidate(
        name=rec.name,
        source=rec.source,
        source_id=rec.source_id,
        road_address=rec.road_address,
        jibun_address=rec.jibun_address,
        latitude=rec.latitude,
        longitude=rec.longitude,
        coordinate_note=rec.coordinate_note,
        distance_m=round(distance),
        category=rec.category,
        food_type=_food_type_of(rec.category),
        business_status=rec.status_name if rec.source == SOURCE_GANGNAM_LICENSE else None,
        detail_available=rec.source == SOURCE_REDTABLE,
    )


def _filter_area(records, center, food_type):
    out = []
    for rec in records:
        if rec.latitude is None or rec.longitude is None:
            continue
        if rec.category in CAFE_CATEGORIES:
            continue
        if food_type and _food_type_of(rec.category) != food_type:
            continue
        dist = haversine_m(center[0], center[1], rec.latitude, rec.longitude)
        if dist <= SEARCH_RADIUS_M:
            out.append((dist, rec))
    out.sort(key=lambda t: (t[0], t[1].name))
    return out


def create_tool(
    redtable: RedtableRestaurantDataset,
    gangnam_license: GangnamLicenseDataset,
    *,
    today_fn: Callable[[], date] = lambda: now_kst().date(),
) -> ToolSpec:
    def run(params: RestaurantSearchInput) -> RestaurantSearchOutput:
        today = today_fn()
        center = STATIONS[params.area]
        notes: list[str] = []
        requested = params.reference_date
        applied = requested or today
        differs = False
        if requested is None:
            notes.append(f"기준일이 생략되어 기본값인 오늘({today.isoformat()}, KST)을 적용했습니다.")
        elif requested > today:
            applied = today
            differs = True
            notes.append(
                f"요청 기준일 {requested.isoformat()}은 미래라서 인허가 데이터로 영업 여부를 알 수 없으므로 "
                f"오늘({today.isoformat()}) 기준 영업상태로 조회했습니다."
            )
        notes.append("서울관광재단 식당기본정보는 기준일 조회를 지원하지 않아 데이터 수집 시점 기준입니다(폐업 여부 미포함).")
        if params.area == "강남역":
            notes.append("강남구 인허가 데이터에는 강남역 서측(서초구) 업소가 포함되지 않습니다.")

        statuses: list[SourceStatus] = []
        candidates: list[RestaurantCandidate] = []

        # 1순위: 레드테이블
        primary: list[tuple[float, RestaurantRecord]] = []
        try:
            records, meta = redtable.load()
            primary = _filter_area(records, center, params.food_type)
            selected = primary[: params.max_results]
            candidates.extend(_to_candidate(r, center, d) for d, r in selected)
            statuses.append(SourceStatus(
                source=SOURCE_REDTABLE, provider="서울관광재단 음식관광 API", ok=True,
                returned=len(selected), data_fetched_at=meta.get("fetched_at"),
            ))
        except ExternalAPIError as exc:
            statuses.append(SourceStatus(
                source=SOURCE_REDTABLE, provider="서울관광재단 음식관광 API", ok=False,
                error_code=exc.code, message=exc.message,
            ))

        # 보완: 강남구 인허가 (1순위로 채우지 못한 만큼)
        skipped = 0
        remaining = params.max_results - len(candidates)
        if remaining > 0:
            try:
                records, meta = gangnam_license.load()
                open_records = [r for r in records if license_open_on(r, applied, today)]
                supplement = _filter_area(open_records, center, params.food_type)
                primary_keys = [(_normalize_name(r.name), r) for _, r in primary]
                added = 0
                for dist, rec in supplement:
                    if added >= remaining:
                        break
                    key = _normalize_name(rec.name)
                    if any(
                        k == key and haversine_m(p.latitude, p.longitude, rec.latitude, rec.longitude) <= DUPLICATE_DISTANCE_M
                        for k, p in primary_keys
                    ):
                        skipped += 1
                        continue
                    candidates.append(_to_candidate(rec, center, dist))
                    added += 1
                statuses.append(SourceStatus(
                    source=SOURCE_GANGNAM_LICENSE, provider="서울 열린데이터광장 API", ok=True, returned=added,
                    data_fetched_at=meta.get("fetched_at"), data_updated_at=meta.get("data_updated_at"),
                ))
            except ExternalAPIError as exc:
                statuses.append(SourceStatus(
                    source=SOURCE_GANGNAM_LICENSE, provider="서울 열린데이터광장 API", ok=False,
                    error_code=exc.code, message=exc.message,
                ))
        else:
            statuses.append(SourceStatus(
                source=SOURCE_GANGNAM_LICENSE, provider="서울 열린데이터광장 API", ok=True, returned=0,
                message="1순위 출처로 최대 결과 수를 채워 보완 조회를 생략했습니다.",
            ))

        failures = [s for s in statuses if not s.ok]
        if len(failures) == len(statuses):
            codes = {f.error_code for f in failures}
            code = ErrorCode.MISSING_API_KEY if codes == {ErrorCode.MISSING_API_KEY} else failures[0].error_code
            raise ToolError(code, "음식점 후보를 조회하지 못했습니다: " + " / ".join(f.message or "" for f in failures))
        if not candidates:
            detail = f" (일부 출처 실패: {', '.join(f.provider for f in failures)})" if failures else ""
            raise ToolError(ErrorCode.NO_RESULT, f"{params.area} 반경 {SEARCH_RADIUS_M}m 안에 조건에 맞는 음식점이 없습니다.{detail}")

        return RestaurantSearchOutput(
            area=params.area,
            center={"latitude": center[0], "longitude": center[1]},
            radius_m=SEARCH_RADIUS_M,
            food_type=params.food_type,
            query_basis=QueryBasis(
                requested_date=requested, applied_date=applied, default_applied=requested is None,
                differs_from_request=differs, notes=notes,
            ),
            candidates=candidates,
            source_status=statuses,
            skipped_possible_duplicates=skipped,
        )

    return ToolSpec(
        name=TOOL_NAME,
        description=DESCRIPTION,
        kind=ToolKind.EXTERNAL_API,
        providers=["서울관광재단 음식관광 API (식당기본정보)", "서울 열린데이터광장 (강남구 일반음식점 인허가 정보)"],
        input_model=RestaurantSearchInput,
        output_model=RestaurantSearchOutput,
        error_codes=[ErrorCode.INVALID_INPUT, ErrorCode.MISSING_API_KEY, ErrorCode.NO_RESULT, ErrorCode.TIMEOUT, ErrorCode.API_ERROR],
        func=run,
    )

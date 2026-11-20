"""F3002 음식점 후보 조회 Tool: search_restaurant_candidates.

1순위: 서울관광재단 음식관광 API 식당기본정보 (상세정보 Tool 과 ID 로 연결 가능)
보완 : 강남구 일반음식점 인허가 정보 (1순위로 max_results 를 채우지 못할 때 보충)

정렬(order)
- distance (기본): 가까운 순. 같은 요청이면 항상 같은 후보.
- varied : 반경 안 후보를 거리 구간(가까움/중간/멂)으로 나누고 seed 로 구간 안을 섞은 뒤,
           메뉴 정보가 있는 곳을 먼저, 구간을 번갈아 뽑는다. 결과는 거리순으로 돌려준다.
           (가장 가까운 몇 곳만 반복 추천되는 문제 해결. seed 가 같으면 같은 결과 → 재현 가능)
"""
from __future__ import annotations

import logging
import random
import re
from datetime import date
from typing import Callable, Literal

from pydantic import BaseModel, Field

from app.core.errors import ErrorCode, ExternalAPIError
from app.core.geo import STATIONS, haversine_m
from app.datasets.cache import now_kst
from app.datasets.exits import StationExitDataset
from app.datasets.restaurants import (
    SOURCE_GANGNAM_LICENSE,
    SOURCE_REDTABLE,
    GangnamLicenseDataset,
    RedtableDetailDataset,
    RedtableRestaurantDataset,
    RestaurantRecord,
    license_open_on,
)
from app.tools.common import ToolError, ToolKind, ToolSpec

logger = logging.getLogger(__name__)

TOOL_NAME = "search_restaurant_candidates"
SEARCH_RADIUS_M = 700  # 역 중심 도보 약 10분
DUPLICATE_DISTANCE_M = 30
VARIED_BANDS_M = (250, 450)  # varied 정렬의 거리 구간 경계 (0~250, 250~450, 450~반경)

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
# 식당 후보에서 제외하는 비식사 업종 (카페는 F3004 에서 검색). 분류값이 비어 있는 경우를 위해 이름 패턴도 본다.
CAFE_CATEGORIES = {"까페", "카페", "커피숍", "다방", "전통찻집", "키즈카페", "라이브카페", "떡카페", "제과점영업", "아이스크림", "편의점",
                   "기타 휴게음식점"}
NON_MEAL_NAME = re.compile(
    r"카페|커피|coffee|cafe|타로|사주|베이커리|도넛|도너츠|아이스크림|빙수|쥬스|주스|솜사탕|요거트|마카롱|"
    r"이디야|스타벅스|투썸|메가\s*(?:MGC|커피)|빽다방|컴포즈|할리스|폴바셋|커피빈|파스쿠찌|엔제리너스|탐앤탐스|공차|"
    r"배스킨|베스킨|설빙|파리바게|뚜레쥬르|크리스피", re.IGNORECASE)


class RestaurantSearchInput(BaseModel):
    area: Area = Field(description="검색 지역. '강남역' 또는 '역삼역'")
    food_type: FoodType | None = Field(default=None, description="음식 종류. 생략하면 전체")
    reference_date: date | None = Field(
        default=None, description="영업 여부 판단 기준일(YYYY-MM-DD). 생략하면 오늘(KST)"
    )
    max_results: int = Field(default=10, ge=1, le=50, description="최대 결과 수 (1~50, 기본 10)")
    order: Literal["distance", "varied"] = Field(
        default="distance",
        description="distance: 가까운 순(기본). varied: 반경 안에서 거리 구간별로 고르게 섞어 고름(메뉴 정보 있는 곳 우선)")
    seed: int | None = Field(default=None, description="order=varied 의 섞기 기준값. 같으면 같은 결과, 생략하면 매번 다름")
    exit_number: int | None = Field(default=None, ge=1, le=20,
                                    description="사용자가 'N번 출구' 를 말했을 때 그 출구를 거리 기준점으로 사용. 찾지 못하면 역 중심 기준")
    radius_m: int | None = Field(default=None, ge=50, le=SEARCH_RADIUS_M,
                                 description="역 중심 검색 반경(m, 50~700). 사용자가 거리·도보 시간 제한을 말했을 때만 지정, 생략하면 700")


class RestaurantCandidate(BaseModel):
    name: str
    source: str = Field(description="출처 코드. 상세정보 Tool 에 그대로 전달")
    source_id: str = Field(description="출처 내부 식별자. 다른 출처 ID 와 호환되지 않음")
    road_address: str | None
    jibun_address: str | None
    latitude: float | None
    longitude: float | None
    coordinate_note: str | None
    distance_m: int | None = Field(description="거리 기준점(origin: 역 중심 또는 지정한 출구)으로부터 직선거리(m)")
    category: str | None = Field(description="출처 원본 분류값")
    food_type: str | None = Field(description="정규화 음식 종류")
    business_status: str | None = Field(default=None, description="인허가 데이터의 현재 영업상태 (해당 출처만)")
    detail_available: bool = Field(description="get_restaurant_details 로 메뉴·운영정보 조회 가능 여부")
    menu_available: bool | None = Field(default=None, description="출처에 메뉴 정보가 있는지 (확인 못 하면 null)")


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


class Origin(BaseModel):
    kind: Literal["station", "exit"]
    label: str = Field(description="예: '강남역', '강남역 11번 출구'")
    latitude: float
    longitude: float
    source: str = Field(description="좌표 출처")
    place_url: str | None = None


class RestaurantSearchOutput(BaseModel):
    area: str
    center: dict[str, float]
    radius_m: int
    origin: Origin | None = Field(default=None, description="거리 기준점")
    food_type: str | None
    order: str = "distance"
    pool_size: int = Field(default=0, description="반경·조건을 통과한 1순위 출처 전체 후보 수 (이 중에서 max_results 만큼 고름)")
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


def _varied(pool: list[tuple[float, RestaurantRecord]], n: int, seed: int | None,
            has_menu: set[str] | None, radius_m: int = SEARCH_RADIUS_M) -> list[tuple[float, RestaurantRecord]]:
    """거리 구간별로 섞어 고르게 n 곳을 뽑는다. 구간 안에서는 메뉴 정보가 있는 곳이 먼저.
    구간 경계는 반경에 비례한다 (반경 700m 기준 250·450m)."""
    rng = random.Random(seed)
    edges = [b * radius_m / SEARCH_RADIUS_M for b in VARIED_BANDS_M]
    bands: list[list[tuple[float, RestaurantRecord]]] = [[] for _ in range(len(edges) + 1)]
    for item in pool:
        bands[sum(item[0] >= b for b in edges)].append(item)
    for band in bands:
        rng.shuffle(band)
        if has_menu is not None:
            band.sort(key=lambda t: t[1].source_id not in has_menu)  # 안정 정렬: 섞은 순서 유지
    picked: list[tuple[float, RestaurantRecord]] = []
    while len(picked) < n and any(bands):
        for band in bands:
            if band and len(picked) < n:
                picked.append(band.pop(0))
    picked.sort(key=lambda t: (t[0], t[1].name))
    return picked


def _to_candidate(rec: RestaurantRecord, center: tuple[float, float], distance: float,
                  has_menu: set[str] | None = None) -> RestaurantCandidate:
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
        menu_available=(rec.source_id in has_menu) if (has_menu is not None and rec.source == SOURCE_REDTABLE)
        else (False if rec.source != SOURCE_REDTABLE else None),
    )


def _filter_area(records, center, food_type, radius_m: int = SEARCH_RADIUS_M):
    out = []
    for rec in records:
        if rec.latitude is None or rec.longitude is None:
            continue
        if rec.category in CAFE_CATEGORIES or NON_MEAL_NAME.search(rec.name):
            continue
        if food_type and _food_type_of(rec.category) != food_type:
            continue
        dist = haversine_m(center[0], center[1], rec.latitude, rec.longitude)
        if dist <= radius_m:
            out.append((dist, rec))
    out.sort(key=lambda t: (t[0], t[1].name))
    return out


def create_tool(
    redtable: RedtableRestaurantDataset,
    gangnam_license: GangnamLicenseDataset,
    redtable_details: RedtableDetailDataset | None = None,
    exits: StationExitDataset | None = None,
    *,
    today_fn: Callable[[], date] = lambda: now_kst().date(),
) -> ToolSpec:
    def run(params: RestaurantSearchInput) -> RestaurantSearchOutput:
        today = today_fn()
        center = STATIONS[params.area]
        radius = params.radius_m or SEARCH_RADIUS_M
        origin = Origin(kind="station", label=params.area, latitude=center[0], longitude=center[1], source="서비스 기준 역 좌표")
        exit_note: str | None = None
        if params.exit_number is not None:
            hit, reason = exits.find(params.area, params.exit_number) if exits else (None, "출구 위치 데이터를 사용할 수 없습니다")
            if hit:
                center = (hit["latitude"], hit["longitude"])
                origin = Origin(kind="exit", label=f"{params.area} {params.exit_number}번 출구", latitude=center[0],
                                longitude=center[1], source=f"카카오 로컬 '{hit['name']}'", place_url=hit.get("place_url"))
                exit_note = f"거리는 {origin.label}(카카오 로컬 '{hit['name']}' 좌표) 기준입니다."
            else:
                exit_note = f"{reason} — 역 중심 기준으로 찾았습니다."
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
        if exit_note:
            notes.append(exit_note)
        notes.append("서울관광재단 식당기본정보는 기준일 조회를 지원하지 않아 데이터 수집 시점 기준입니다(폐업 여부 미포함).")
        if params.area == "강남역":
            notes.append("강남구 인허가 데이터에는 강남역 서측(서초구) 업소가 포함되지 않습니다.")

        statuses: list[SourceStatus] = []
        candidates: list[RestaurantCandidate] = []

        # 메뉴 정보 보유 여부 (varied 정렬에서만 사용하는 부가 정보 — 실패해도 후보 조회는 계속, 값은 null)
        has_menu: set[str] | None = None
        if redtable_details is not None and params.order == "varied":
            try:
                has_menu = {str(k) for k in redtable_details.menus_by_id()[0]}
            except Exception:  # noqa: BLE001 - 부가 정보라 실패를 후보 조회 실패로 만들지 않는다
                logger.warning("메뉴 정보 보유 여부를 확인하지 못해 menu_available 을 null 로 둡니다", exc_info=True)
                has_menu = None

        # 1순위: 레드테이블
        primary: list[tuple[float, RestaurantRecord]] = []
        try:
            records, meta = redtable.load()
            primary = _filter_area(records, center, params.food_type, radius)
            if params.order == "varied":
                selected = _varied(primary, params.max_results, params.seed, has_menu, radius)
                notes.append(f"반경 안 후보 {len(primary)}곳에서 거리 구간별로 고르게 {len(selected)}곳을 골랐습니다"
                             + (" (메뉴 정보가 있는 곳 우선)." if has_menu is not None else "."))
            else:
                selected = primary[: params.max_results]
            candidates.extend(_to_candidate(r, center, d, has_menu) for d, r in selected)
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
                supplement = _filter_area(open_records, center, params.food_type, radius)
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
                    candidates.append(_to_candidate(rec, center, dist, has_menu))
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
            raise ToolError(ErrorCode.NO_RESULT, f"{origin.label} 반경 {radius}m 안에 조건에 맞는 음식점이 없습니다.{detail}")

        return RestaurantSearchOutput(
            area=params.area,
            center={"latitude": center[0], "longitude": center[1]},
            radius_m=radius,
            origin=origin,
            food_type=params.food_type,
            order=params.order,
            pool_size=len(primary),
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

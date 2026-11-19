"""F3004 주변 카페 검색 Tool: search_nearby_cafes.

1순위: 카카오 로컬 API 카테고리 검색(CE7 카페) — 이름·주소·좌표·거리·장소 링크
보조 : 강남구 휴게음식점 인허가(커피숍·다방 등) — 카카오 호출이 실패했거나 결과가 없을 때만 사용.
       이름·주소·좌표(변환)만 있고 장소 링크는 없다. 카카오 장소와 연결하지 않는다.

거리: 카카오가 준 거리(또는 확인된 좌표로 계산한 값)는 직선거리다.
      도보 시간은 직선거리 × 1.3 ÷ 67m/분 으로 추정한 값이며 실제 경로 시간이 아니다.
영업시간·콘센트·와이파이·혼잡도는 두 출처 모두 제공하지 않으므로 null 로 둔다.
"""
from __future__ import annotations

import math
from datetime import date
from typing import Callable

from pydantic import BaseModel, Field

from app.clients.kakao_local import CATEGORY_CAFE, MAX_PAGE, MAX_PAGE_SIZE, MAX_RADIUS_M, KakaoLocalClient
from app.core.errors import ErrorCode, ExternalAPIError
from app.core.geo import haversine_m, to_float
from app.datasets.cache import now_kst
from app.datasets.restaurants import GangnamLicenseDataset, license_open_on
from app.tools.common import ToolError, ToolKind, ToolSpec

TOOL_NAME = "search_nearby_cafes"
NOT_PROVIDED_FIELDS = ["opening_hours", "power_outlet", "wifi", "congestion"]
SOURCE_KAKAO = "kakao_local_category_CE7"
SOURCE_REST_FOOD = "gangnam_rest_food_license"
CAFE_LICENSE_CATEGORIES = {"커피숍", "다방", "전통찻집", "떡카페", "까페"}

WALK_DETOUR_FACTOR = 1.3  # 직선거리 대비 실제 보행 경로 보정 (밥카공 추정 정책)
WALK_SPEED_M_PER_MIN = 67  # 약 4km/h
WALK_BASIS = f"직선거리×{WALK_DETOUR_FACTOR}÷{WALK_SPEED_M_PER_MIN}m/분 추정 (실제 경로 아님)"


def estimate_walk_minutes(distance_m: int | None) -> int | None:
    if distance_m is None:
        return None
    return max(1, math.ceil(distance_m * WALK_DETOUR_FACTOR / WALK_SPEED_M_PER_MIN))


class CafeSearchInput(BaseModel):
    latitude: float = Field(ge=33.0, le=39.0, description="기준 위도 (예: 식당 후보의 latitude)")
    longitude: float = Field(ge=124.0, le=132.0, description="기준 경도 (예: 식당 후보의 longitude)")
    radius_m: int = Field(default=500, ge=1, le=MAX_RADIUS_M, description="검색 반경(m), 1~20000, 기본 500")
    max_results: int = Field(default=10, ge=1, le=MAX_PAGE_SIZE * MAX_PAGE, description="최대 결과 수, 기본 10")


class CafeInfo(BaseModel):
    source: str = Field(description="출처 코드")
    source_id: str = Field(description="출처 내부 식별자 (카카오 장소 ID 또는 인허가 관리번호)")
    name: str
    address: str | None = Field(description="지번 주소")
    road_address: str | None
    latitude: float
    longitude: float
    distance_m: int | None = Field(description="기준 좌표로부터 직선거리(m)")
    distance_basis: str | None = Field(description="거리 출처 (카카오 제공 / 좌표로 계산)")
    estimated_walk_minutes: int | None = Field(description="직선거리 기반 도보 추정 시간(분). 실제 경로 시간 아님")
    place_url: str | None = Field(description="카카오맵 장소 상세 링크 (보조 출처는 null)")
    phone: str | None
    category_name: str | None
    opening_hours: None = Field(default=None, description="미제공 → 항상 null")
    power_outlet: None = Field(default=None, description="미제공 → 항상 null")
    wifi: None = Field(default=None, description="미제공 → 항상 null")
    congestion: None = Field(default=None, description="미제공 → 항상 null")


class CafeSourceStatus(BaseModel):
    source: str
    ok: bool
    returned: int = 0
    error_code: ErrorCode | None = None
    message: str | None = None


class CafeSearchOutput(BaseModel):
    center: dict[str, float]
    radius_m: int
    total_count: int = Field(description="1순위(카카오)가 보고한 반경 내 카페 수, 보조 출처만 쓰면 그 수")
    cafes: list[CafeInfo]
    not_provided_fields: list[str]
    walk_time_basis: str
    source_status: list[CafeSourceStatus]


DESCRIPTION = (
    "식사할 음식점이 정해진 뒤 그 주변에서 카공(공부·작업)할 카페를 찾아야 할 때 사용한다. "
    "음식점 후보의 latitude/longitude 를 넣으면 반경 안의 카페를 가까운 순으로 돌려준다. "
    "거리는 직선거리이고 도보 시간은 추정치다. 영업시간·콘센트·와이파이·혼잡도는 이 Tool 로 확인할 수 없어 항상 null 이다."
)


def _kakao_cafes(client: KakaoLocalClient, params: CafeSearchInput) -> tuple[list[CafeInfo], int]:
    cafes: list[CafeInfo] = []
    seen: set[str] = set()
    total = 0
    page = 1
    while len(cafes) < params.max_results and page <= MAX_PAGE:
        result = client.search_category(
            CATEGORY_CAFE, lat=params.latitude, lng=params.longitude, radius_m=params.radius_m,
            page=page, size=MAX_PAGE_SIZE, sort="distance",
        )
        total = result.total_count
        for doc in result.documents:
            pid = str(doc.get("id") or "").strip()
            lat, lng = to_float(doc.get("y")), to_float(doc.get("x"))
            url = (doc.get("place_url") or "").strip()
            name = (doc.get("place_name") or "").strip()
            # 주소·좌표·링크를 확인할 수 없는 문서는 결과에 넣지 않는다
            if not pid or pid in seen or not name or lat is None or lng is None or not url.startswith("http"):
                continue
            seen.add(pid)
            dist = int(doc["distance"]) if str(doc.get("distance") or "").isdigit() else None
            cafes.append(CafeInfo(
                source=SOURCE_KAKAO, source_id=pid, name=name,
                address=(doc.get("address_name") or "").strip() or None,
                road_address=(doc.get("road_address_name") or "").strip() or None,
                latitude=lat, longitude=lng, distance_m=dist,
                distance_basis="카카오 제공 직선거리" if dist is not None else None,
                estimated_walk_minutes=estimate_walk_minutes(dist), place_url=url,
                phone=(doc.get("phone") or "").strip() or None,
                category_name=(doc.get("category_name") or "").strip() or None,
            ))
            if len(cafes) >= params.max_results:
                break
        if result.is_end:
            break
        page += 1
    return cafes, total


def _license_cafes(dataset: GangnamLicenseDataset, params: CafeSearchInput, today: date) -> list[CafeInfo]:
    records, _ = dataset.load()
    found = []
    for rec in records:
        if rec.category not in CAFE_LICENSE_CATEGORIES or rec.latitude is None or rec.longitude is None:
            continue
        if not license_open_on(rec, today, today):
            continue
        dist = round(haversine_m(params.latitude, params.longitude, rec.latitude, rec.longitude))
        if dist <= params.radius_m:
            found.append((dist, rec))
    found.sort(key=lambda t: (t[0], t[1].name))
    return [
        CafeInfo(
            source=SOURCE_REST_FOOD, source_id=rec.source_id, name=rec.name, address=rec.jibun_address,
            road_address=rec.road_address, latitude=rec.latitude, longitude=rec.longitude, distance_m=dist,
            distance_basis="인허가 좌표(EPSG:5174→WGS84 변환)로 계산한 직선거리",
            estimated_walk_minutes=estimate_walk_minutes(dist), place_url=None, phone=rec.phone,
            category_name=f"휴게음식점 > {rec.category}",
        )
        for dist, rec in found[: params.max_results]
    ]


def create_tool(
    client: KakaoLocalClient,
    rest_food: GangnamLicenseDataset | None = None,
    *,
    today_fn: Callable[[], date] = lambda: now_kst().date(),
) -> ToolSpec:
    def run(params: CafeSearchInput) -> CafeSearchOutput:
        statuses: list[CafeSourceStatus] = []
        cafes: list[CafeInfo] = []
        total = 0
        kakao_error: ExternalAPIError | None = None
        try:
            cafes, total = _kakao_cafes(client, params)
            statuses.append(CafeSourceStatus(source=SOURCE_KAKAO, ok=True, returned=len(cafes)))
        except ExternalAPIError as exc:
            kakao_error = exc
            statuses.append(CafeSourceStatus(source=SOURCE_KAKAO, ok=False, error_code=exc.code, message=exc.message))

        if not cafes and rest_food is not None:
            try:
                cafes = _license_cafes(rest_food, params, today_fn())
                total = len(cafes)
                statuses.append(CafeSourceStatus(source=SOURCE_REST_FOOD, ok=True, returned=len(cafes),
                                                 message="카카오 결과가 없어 강남구 휴게음식점 인허가 데이터로 보조 검색 (장소 링크 없음)"))
            except ExternalAPIError as exc:
                statuses.append(CafeSourceStatus(source=SOURCE_REST_FOOD, ok=False, error_code=exc.code, message=exc.message))

        if not cafes:
            failures = [s for s in statuses if not s.ok]
            if kakao_error is not None and len(failures) < len(statuses):
                # 1순위가 실패하고 보조 출처만 0건이면 '결과 없음'으로 단정하지 않고 1순위 오류를 알린다
                raise ToolError(kakao_error.code, f"카페를 조회하지 못했습니다: {kakao_error.message} (보조 출처 결과 0건)")
            if failures and len(failures) == len(statuses):
                codes = {f.error_code for f in failures}
                code = ErrorCode.MISSING_API_KEY if codes == {ErrorCode.MISSING_API_KEY} else (
                    kakao_error.code if kakao_error else failures[0].error_code)
                raise ToolError(code, "카페를 조회하지 못했습니다: " + " / ".join(f.message or "" for f in failures))
            raise ToolError(ErrorCode.NO_RESULT, f"반경 {params.radius_m}m 안에서 카페를 찾지 못했습니다.")
        return CafeSearchOutput(
            center={"latitude": params.latitude, "longitude": params.longitude},
            radius_m=params.radius_m, total_count=total, cafes=cafes, not_provided_fields=NOT_PROVIDED_FIELDS,
            walk_time_basis=WALK_BASIS, source_status=statuses,
        )

    return ToolSpec(
        name=TOOL_NAME,
        description=DESCRIPTION,
        kind=ToolKind.EXTERNAL_API,
        providers=["카카오 로컬 API (카테고리로 장소 검색, CE7)", "서울 열린데이터광장 (강남구 휴게음식점 인허가 정보, 보조)"],
        input_model=CafeSearchInput,
        output_model=CafeSearchOutput,
        error_codes=[ErrorCode.INVALID_INPUT, ErrorCode.MISSING_API_KEY, ErrorCode.NO_RESULT, ErrorCode.TIMEOUT, ErrorCode.API_ERROR],
        func=run,
    )

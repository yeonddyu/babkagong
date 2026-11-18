"""F3004 주변 카페 검색 Tool: search_nearby_cafes.

카카오 로컬 API 카테고리 검색(CE7 카페)으로 식당 좌표 주변 카페를 거리순으로 찾는다.
카카오가 제공하지 않는 영업시간·콘센트·와이파이·혼잡도는 null 로 두고 생성하지 않는다.
"""
from __future__ import annotations

from pydantic import BaseModel, Field

from app.clients.kakao_local import CATEGORY_CAFE, MAX_PAGE, MAX_PAGE_SIZE, MAX_RADIUS_M, KakaoLocalClient
from app.core.errors import ErrorCode
from app.core.geo import to_float
from app.tools.common import ToolError, ToolKind, ToolSpec

TOOL_NAME = "search_nearby_cafes"
NOT_PROVIDED_FIELDS = ["opening_hours", "power_outlet", "wifi", "congestion"]


class CafeSearchInput(BaseModel):
    latitude: float = Field(ge=33.0, le=39.0, description="기준 위도 (예: 식당 후보의 latitude)")
    longitude: float = Field(ge=124.0, le=132.0, description="기준 경도 (예: 식당 후보의 longitude)")
    radius_m: int = Field(default=500, ge=1, le=MAX_RADIUS_M, description="검색 반경(m), 1~20000, 기본 500")
    max_results: int = Field(default=10, ge=1, le=MAX_PAGE_SIZE * MAX_PAGE, description="최대 결과 수, 기본 10")


class CafeInfo(BaseModel):
    kakao_place_id: str
    name: str
    address: str | None = Field(description="지번 주소")
    road_address: str | None
    latitude: float
    longitude: float
    distance_m: int | None = Field(description="기준 좌표로부터 거리(m, 카카오 제공)")
    place_url: str = Field(description="카카오맵 장소 상세 페이지")
    phone: str | None
    category_name: str | None
    opening_hours: None = Field(default=None, description="카카오 로컬 API 미제공 → 항상 null")
    power_outlet: None = Field(default=None, description="미제공 → 항상 null")
    wifi: None = Field(default=None, description="미제공 → 항상 null")
    congestion: None = Field(default=None, description="미제공 → 항상 null")


class CafeSearchOutput(BaseModel):
    center: dict[str, float]
    radius_m: int
    total_count: int = Field(description="카카오가 보고한 반경 내 전체 카페 수")
    cafes: list[CafeInfo]
    not_provided_fields: list[str] = Field(description="이 출처로 확인할 수 없어 null 로 둔 항목")
    source: str = "kakao_local_category_CE7"


DESCRIPTION = (
    "식사할 음식점이 정해진 뒤 그 주변에서 카공(공부·작업)할 카페를 찾아야 할 때 사용한다. "
    "음식점 후보의 latitude/longitude 를 넣으면 반경 안의 카페를 가까운 순으로 돌려준다. "
    "영업시간·콘센트·와이파이·혼잡도는 이 Tool 로 확인할 수 없어 항상 null 이다."
)


def create_tool(client: KakaoLocalClient) -> ToolSpec:
    def run(params: CafeSearchInput) -> CafeSearchOutput:
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
                cafes.append(CafeInfo(
                    kakao_place_id=pid, name=name,
                    address=(doc.get("address_name") or "").strip() or None,
                    road_address=(doc.get("road_address_name") or "").strip() or None,
                    latitude=lat, longitude=lng,
                    distance_m=int(doc["distance"]) if str(doc.get("distance") or "").isdigit() else None,
                    place_url=url,
                    phone=(doc.get("phone") or "").strip() or None,
                    category_name=(doc.get("category_name") or "").strip() or None,
                ))
                if len(cafes) >= params.max_results:
                    break
            if result.is_end:
                break
            page += 1

        if not cafes:
            raise ToolError(ErrorCode.NO_RESULT, f"반경 {params.radius_m}m 안에서 카페를 찾지 못했습니다.")
        return CafeSearchOutput(
            center={"latitude": params.latitude, "longitude": params.longitude},
            radius_m=params.radius_m, total_count=total, cafes=cafes, not_provided_fields=NOT_PROVIDED_FIELDS,
        )

    return ToolSpec(
        name=TOOL_NAME,
        description=DESCRIPTION,
        kind=ToolKind.EXTERNAL_API,
        providers=["카카오 로컬 API (카테고리로 장소 검색, CE7)"],
        input_model=CafeSearchInput,
        output_model=CafeSearchOutput,
        error_codes=[ErrorCode.INVALID_INPUT, ErrorCode.MISSING_API_KEY, ErrorCode.NO_RESULT, ErrorCode.TIMEOUT, ErrorCode.API_ERROR],
        func=run,
    )

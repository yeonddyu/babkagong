"""F3003 음식점 상세정보 조회 Tool: get_restaurant_details.

- 서울관광재단(레드테이블) 후보: 식당기본정보 + 메뉴정보(한국어) + 식당운영정보를 RSTR_ID 로 연결
- 강남구 인허가 후보: 기본정보만 반환하고 상세정보 부재 사유(DETAIL_NOT_AVAILABLE)를 구분해 표시
- 확인되지 않은 값은 null 로 둔다. 다른 출처의 식당과 임의로 매칭하지 않는다.
"""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from app.core.errors import ErrorCode, ExternalAPIError
from app.datasets.restaurants import (
    SOURCE_GANGNAM_LICENSE,
    SOURCE_REDTABLE,
    GangnamLicenseDataset,
    RedtableDetailDataset,
    RedtableRestaurantDataset,
    RestaurantRecord,
)
from app.tools.common import ToolError, ToolKind, ToolSpec

TOOL_NAME = "get_restaurant_details"

SectionStatus = Literal["found", "not_found", "unavailable", "error"]


class RestaurantDetailInput(BaseModel):
    source: Literal["seoul_tourism_redtable", "gangnam_general_restaurant_license"] = Field(
        description="search_restaurant_candidates 결과의 source 값"
    )
    source_id: str = Field(min_length=1, max_length=64, description="search_restaurant_candidates 결과의 source_id 값")


class BasicInfo(BaseModel):
    name: str
    road_address: str | None
    jibun_address: str | None
    latitude: float | None
    longitude: float | None
    phone: str | None
    category: str | None
    license_type: str | None
    business_status: str | None = None


class MenuItem(BaseModel):
    menu_id: str | None
    name: str
    price_krw: int | None = Field(description="확인된 가격. 없거나 0 이면 null")
    is_local_specialty: bool | None


class OperationInfo(BaseModel):
    business_hours: str | None
    holidays: str | None
    wifi: bool | None
    parking: bool | None
    standing_seats: int | None
    floor_seats: int | None
    reservation_method: str | None
    barrier_free: bool | None
    delivery: bool | None
    kiosk: bool | None
    mobile_payment: bool | None
    representative_menu: str | None
    homepage_url: str | None


class SectionError(BaseModel):
    section: str
    code: ErrorCode
    message: str


class DetailUnavailable(BaseModel):
    code: ErrorCode = ErrorCode.DETAIL_NOT_AVAILABLE
    message: str


class RestaurantDetailOutput(BaseModel):
    source: str
    source_id: str
    basic: BasicInfo
    detail_available: bool
    detail_unavailable: DetailUnavailable | None = Field(description="상세정보를 제공할 수 없는 출처일 때 사유")
    menus: list[MenuItem] | None = Field(description="확인된 메뉴. 확인 불가면 null, 등록된 메뉴가 없으면 []")
    menu_status: SectionStatus
    operation: OperationInfo | None = Field(description="확인된 운영정보. 확인 불가면 null")
    operation_status: SectionStatus
    section_errors: list[SectionError]
    data_fetched_at: dict[str, str | None]


DESCRIPTION = (
    "search_restaurant_candidates 로 찾은 특정 음식점의 메뉴명·가격·영업시간·휴무일·편의시설을 확인해야 할 때 사용한다. "
    "후보의 source 와 source_id 를 그대로 넣는다. 확인되지 않은 값은 null 이며, "
    "상세정보를 제공하지 않는 출처의 후보는 detail_available=false 와 그 사유를 돌려준다."
)


def _text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text if text and text.lower() not in ("null", "none") else None


def _yn(value: Any) -> bool | None:
    text = (_text(value) or "").upper()
    return {"Y": True, "N": False}.get(text)


def _int(value: Any) -> int | None:
    text = _text(value)
    if text is None:
        return None
    try:
        return int(float(text.replace(",", "")))
    except ValueError:
        return None


def _price(value: Any) -> int | None:
    price = _int(value)
    return price if price and price > 0 else None


def _basic(rec: RestaurantRecord) -> BasicInfo:
    return BasicInfo(
        name=rec.name, road_address=rec.road_address, jibun_address=rec.jibun_address,
        latitude=rec.latitude, longitude=rec.longitude, phone=rec.phone, category=rec.category,
        license_type=rec.license_type,
        business_status=rec.status_name if rec.source == SOURCE_GANGNAM_LICENSE else None,
    )


def _menu(row: dict[str, Any]) -> MenuItem | None:
    name = _text(row.get("MENU_NM"))
    if not name:
        return None
    return MenuItem(
        menu_id=_text(row.get("MENU_ID")), name=name, price_krw=_price(row.get("MENU_PRICE")),
        is_local_specialty=_yn(row.get("SPCLT_MENU_YN")),
    )


def _operation(row: dict[str, Any]) -> OperationInfo:
    return OperationInfo(
        business_hours=_text(row.get("BSNS_TM_CN")),
        holidays=_text(row.get("RESTDY_INFO_CN")),
        wifi=_yn(row.get("WIFI_OFR_YN")),
        parking=_yn(row.get("PRKG_POS_YN")),
        standing_seats=_int(row.get("PRDL_SEAT_CNT")),
        floor_seats=_int(row.get("SEAT_CNT")),
        reservation_method=_text(row.get("RSRV_MTHD_NM")),
        barrier_free=_yn(row.get("DSBR_CVNTL_YN")),
        delivery=_yn(row.get("DELV_SRVIC_YN")),
        kiosk=_yn(row.get("KIOSK_YN")),
        mobile_payment=_yn(row.get("MB_PMAMT_YN")),
        representative_menu=_text(row.get("REPRSNT_MENU_NM")),
        homepage_url=_text(row.get("HMPG_URL")),
    )


def _find(records: list[RestaurantRecord], source_id: str) -> RestaurantRecord | None:
    return next((r for r in records if r.source_id == source_id), None)


def create_tool(
    redtable_restaurants: RedtableRestaurantDataset,
    redtable_details: RedtableDetailDataset,
    gangnam_license: GangnamLicenseDataset,
) -> ToolSpec:
    def run_redtable(source_id: str) -> RestaurantDetailOutput:
        records, meta = redtable_restaurants.load()
        rec = _find(records, source_id)
        if rec is None:
            raise ToolError(ErrorCode.NO_RESULT, f"서울관광재단 식당 ID {source_id} 를 서비스 지역(강남·역삼) 데이터에서 찾지 못했습니다.")

        fetched: dict[str, str | None] = {"basic": meta.get("fetched_at"), "menu": None, "operation": None}
        errors: list[SectionError] = []

        menus: list[MenuItem] | None = None
        menu_status: SectionStatus
        try:
            by_id, menu_meta = redtable_details.menus_by_id()
            fetched["menu"] = menu_meta.get("fetched_at")
            rows = by_id.get(source_id)
            if rows:
                menus = []
                seen: set[tuple[str, int | None]] = set()
                for m in (_menu(r) for r in rows):
                    if m and (m.name, m.price_krw) not in seen:  # 원본의 중복 행 제거
                        seen.add((m.name, m.price_krw))
                        menus.append(m)
                menu_status = "found" if menus else "not_found"
            else:
                menus, menu_status = [], "not_found"
        except ExternalAPIError as exc:
            menu_status = "error"
            errors.append(SectionError(section="menu", code=exc.code, message=exc.message))

        operation: OperationInfo | None = None
        operation_status: SectionStatus
        try:
            by_id, op_meta = redtable_details.operations_by_id()
            fetched["operation"] = op_meta.get("fetched_at")
            rows = by_id.get(source_id)
            if rows:
                operation, operation_status = _operation(rows[0]), "found"
            else:
                operation_status = "not_found"
        except ExternalAPIError as exc:
            operation_status = "error"
            errors.append(SectionError(section="operation", code=exc.code, message=exc.message))

        return RestaurantDetailOutput(
            source=SOURCE_REDTABLE, source_id=source_id, basic=_basic(rec), detail_available=True,
            detail_unavailable=None, menus=menus, menu_status=menu_status, operation=operation,
            operation_status=operation_status, section_errors=errors, data_fetched_at=fetched,
        )

    def run_license(source_id: str) -> RestaurantDetailOutput:
        records, meta = gangnam_license.load()
        rec = _find(records, source_id)
        if rec is None:
            raise ToolError(ErrorCode.NO_RESULT, f"강남구 인허가 관리번호 {source_id} 를 서비스 지역 데이터에서 찾지 못했습니다.")
        return RestaurantDetailOutput(
            source=SOURCE_GANGNAM_LICENSE, source_id=source_id, basic=_basic(rec), detail_available=False,
            detail_unavailable=DetailUnavailable(message=(
                "강남구 일반음식점 인허가 데이터는 메뉴·가격·영업시간을 제공하지 않습니다. "
                "서울관광재단 데이터와 공통 식별자가 없어 다른 식당의 상세정보로 대체하지 않았습니다."
            )),
            menus=None, menu_status="unavailable", operation=None, operation_status="unavailable",
            section_errors=[], data_fetched_at={"basic": meta.get("fetched_at"), "menu": None, "operation": None},
        )

    def run(params: RestaurantDetailInput) -> RestaurantDetailOutput:
        source_id = params.source_id.strip()
        if params.source == SOURCE_REDTABLE:
            return run_redtable(source_id)
        return run_license(source_id)

    return ToolSpec(
        name=TOOL_NAME,
        description=DESCRIPTION,
        kind=ToolKind.EXTERNAL_API,
        providers=["서울관광재단 음식관광 API (식당기본정보·메뉴정보 한국어·식당운영정보)", "서울 열린데이터광장 (강남구 일반음식점 인허가 정보)"],
        input_model=RestaurantDetailInput,
        output_model=RestaurantDetailOutput,
        error_codes=[ErrorCode.INVALID_INPUT, ErrorCode.MISSING_API_KEY, ErrorCode.NO_RESULT, ErrorCode.TIMEOUT,
                     ErrorCode.API_ERROR, ErrorCode.DETAIL_NOT_AVAILABLE],
        func=run,
    )

"""음식점 데이터셋 (외부 API → 서비스 지역으로 거른 정규화 레코드).

출처별 식별자는 출처 안에서만 유효하다. 서로 다른 출처의 ID 를 같은 것으로 취급하지 않는다.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any

from app.clients.redtable import ENDPOINT_RESTAURANT, RedtableClient
from app.clients.seoul_opendata import SERVICE_GANGNAM_GENERAL_RESTAURANT, SERVICE_GANGNAM_REST_FOOD, SeoulOpenDataClient
from app.core.geo import LOCALDATA_CRS, tm_to_wgs84, to_float, within_any_station
from app.datasets.cache import JsonCache

SOURCE_REDTABLE = "seoul_tourism_redtable"  # 서울관광재단 음식관광 API 식당기본정보
SOURCE_GANGNAM_LICENSE = "gangnam_general_restaurant_license"  # 강남구 일반음식점 인허가 정보
SOURCE_GANGNAM_REST_FOOD = "gangnam_rest_food_license"  # 강남구 휴게음식점 인허가 정보 (카페류)

AREA_CACHE_RADIUS_M = 1500  # 캐시에 보관할 반경 (두 역 중 하나에서)


@dataclass
class RestaurantRecord:
    source: str
    source_id: str
    name: str
    road_address: str | None
    jibun_address: str | None
    latitude: float | None
    longitude: float | None
    coordinate_note: str | None
    category: str | None  # 출처 원본 분류값
    phone: str | None = None
    license_type: str | None = None
    permit_date: str | None = None  # YYYY-MM-DD (인허가 데이터만)
    closed_date: str | None = None
    status_code: str | None = None
    status_name: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return self.__dict__.copy()

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "RestaurantRecord":
        return cls(**data)


def _text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _ymd(value: Any) -> str | None:
    text = _text(value)
    if not text:
        return None
    digits = text.replace("-", "")[:8]
    if len(digits) != 8 or not digits.isdigit():
        return None
    return f"{digits[:4]}-{digits[4:6]}-{digits[6:]}"


def _records(owner: Any, payload: dict[str, Any]) -> list[RestaurantRecord]:
    """같은 캐시 payload 에서 만든 레코드 목록을 재사용한다 (매 호출 변환 비용 제거)."""
    memo = getattr(owner, "_records_memo", None)
    if memo is not None and memo[0] is payload:
        return memo[1]
    records = [RestaurantRecord.from_dict(d) for d in payload["data"]]
    owner._records_memo = (payload, records)
    return records


# ---------------------------------------------------------------- 레드테이블
def normalize_redtable_restaurant(row: dict[str, Any]) -> RestaurantRecord | None:
    rid = _text(row.get("RSTR_ID"))
    name = _text(row.get("RSTR_NM"))
    if not rid or not name:
        return None
    lat, lng = to_float(row.get("RSTR_LA")), to_float(row.get("RSTR_LO"))
    return RestaurantRecord(
        source=SOURCE_REDTABLE,
        source_id=rid,
        name=name,
        road_address=_text(row.get("RSTR_RDNMADR")),
        jibun_address=_text(row.get("RSTR_LNNO_ADRES")),
        latitude=lat,
        longitude=lng,
        coordinate_note="출처 제공 WGS84 좌표" if lat is not None and lng is not None else None,
        category=_text(row.get("BSNS_STATM_BZCND_NM")),
        phone=_text(row.get("RSTR_TELNO")),
        license_type=_text(row.get("BSNS_LCNC_NM")),
        extra={"intro": _text(row.get("RSTR_INTRCN_CONT"))},
    )


class RedtableRestaurantDataset:
    CACHE_NAME = "redtable_rstr_area"

    def __init__(self, client: RedtableClient, cache: JsonCache):
        self.client = client
        self.cache = cache

    def _build(self):
        kept: list[dict[str, Any]] = []
        scanned = 0
        total = 0
        for page in self.client.iter_all(ENDPOINT_RESTAURANT):
            total = page.total_count or total
            for row in page.rows:
                scanned += 1
                rec = normalize_redtable_restaurant(row)
                if rec and rec.latitude is not None and within_any_station(rec.latitude, rec.longitude, AREA_CACHE_RADIUS_M):
                    kept.append(rec.to_dict())
        return kept, {"source_total_count": total, "scanned_rows": scanned}

    def load(self) -> tuple[list[RestaurantRecord], dict[str, Any]]:
        payload = self.cache.get_or_build(self.CACHE_NAME, self._build)
        meta = {k: v for k, v in payload.items() if k != "data"}
        return _records(self, payload), meta


# ---------------------------------------------------------- 강남구 인허가
def normalize_gangnam_license(
    row: dict[str, Any], *, source: str = SOURCE_GANGNAM_LICENSE, license_type: str = "일반음식점"
) -> RestaurantRecord | None:
    mgtno = _text(row.get("MGTNO"))
    name = _text(row.get("BPLCNM"))
    if not mgtno or not name:
        return None
    x, y = to_float(row.get("X")), to_float(row.get("Y"))
    lat = lng = None
    note = None
    if x is not None and y is not None:
        lat, lng = tm_to_wgs84(x, y)
        note = f"출처 TM 좌표({LOCALDATA_CRS})를 WGS84 로 변환"
    return RestaurantRecord(
        source=source,
        source_id=mgtno,
        name=name,
        road_address=_text(row.get("RDNWHLADDR")),
        jibun_address=_text(row.get("SITEWHLADDR")),
        latitude=lat,
        longitude=lng,
        coordinate_note=note,
        category=_text(row.get("UPTAENM")),
        phone=_text(row.get("SITETEL")),
        license_type=license_type,
        permit_date=_ymd(row.get("APVPERMYMD")),
        closed_date=_ymd(row.get("DCBYMD")),
        status_code=_text(row.get("TRDSTATEGBN")),
        status_name=_text(row.get("TRDSTATENM")),
        extra={"updated_at": _text(row.get("UPDATEDT")), "detail_status": _text(row.get("DTLSTATENM"))},
    )


def license_open_on(rec: RestaurantRecord, day: date, today: date) -> bool:
    """인허가일·폐업일·현재 영업상태로 해당 일자 영업 여부를 판정한다.

    휴업 이력은 데이터에 없으므로 과거 일자의 휴업 여부는 판정하지 않는다.
    """
    if rec.permit_date and rec.permit_date > day.isoformat():
        return False
    if rec.closed_date:
        return rec.closed_date > day.isoformat()
    if day >= today:
        return rec.status_code == "01"  # 01: 영업/정상
    # 과거 일자: 폐업일이 없는데 현재 폐업(03)·취소(04 등)면 종료 시점을 알 수 없어 제외
    return rec.status_code in ("01", "02")


class GangnamLicenseDataset:
    """강남구 인허가 데이터셋. 기본은 일반음식점, rest_food() 는 휴게음식점(카페류)."""

    CACHE_NAME = "gangnam_license_area"

    def __init__(
        self,
        client: SeoulOpenDataClient,
        cache: JsonCache,
        *,
        service: str = SERVICE_GANGNAM_GENERAL_RESTAURANT,
        cache_name: str | None = None,
        source: str = SOURCE_GANGNAM_LICENSE,
        license_type: str = "일반음식점",
    ):
        self.client = client
        self.cache = cache
        self.service = service
        self.cache_name = cache_name or self.CACHE_NAME
        self.source = source
        self.license_type = license_type

    @classmethod
    def rest_food(cls, client: SeoulOpenDataClient, cache: JsonCache) -> "GangnamLicenseDataset":
        return cls(client, cache, service=SERVICE_GANGNAM_REST_FOOD, cache_name="gangnam_rest_food_area",
                   source=SOURCE_GANGNAM_REST_FOOD, license_type="휴게음식점")

    def _build(self):
        page = self.client.fetch_all(self.service)
        kept = []
        latest_update = None
        for row in page.rows:
            rec = normalize_gangnam_license(row, source=self.source, license_type=self.license_type)
            if rec is None:
                continue
            upd = rec.extra.get("updated_at")
            if upd and (latest_update is None or upd > latest_update):
                latest_update = upd
            if rec.latitude is not None and within_any_station(rec.latitude, rec.longitude, AREA_CACHE_RADIUS_M):
                kept.append(rec.to_dict())
        return kept, {"source_total_count": page.total_count, "scanned_rows": len(page.rows), "data_updated_at": latest_update}

    def load(self) -> tuple[list[RestaurantRecord], dict[str, Any]]:
        payload = self.cache.get_or_build(self.cache_name, self._build)
        meta = {k: v for k, v in payload.items() if k != "data"}
        return _records(self, payload), meta


# ------------------------------------------------ 레드테이블 메뉴·운영정보 (F3003)
class RedtableDetailDataset:
    """메뉴정보(한국어)·식당운영정보를 서비스 지역 식당 ID 로 걸러 캐시한다.

    두 API 모두 식당 ID 필터가 없어 전체 페이지를 순회한다.
    같은 출처(레드테이블)의 RSTR_ID 로만 연결한다.
    """

    MENU_CACHE = "redtable_menu_area"
    OPERATION_CACHE = "redtable_oprt_area"

    def __init__(self, client: RedtableClient, cache: JsonCache, restaurants: RedtableRestaurantDataset):
        self.client = client
        self.cache = cache
        self.restaurants = restaurants

    def _area_ids(self) -> set[str]:
        records, _ = self.restaurants.load()
        return {r.source_id for r in records}

    def _collect(self, endpoint: str):
        ids = self._area_ids()
        grouped: dict[str, list[dict[str, Any]]] = {}
        scanned = 0
        total = 0
        for page in self.client.iter_all(endpoint):
            total = page.total_count or total
            for row in page.rows:
                scanned += 1
                rid = _text(row.get("RSTR_ID"))
                if rid in ids:
                    grouped.setdefault(rid, []).append(row)
        return grouped, {"source_total_count": total, "scanned_rows": scanned}

    def menus_by_id(self) -> tuple[dict[str, list[dict[str, Any]]], dict[str, Any]]:
        from app.clients.redtable import ENDPOINT_MENU_KOREAN

        payload = self.cache.get_or_build(self.MENU_CACHE, lambda: self._collect(ENDPOINT_MENU_KOREAN))
        return payload["data"], {k: v for k, v in payload.items() if k != "data"}

    def operations_by_id(self) -> tuple[dict[str, list[dict[str, Any]]], dict[str, Any]]:
        from app.clients.redtable import ENDPOINT_OPERATION

        payload = self.cache.get_or_build(self.OPERATION_CACHE, lambda: self._collect(ENDPOINT_OPERATION))
        return payload["data"], {k: v for k, v in payload.items() if k != "data"}

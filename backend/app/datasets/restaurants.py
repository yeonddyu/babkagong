"""음식점 데이터셋 (외부 API → 서비스 지역으로 거른 정규화 레코드).

출처별 식별자는 출처 안에서만 유효하다. 서로 다른 출처의 ID 를 같은 것으로 취급하지 않는다.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any

from app.clients.redtable import ENDPOINT_RESTAURANT, RedtableClient
from app.clients.seoul_opendata import SERVICE_GANGNAM_GENERAL_RESTAURANT, SERVICE_GANGNAM_REST_FOOD, SeoulOpenDataClient
from app.core.geo import LOCALDATA_CRS, tm_to_wgs84, to_float
from app.datasets.cache import JsonCache
from app.datasets.sqlite_store import SqliteRows

SOURCE_REDTABLE = "seoul_tourism_redtable"  # 서울관광재단 음식관광 API 식당기본정보
SOURCE_GANGNAM_LICENSE = "gangnam_general_restaurant_license"  # 강남구 일반음식점 인허가 정보
SOURCE_GANGNAM_REST_FOOD = "gangnam_rest_food_license"  # 강남구 휴게음식점 인허가 정보 (카페류)



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
    """서울관광재단 식당기본정보 — 서울 전역을 SQLite 에 보관하고 좌표 반경으로 조회한다."""

    STORE_NAME = "redtable_rstr_seoul"

    def __init__(self, client: RedtableClient, cache: JsonCache):
        self.client = client
        self.store = SqliteRows(cache, self.STORE_NAME)

    def _build(self):
        stats = {"scanned_rows": 0, "source_total_count": 0, "kept": 0}

        def rows():
            for page in self.client.iter_all(ENDPOINT_RESTAURANT):
                stats["source_total_count"] = page.total_count or stats["source_total_count"]
                for row in page.rows:
                    stats["scanned_rows"] += 1
                    rec = normalize_redtable_restaurant(row)
                    if rec and rec.latitude is not None and rec.longitude is not None:
                        stats["kept"] += 1
                        yield rec.source_id, rec.latitude, rec.longitude, rec.to_dict()

        return rows(), lambda: dict(stats)

    def ensure(self) -> dict[str, Any]:
        """데이터가 없거나 만료면 전체를 다시 받는다 (외부 API 오류는 ExternalAPIError 로 전파)."""
        return self.store.ensure(self._build)

    def near(self, lat: float, lng: float, radius_m: float) -> list[tuple[float, RestaurantRecord]]:
        self.ensure()
        return [(d, RestaurantRecord.from_dict(data)) for d, data in self.store.near(lat, lng, radius_m)]

    def count_near(self, lat: float, lng: float, radius_m: float) -> int:
        self.ensure()
        return self.store.count_near(lat, lng, radius_m)

    def get(self, source_id: str) -> RestaurantRecord | None:
        self.ensure()
        rows = self.store.by_key(str(source_id))
        return RestaurantRecord.from_dict(rows[0]) if rows else None


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

    CACHE_NAME = "gangnam_license_all"

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
        return cls(client, cache, service=SERVICE_GANGNAM_REST_FOOD, cache_name="gangnam_rest_food_all",
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
            if rec.latitude is not None:  # 강남구 전체 (서울 전역 역 확장 후 강남구 안의 다른 역에서도 쓰도록)
                kept.append(rec.to_dict())
        return kept, {"source_total_count": page.total_count, "scanned_rows": len(page.rows), "data_updated_at": latest_update}

    def load(self) -> tuple[list[RestaurantRecord], dict[str, Any]]:
        payload = self.cache.get_or_build(self.cache_name, self._build)
        meta = {k: v for k, v in payload.items() if k != "data"}
        return _records(self, payload), meta


# ------------------------------------------------ 레드테이블 메뉴·운영정보 (F3003)
MENU_FIELDS = ("MENU_ID", "MENU_NM", "MENU_PRICE", "SPCLT_MENU_YN")
OPERATION_FIELDS = ("BSNS_TM_CN", "RESTDY_INFO_CN", "WIFI_OFR_YN", "PRKG_POS_YN", "PRDL_SEAT_CNT", "SEAT_CNT", "RSRV_MTHD_NM",
                    "DSBR_CVNTL_YN", "DELV_SRVIC_YN", "KIOSK_YN", "MB_PMAMT_YN", "REPRSNT_MENU_NM", "HMPG_URL")


class RedtableDetailDataset:
    """메뉴정보(한국어)·식당운영정보 — 서울 전역을 식당 ID(RSTR_ID)별로 SQLite 에 보관한다.

    두 API 모두 식당 ID 필터가 없어 전체 페이지를 순회한다. 같은 출처(레드테이블)의 RSTR_ID 로만 연결한다.
    상세 Tool 이 쓰는 필드만 저장한다 (MENU_FIELDS, OPERATION_FIELDS).
    """

    def __init__(self, client: RedtableClient, cache: JsonCache, restaurants: RedtableRestaurantDataset | None = None):
        self.client = client
        self.menu_store = SqliteRows(cache, "redtable_menu_seoul")
        self.operation_store = SqliteRows(cache, "redtable_oprt_seoul")

    def _builder(self, endpoint: str, fields: tuple[str, ...]):
        def build():
            stats = {"scanned_rows": 0, "source_total_count": 0}

            def rows():
                for page in self.client.iter_all(endpoint):
                    stats["source_total_count"] = page.total_count or stats["source_total_count"]
                    for row in page.rows:
                        stats["scanned_rows"] += 1
                        rid = _text(row.get("RSTR_ID"))
                        if rid:
                            yield rid, None, None, {k: row.get(k) for k in fields}

            return rows(), lambda: dict(stats)
        return build

    def ensure_menus(self) -> dict[str, Any]:
        from app.clients.redtable import ENDPOINT_MENU_KOREAN

        return self.menu_store.ensure(self._builder(ENDPOINT_MENU_KOREAN, MENU_FIELDS))

    def ensure_operations(self) -> dict[str, Any]:
        from app.clients.redtable import ENDPOINT_OPERATION

        return self.operation_store.ensure(self._builder(ENDPOINT_OPERATION, OPERATION_FIELDS))

    def menus_for(self, source_id: str) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        meta = self.ensure_menus()
        return self.menu_store.by_key(str(source_id)), meta

    def operations_for(self, source_id: str) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        meta = self.ensure_operations()
        return self.operation_store.by_key(str(source_id)), meta

    def ids_with_menu(self, ids) -> set[str]:
        self.ensure_menus()
        return self.menu_store.keys_present(str(i) for i in ids)

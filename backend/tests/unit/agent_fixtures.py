"""Agent 테스트용 가짜 외부 API 데이터 (Mock). 실제 API 응답이 아니다."""
from __future__ import annotations

from datetime import date, datetime

from app.clients.seoul_opendata import SERVICE_GANGNAM_GENERAL_RESTAURANT, SERVICE_GANGNAM_REST_FOOD
from app.datasets.cache import KST
from app.tools.catalog import build_default_registry
from tests.fakes import FakeSession, json_response, redtable_pages, seoul_rows
from tests.unit.test_f3002_restaurant_candidates import lic_row, rt_row

TODAY = date(2026, 11, 19)  # 목요일
NOW = datetime(2026, 11, 19, 10, 30, tzinfo=KST)

RSTR = "seoul.openapi.redtable.global/api/rstr"
OPRT = "seoul.openapi.redtable.global/api/rstr/oprt"
MENU = "seoul.openapi.redtable.global/api/menu/korean"
SEOUL_GENERAL = "LOCALDATA_072404_GN"
SEOUL_REST = "LOCALDATA_072405_GN"
KAKAO = "dapi.kakao.com"
KMA = "apis.data.go.kr/1360000"

# 강남역(37.497952, 127.027619) 주변. 번호가 작을수록 가까움.
GANGNAM = [
    rt_row(1, "김치찌개집", 37.4981, 127.0277),            # 한식, 9천원 메뉴, 영업 11~21
    rt_row(2, "스시하우스", 37.4983, 127.0279, cat="일식"),  # 일식, 2만원대
    rt_row(3, "가격미상 국밥", 37.4985, 127.0281),         # 메뉴 없음
    rt_row(4, "일요일휴무 백반", 37.4987, 127.0283),       # 휴무 일요일
    rt_row(5, "저녁만 고기집", 37.4989, 127.0285),         # 17:00~23:00
    rt_row(6, "라멘가게", 37.4991, 127.0287, cat="일식"),    # 1만2천 라멘
    rt_row(7, "냉면명가", 37.4993, 127.0289),              # 냉면 1만1천
    rt_row(8, "칼국수집", 37.4995, 127.0291),              # 칼국수 9천
]
YEOKSAM = [rt_row(21, "역삼 백반", 37.5008, 127.0366)]

MENUS = [
    (1, "김치찌개", 9000), (1, "제육볶음", 11000),
    (2, "모둠초밥", 22000), (2, "특초밥", 30000),
    (4, "백반정식", 8000),
    (5, "삼겹살", 16000),
    (6, "돈코츠라멘", 12000),
    (7, "물냉면", 11000),
    (8, "바지락칼국수", 9000),
    (21, "백반", 8500),
]
OPRT_ROWS = [
    {"RSTR_ID": 1, "BSNS_TM_CN": "매일 11:00~21:00", "RESTDY_INFO_CN": "연중무휴", "WIFI_OFR_YN": "Y"},
    {"RSTR_ID": 2, "BSNS_TM_CN": "평일 11:30~22:00, 주말 12:00~21:00"},
    {"RSTR_ID": 4, "BSNS_TM_CN": "매일 08:00~20:00", "RESTDY_INFO_CN": "일요일"},
    {"RSTR_ID": 5, "BSNS_TM_CN": "매일 17:00~23:00"},
    {"RSTR_ID": 6, "BSNS_TM_CN": "매일 11:00~22:00"},
    {"RSTR_ID": 21, "BSNS_TM_CN": "매일 10:00~21:00"},
]


def menu_rows():
    return [{"MENU_ID": n, "MENU_NM": name, "MENU_PRICE": price, "RSTR_ID": rid}
            for n, (rid, name, price) in enumerate(MENUS, start=1)]


def kakao_handler(fail=False, empty=False):
    def handler(url, params, headers):
        if fail:
            from tests.fakes import FakeResponse
            return FakeResponse(500, "error")
        lat, lng = float(params["y"]), float(params["x"])
        docs = [] if empty else [
            {"id": f"{int(lat * 1e4)}{i}", "place_name": f"카페{i}", "address_name": "서울 강남구 역삼동",
             "road_address_name": "서울 강남구 테헤란로", "x": f"{lng + 0.0003 * i:.6f}", "y": f"{lat:.6f}",
             "place_url": f"http://place.map.kakao.com/{i}", "distance": str(30 * i), "phone": "", "category_name": "음식점 > 카페"}
            for i in range(1, 4)]
        return json_response({"meta": {"total_count": len(docs), "pageable_count": len(docs), "is_end": True}, "documents": docs})

    return handler


def kma_handler(tmp="12", pop="20", pty="0"):
    def handler(url, params, headers):
        fd, ft = "20261119", "1200"
        items = [{"category": k, "fcstDate": fd, "fcstTime": ft, "fcstValue": v}
                 for k, v in {"TMP": tmp, "POP": pop, "PTY": pty, "SKY": "1", "PCP": "강수없음", "REH": "50", "WSD": "2"}.items()]
        # 다른 날짜(내일)도 일부 제공
        items += [{"category": k, "fcstDate": "20261120", "fcstTime": ft, "fcstValue": v} for k, v in {"TMP": tmp, "POP": pop, "PTY": pty}.items()]
        return json_response({"response": {"header": {"resultCode": "00"}, "body": {"items": {"item": items}, "totalCount": len(items)}}})

    return handler


def make_session(*, kakao=None, kma=None, rt_rows=None, menus=None):
    return (
        FakeSession()
        .route(RSTR, redtable_pages(rt_rows if rt_rows is not None else GANGNAM + YEOKSAM, page_size=50))
        .route(OPRT, redtable_pages(OPRT_ROWS, page_size=50))
        .route(MENU, redtable_pages(menus if menus is not None else menu_rows(), page_size=50))
        .route(SEOUL_GENERAL, seoul_rows(SERVICE_GANGNAM_GENERAL_RESTAURANT, [lic_row("3220000-101-2020-09999", "인허가 식당", 37.4979, 127.0274)]))
        .route(SEOUL_REST, seoul_rows(SERVICE_GANGNAM_REST_FOOD, []))
        .route(KAKAO, kakao or kakao_handler())
        .route(KMA, kma or kma_handler())
    )


def make_registry(make_settings, session, **keys):
    from dataclasses import replace

    settings = replace(make_settings(**{k: v for k, v in keys.items() if k in ("redtable", "seoul", "kakao")}),
                       kma_api_key=keys.get("kma", "test-kma"))
    return build_default_registry(settings, session=session, today_fn=lambda: TODAY, now_fn=lambda: NOW)

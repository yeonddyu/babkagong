"""F3003 음식점 상세정보 조회 Tool - Mock 단위 테스트 (외부 호출 없음)."""
from __future__ import annotations

from datetime import date

import pytest

from app.clients.seoul_opendata import SERVICE_GANGNAM_GENERAL_RESTAURANT
from app.tools.catalog import build_default_registry
from tests.fakes import FakeSession, raise_timeout, redtable_pages, seoul_rows
from tests.unit.test_f3002_restaurant_candidates import LIC_ROWS, RT_ROWS

TOOL = "get_restaurant_details"
RSTR = "seoul.openapi.redtable.global/api/rstr"
OPRT = "seoul.openapi.redtable.global/api/rstr/oprt"
MENU = "seoul.openapi.redtable.global/api/menu/korean"
SEOUL = "openapi.seoul.go.kr"

MENU_ROWS = [
    {"MENU_ID": 1, "MENU_NM": "김치찌개", "MENU_PRICE": 9000, "SPCLT_MENU_YN": "N", "RSTR_ID": 101, "RSTR_NM": "강남 김치찌개"},
    {"MENU_ID": 2, "MENU_NM": "계란말이", "MENU_PRICE": None, "SPCLT_MENU_YN": None, "RSTR_ID": 101, "RSTR_NM": "강남 김치찌개"},
    {"MENU_ID": 3, "MENU_NM": "공기밥", "MENU_PRICE": 0, "SPCLT_MENU_YN": "N", "RSTR_ID": 101, "RSTR_NM": "강남 김치찌개"},
    {"MENU_ID": 9, "MENU_NM": "다른지역 메뉴", "MENU_PRICE": 5000, "RSTR_ID": 999, "RSTR_NM": "서울 다른 식당"},
]
OPRT_ROWS = [
    {"RSTR_ID": 101, "RSTR_NM": "강남 김치찌개", "BSNS_TM_CN": "매일 11:00~22:00", "RESTDY_INFO_CN": "일요일",
     "WIFI_OFR_YN": "Y", "PRKG_POS_YN": "N", "SEAT_CNT": "20", "PRDL_SEAT_CNT": None, "RSRV_MTHD_NM": None,
     "DSBR_CVNTL_YN": None, "DELV_SRVIC_YN": "", "KIOSK_YN": "N", "MB_PMAMT_YN": None, "REPRSNT_MENU_NM": None, "HMPG_URL": None},
]


def session(menu=MENU_ROWS, oprt=OPRT_ROWS, menu_handler=None):
    return (
        FakeSession()
        .route(RSTR, redtable_pages(RT_ROWS))
        .route(MENU, menu_handler or redtable_pages(menu))
        .route(OPRT, redtable_pages(oprt))
        .route(SEOUL, seoul_rows(SERVICE_GANGNAM_GENERAL_RESTAURANT, LIC_ROWS))
    )


def registry(make_settings, sess, **kw):
    return build_default_registry(make_settings(**kw), session=sess, today_fn=lambda: date(2026, 11, 18))


def ok_data(result):
    assert result["ok"] is True, result
    return result["data"]


def fail_code(result):
    assert result["ok"] is False and result["data"] is None, result
    return result["error"]["code"]


def test_registered_with_schema(make_settings):
    desc = {d["name"]: d for d in registry(make_settings, FakeSession()).describe()}[TOOL]
    assert desc["kind"] == "external_api"
    assert set(desc["input_schema"]["required"]) == {"source", "source_id"}
    assert "DETAIL_NOT_AVAILABLE" in desc["error_codes"]


def test_candidate_id_flows_into_details(make_settings):
    """F3002 결과의 source/source_id 를 그대로 F3003 에 넘겨 조회가 이어진다."""
    reg = registry(make_settings, session())
    cands = ok_data(reg.invoke("search_restaurant_candidates", {"area": "강남역"}))["candidates"]
    first = next(c for c in cands if c["source"] == "seoul_tourism_redtable")
    data = ok_data(reg.invoke(TOOL, {"source": first["source"], "source_id": first["source_id"]}))
    assert data["source_id"] == first["source_id"] == "101"
    assert data["basic"]["name"] == first["name"]
    assert data["detail_available"] is True and data["detail_unavailable"] is None


def test_redtable_details_with_missing_fields_stay_null(make_settings):
    data = ok_data(registry(make_settings, session()).invoke(TOOL, {"source": "seoul_tourism_redtable", "source_id": "101"}))
    assert data["menu_status"] == "found"
    menus = {m["name"]: m for m in data["menus"]}
    assert set(menus) == {"김치찌개", "계란말이", "공기밥"}  # 다른 식당 메뉴는 섞이지 않음
    assert menus["김치찌개"]["price_krw"] == 9000
    assert menus["계란말이"]["price_krw"] is None  # 가격 없음 → null
    assert menus["공기밥"]["price_krw"] is None  # 0 → 미확인
    assert menus["계란말이"]["is_local_specialty"] is None
    op = data["operation"]
    assert data["operation_status"] == "found"
    assert op["business_hours"] == "매일 11:00~22:00" and op["holidays"] == "일요일"
    assert op["wifi"] is True and op["parking"] is False and op["floor_seats"] == 20
    # 응답에 없거나 빈 값은 임의로 채우지 않음
    for key in ("standing_seats", "reservation_method", "barrier_free", "delivery", "mobile_payment", "representative_menu", "homepage_url"):
        assert op[key] is None, key


def test_redtable_no_menu_no_operation(make_settings):
    data = ok_data(registry(make_settings, session()).invoke(TOOL, {"source": "seoul_tourism_redtable", "source_id": "102"}))
    assert data["menus"] == [] and data["menu_status"] == "not_found"
    assert data["operation"] is None and data["operation_status"] == "not_found"


def test_license_candidate_is_not_matched_to_other_source(make_settings):
    sess = session()
    mgtno = "3220000-101-2020-00001"  # 레드테이블 '강남 김치찌개' 와 이름·위치가 같은 인허가 행
    data = ok_data(registry(make_settings, sess).invoke(TOOL, {"source": "gangnam_general_restaurant_license", "source_id": mgtno}))
    assert data["detail_available"] is False
    assert data["detail_unavailable"]["code"] == "DETAIL_NOT_AVAILABLE"
    assert data["basic"]["name"] == "강남김치찌개"
    assert data["basic"]["business_status"] == "영업/정상"
    assert data["menus"] is None and data["operation"] is None
    assert data["menu_status"] == data["operation_status"] == "unavailable"
    assert not any("redtable" in c["url"] for c in sess.calls)  # 다른 출처를 조회해 매칭하지 않음


def test_unknown_id_no_result(make_settings):
    assert fail_code(registry(make_settings, session()).invoke(TOOL, {"source": "seoul_tourism_redtable", "source_id": "999"})) == "NO_RESULT"
    assert fail_code(registry(make_settings, session()).invoke(TOOL, {"source": "gangnam_general_restaurant_license", "source_id": "x"})) == "NO_RESULT"


@pytest.mark.parametrize("args", [{}, {"source": "seoul_tourism_redtable"}, {"source": "kakao", "source_id": "1"}, {"source": "seoul_tourism_redtable", "source_id": ""}])
def test_invalid_input(make_settings, args):
    sess = session()
    assert fail_code(registry(make_settings, sess).invoke(TOOL, args)) == "INVALID_INPUT"
    assert sess.calls == []


def test_missing_api_key(make_settings):
    sess = session()
    reg = registry(make_settings, sess, redtable=None, seoul=None)
    assert fail_code(reg.invoke(TOOL, {"source": "seoul_tourism_redtable", "source_id": "101"})) == "MISSING_API_KEY"
    assert fail_code(reg.invoke(TOOL, {"source": "gangnam_general_restaurant_license", "source_id": "x"})) == "MISSING_API_KEY"
    assert sess.calls == []


def test_basic_timeout(make_settings):
    sess = FakeSession().route(RSTR, raise_timeout)
    assert fail_code(registry(make_settings, sess).invoke(TOOL, {"source": "seoul_tourism_redtable", "source_id": "101"})) == "TIMEOUT"


def test_menu_api_failure_is_isolated(make_settings):
    data = ok_data(registry(make_settings, session(menu_handler=raise_timeout)).invoke(
        TOOL, {"source": "seoul_tourism_redtable", "source_id": "101"}))
    assert data["menus"] is None and data["menu_status"] == "error"
    assert data["section_errors"] == [{"section": "menu", "code": "TIMEOUT", "message": data["section_errors"][0]["message"]}]
    assert data["operation_status"] == "found"  # 운영정보는 정상 반환


def test_duplicate_menu_rows_deduplicated(make_settings):
    dup = MENU_ROWS[:1] * 3 + MENU_ROWS[1:]
    data = ok_data(registry(make_settings, session(menu=dup)).invoke(TOOL, {"source": "seoul_tourism_redtable", "source_id": "101"}))
    assert [m["name"] for m in data["menus"]].count("김치찌개") == 1

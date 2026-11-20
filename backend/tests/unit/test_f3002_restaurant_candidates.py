"""F3002 음식점 후보 조회 Tool - Mock 단위 테스트 (외부 호출 없음)."""
from __future__ import annotations

from datetime import date

import pytest
from pyproj import Transformer

from app.clients.seoul_opendata import SERVICE_GANGNAM_GENERAL_RESTAURANT
from app.tools.catalog import build_default_registry
from tests.fakes import (
    FakeResponse,
    FakeSession,
    json_response,
    raise_connection_error,
    raise_timeout,
    redtable_pages,
    seoul_rows,
)

TOOL = "search_restaurant_candidates"
REDTABLE = "seoul.openapi.redtable.global/api/rstr"
SEOUL = "openapi.seoul.go.kr"
TODAY = date(2026, 11, 18)

_to_tm = Transformer.from_crs("EPSG:4326", "EPSG:5174", always_xy=True)


def tm(lat, lng):
    x, y = _to_tm.transform(lng, lat)
    return f"{x:.6f}    ", f"{y:.6f}    "


def rt_row(rid, name, lat, lng, cat="한식", **kw):
    row = {
        "RSTR_ID": rid, "RSTR_NM": name, "RSTR_RDNMADR": f"서울특별시 강남구 테스트로 {rid}",
        "RSTR_LNNO_ADRES": None, "RSTR_LA": str(lat), "RSTR_LO": str(lng), "RSTR_TELNO": None,
        "BSNS_STATM_BZCND_NM": cat, "BSNS_LCNC_NM": "일반음식점", "RSTR_INTRCN_CONT": None,
    }
    row.update(kw)
    return row


def lic_row(mgtno, name, lat, lng, cat="한식", status="01", permit="2010-01-01", closed=""):
    x, y = tm(lat, lng) if lat is not None else ("", "")
    return {
        "MGTNO": mgtno, "BPLCNM": name, "UPTAENM": cat, "TRDSTATEGBN": status,
        "TRDSTATENM": {"01": "영업/정상", "02": "휴업", "03": "폐업"}[status],
        "APVPERMYMD": permit + "              ", "DCBYMD": closed, "RDNWHLADDR": "서울특별시 강남구 테헤란로 1",
        "SITEWHLADDR": "서울특별시 강남구 역삼동 1", "SITETEL": "", "X": x, "Y": y, "UPDATEDT": "2026-11-15 10:00:00",
    }


# 강남역(37.497952, 127.027619) 근처 / 먼 곳
NEAR = (37.4985, 127.0280)
NEAR2 = (37.4990, 127.0290)
FAR = (37.5400, 127.0600)

RT_ROWS = [
    rt_row(101, "강남 김치찌개", *NEAR),
    rt_row(102, "역삼 스시", *NEAR2, cat="일식"),
    rt_row(103, "멀리 있는 식당", *FAR),
    rt_row(104, "강남 커피", *NEAR, cat="까페"),
    rt_row(105, "좌표 없는 식당", "", ""),
]
LIC_ROWS = [
    lic_row("3220000-101-2020-00001", "강남김치찌개", *NEAR),  # 레드테이블과 동일 업소로 보이는 행
    lic_row("3220000-101-2020-00002", "테헤란 백반", 37.4983, 127.0283),
    lic_row("3220000-101-2020-00003", "폐업한 식당", 37.4982, 127.0281, status="03", closed="20250101"),
    lic_row("3220000-101-2027-00004", "2027년 개업", 37.4982, 127.0281, permit="2027-01-01"),
    lic_row("3220000-101-2020-00005", "강남 분식", 37.4981, 127.0279, cat="분식"),
]


def make_registry(make_settings, session, **kw):
    return build_default_registry(make_settings(**kw), session=session, today_fn=lambda: TODAY)


def default_session(rt_rows=RT_ROWS, lic_rows=LIC_ROWS):
    return (
        FakeSession()
        .route(REDTABLE, redtable_pages(rt_rows))
        .route(SEOUL, seoul_rows(SERVICE_GANGNAM_GENERAL_RESTAURANT, lic_rows))
    )


def ok_data(result):
    assert result["ok"] is True, result
    assert result["error"] is None
    return result["data"]


def fail_code(result):
    assert result["ok"] is False and result["data"] is None, result
    return result["error"]["code"]


# ---------------------------------------------------------------- 등록/스키마
def test_registered_with_schema(make_settings):
    reg = build_default_registry(make_settings(), session=FakeSession())
    desc = {d["name"]: d for d in reg.describe()}[TOOL]
    assert desc["kind"] == "external_api"
    assert desc["input_schema"]["required"] == ["area"]
    assert set(desc["input_schema"]["properties"]) == {"area", "food_type", "reference_date", "max_results", "order", "seed", "radius_m", "exit_number"}
    assert {"candidates", "query_basis", "source_status"} <= set(desc["output_schema"]["properties"])


# ---------------------------------------------------------------- 정상
def test_success_primary_then_supplement(make_settings):
    session = default_session()
    data = ok_data(make_registry(make_settings, session).invoke(TOOL, {"area": "강남역", "max_results": 10}))
    names = [c["name"] for c in data["candidates"]]
    # 레드테이블 후보 먼저(거리순), 카페·원거리·좌표없음 제외
    assert names[:2] == ["강남 김치찌개", "역삼 스시"]
    assert "멀리 있는 식당" not in names and "강남 커피" not in names and "좌표 없는 식당" not in names
    # 인허가 보충: 영업 중인 것만, 동일 업소로 보이는 행은 연결하지 않고 제외
    assert set(names[2:]) == {"테헤란 백반", "강남 분식"}
    assert data["skipped_possible_duplicates"] == 1
    for c in data["candidates"]:
        assert c["source"] in ("seoul_tourism_redtable", "gangnam_general_restaurant_license")
        assert c["source_id"] and c["road_address"]
        assert c["latitude"] and c["longitude"] and c["distance_m"] <= 700
        assert c["detail_available"] == (c["source"] == "seoul_tourism_redtable")
    lic = [c for c in data["candidates"] if c["source"] == "gangnam_general_restaurant_license"]
    assert all(c["source_id"].startswith("3220000-") for c in lic)
    assert "EPSG:5174" in lic[0]["coordinate_note"]
    assert {s["source"]: s["ok"] for s in data["source_status"]} == {
        "seoul_tourism_redtable": True, "gangnam_general_restaurant_license": True,
    }


def test_food_type_filter(make_settings):
    data = ok_data(make_registry(make_settings, default_session()).invoke(TOOL, {"area": "강남역", "food_type": "분식"}))
    assert [c["name"] for c in data["candidates"]] == ["강남 분식"]


def test_supplement_skipped_when_primary_fills(make_settings):
    session = default_session()
    data = ok_data(make_registry(make_settings, session).invoke(TOOL, {"area": "강남역", "max_results": 2}))
    assert len(data["candidates"]) == 2
    assert not any(SEOUL in c["url"] for c in session.calls)


# ---------------------------------------------------------------- 기준일
def test_default_reference_date_applied(make_settings):
    data = ok_data(make_registry(make_settings, default_session()).invoke(TOOL, {"area": "강남역"}))
    qb = data["query_basis"]
    assert qb["requested_date"] is None
    assert qb["applied_date"] == TODAY.isoformat()
    assert qb["default_applied"] is True and qb["differs_from_request"] is False
    assert any("기본값" in n for n in qb["notes"])


def test_future_reference_date_is_disclosed(make_settings):
    data = ok_data(make_registry(make_settings, default_session()).invoke(TOOL, {"area": "강남역", "reference_date": "2027-03-01"}))
    qb = data["query_basis"]
    assert qb["requested_date"] == "2027-03-01"
    assert qb["applied_date"] == TODAY.isoformat()
    assert qb["differs_from_request"] is True
    assert any("미래" in n for n in qb["notes"])
    assert "2027년 개업" not in [c["name"] for c in data["candidates"]]


def test_past_reference_date_includes_later_closed(make_settings):
    data = ok_data(make_registry(make_settings, default_session()).invoke(TOOL, {"area": "강남역", "reference_date": "2024-06-01"}))
    assert data["query_basis"]["differs_from_request"] is False
    assert "폐업한 식당" in [c["name"] for c in data["candidates"]]  # 2025-01-01 폐업 → 2024-06-01 에는 영업


# ---------------------------------------------------------------- 실패
@pytest.mark.parametrize("args", [{}, {"area": "강남역", "max_results": 0}, {"area": "강남역", "reference_date": "어제"}])
def test_invalid_input(make_settings, args):
    session = default_session()
    assert fail_code(make_registry(make_settings, session).invoke(TOOL, args)) == "INVALID_INPUT"
    assert session.calls == []


def test_unknown_station_is_invalid_after_one_station_list_refresh(make_settings):
    """역 목록에 없는 이름은 목록을 한 번 받아 다시 확인한 뒤 INVALID_INPUT (식당 데이터는 조회하지 않음)."""
    session = default_session()
    assert fail_code(make_registry(make_settings, session).invoke(TOOL, {"area": "없는역"})) == "INVALID_INPUT"
    assert [c["url"] for c in session.calls] and all("subwayStationMaster" in c["url"] for c in session.calls)


def test_missing_all_api_keys(make_settings):
    session = default_session()
    reg = make_registry(make_settings, session, redtable=None, seoul=None)
    result = reg.invoke(TOOL, {"area": "강남역"})
    assert fail_code(result) == "MISSING_API_KEY"
    assert session.calls == []


def test_primary_missing_key_falls_back_to_supplement(make_settings):
    data = ok_data(make_registry(make_settings, default_session(), redtable=None).invoke(TOOL, {"area": "강남역"}))
    assert {c["source"] for c in data["candidates"]} == {"gangnam_general_restaurant_license"}
    st = {s["source"]: s for s in data["source_status"]}
    assert st["seoul_tourism_redtable"]["ok"] is False
    assert st["seoul_tourism_redtable"]["error_code"] == "MISSING_API_KEY"
    # 레드테이블 후보가 없으므로 중복 제외도 없다
    assert "강남김치찌개" in [c["name"] for c in data["candidates"]]


def test_primary_timeout_does_not_break_tool(make_settings):
    session = FakeSession().route(REDTABLE, raise_timeout).route(SEOUL, seoul_rows(SERVICE_GANGNAM_GENERAL_RESTAURANT, LIC_ROWS))
    data = ok_data(make_registry(make_settings, session).invoke(TOOL, {"area": "강남역"}))
    st = {s["source"]: s for s in data["source_status"]}
    assert st["seoul_tourism_redtable"]["error_code"] == "TIMEOUT"
    assert data["candidates"]


def test_both_sources_fail(make_settings):
    session = FakeSession().route(REDTABLE, raise_timeout).route(SEOUL, raise_connection_error)
    result = make_registry(make_settings, session).invoke(TOOL, {"area": "강남역"})
    assert fail_code(result) == "TIMEOUT"


def test_redtable_auth_error_maps_to_api_error(make_settings):
    session = FakeSession().route(
        REDTABLE, lambda *a: json_response({"header": {"resultCode": "30", "resultMsg": "SERVICE_KEY_IS_NOT_REGISTERED_ERROR"}}, 401)
    ).route(SEOUL, raise_timeout)
    result = make_registry(make_settings, session, redtable="secret-token-123").invoke(TOOL, {"area": "강남역"})
    assert fail_code(result) == "API_ERROR"
    assert "secret-token-123" not in result["error"]["message"]


def test_seoul_xml_key_error(make_settings):
    xml = "<RESULT><CODE>INFO-100</CODE><MESSAGE><![CDATA[인증키가 유효하지 않습니다.]]></MESSAGE></RESULT>"
    session = FakeSession().route(REDTABLE, redtable_pages([])).route(SEOUL, lambda *a: FakeResponse(200, xml))
    data_or_fail = make_registry(make_settings, session).invoke(TOOL, {"area": "강남역"})
    assert fail_code(data_or_fail) == "NO_RESULT"  # 레드테이블은 성공(0건), 인허가는 실패 → 결과 없음
    assert "서울 열린데이터광장" in data_or_fail["error"]["message"]


def test_no_result(make_settings):
    session = FakeSession().route(REDTABLE, redtable_pages([rt_row(1, "먼 곳", *FAR)])).route(
        SEOUL, seoul_rows(SERVICE_GANGNAM_GENERAL_RESTAURANT, [])
    )
    assert fail_code(make_registry(make_settings, session).invoke(TOOL, {"area": "역삼역"})) == "NO_RESULT"


# ---------------------------------------------------------------- 캐시/페이징
def test_paging_and_cache_reuse(make_settings):
    session = default_session()
    reg = make_registry(make_settings, session)
    ok_data(reg.invoke(TOOL, {"area": "강남역"}))
    rt_calls = [c for c in session.calls if REDTABLE in c["url"]]
    assert [c["params"]["pageNo"] for c in rt_calls] == [1, 2, 3]  # 5행 / 페이지당 2행
    assert all(c["timeout"] == 3.0 for c in session.calls)
    n = len(session.calls)
    ok_data(reg.invoke(TOOL, {"area": "역삼역"}))
    assert len(session.calls) == n  # 두 번째 호출은 캐시 사용


def test_non_meal_places_excluded(make_settings):
    rows = [rt_row(301, "던킨도너츠(역삼역사점)", *NEAR, cat="제과점영업"), rt_row(302, "강남타로카페", *NEAR, cat="기타"),
            rt_row(303, "진짜 식당", *NEAR2)]
    session = FakeSession().route(REDTABLE, redtable_pages(rows)).route(SEOUL, seoul_rows(SERVICE_GANGNAM_GENERAL_RESTAURANT, []))
    data = ok_data(make_registry(make_settings, session).invoke(TOOL, {"area": "강남역"}))
    assert [c["name"] for c in data["candidates"]] == ["진짜 식당"]


def test_cafe_and_dessert_brands_excluded(make_settings):
    """실제 데이터: 이디야(분류 '패스트푸드'), 쥬스식스('기타 휴게음식점'), 솜사탕 가게가 식사 후보로 추천된 문제."""
    rows = [rt_row(501, "이디야(강남역지하상가점)", *NEAR, cat="패스트푸드"), rt_row(502, "쥬스식스(강남역점)", *NEAR, cat="기타 휴게음식점"),
            rt_row(503, "앤디캔디솜사탕", *NEAR, cat="푸드트럭"), rt_row(504, "마녀떡볶이", *NEAR2, cat="분식")]
    session = FakeSession().route(REDTABLE, redtable_pages(rows)).route(SEOUL, seoul_rows(SERVICE_GANGNAM_GENERAL_RESTAURANT, []))
    data = ok_data(make_registry(make_settings, session).invoke(TOOL, {"area": "강남역"}))
    assert [c["name"] for c in data["candidates"]] == ["마녀떡볶이"]


# ------------------------------------------------- 고르게 섞어 고르기 (같은 식당만 반복되는 문제)
MENU_URL = "seoul.openapi.redtable.global/api/menu/korean"


def _spread_rows():
    """강남역에서 북쪽으로 약 11m 간격, 60곳 (0~660m, 세 거리 구간에 고루)."""
    return [rt_row(1000 + i, f"식당{i:02d}", 37.497952 + i * 0.0001, 127.027619) for i in range(60)]


def _spread_session(menu_ids):
    menus = [{"MENU_ID": n, "MENU_NM": "백반", "MENU_PRICE": 9000, "RSTR_ID": rid} for n, rid in enumerate(menu_ids, 1)]
    return (FakeSession()
            .route(MENU_URL, redtable_pages(menus, page_size=50))
            .route(REDTABLE, redtable_pages(_spread_rows(), page_size=50))
            .route(SEOUL, seoul_rows(SERVICE_GANGNAM_GENERAL_RESTAURANT, [])))


def _ids(data):
    return [c["source_id"] for c in data["candidates"]]


def test_distance_order_is_default_and_always_nearest(make_settings):
    reg = make_registry(make_settings, _spread_session([]))
    data = ok_data(reg.invoke(TOOL, {"area": "강남역", "max_results": 10}))
    assert data["order"] == "distance" and data["pool_size"] == 60
    assert _ids(data) == [str(1000 + i) for i in range(10)]
    assert all(c["menu_available"] is None for c in data["candidates"])  # distance 정렬은 메뉴 조회를 하지 않음


def test_varied_picks_across_distance_bands_and_is_reproducible(make_settings):
    reg = make_registry(make_settings, _spread_session([]))
    args = {"area": "강남역", "max_results": 9, "order": "varied", "seed": 7}
    a = ok_data(reg.invoke(TOOL, args))
    b = ok_data(reg.invoke(TOOL, args))
    c = ok_data(reg.invoke(TOOL, dict(args, seed=8)))
    assert _ids(a) == _ids(b)  # 같은 seed → 같은 결과 (재현 가능)
    assert _ids(a) != _ids(c)  # seed 가 바뀌면 다른 후보
    dists = [x["distance_m"] for x in a["candidates"]]
    assert dists == sorted(dists)  # 고른 뒤에는 거리순
    assert sum(d < 250 for d in dists) == 3 and sum(250 <= d < 450 for d in dists) == 3 and sum(d >= 450 for d in dists) == 3
    assert _ids(a) != [str(1000 + i) for i in range(9)]  # 가장 가까운 9곳 고정이 아님
    assert any("고르게" in n for n in a["query_basis"]["notes"])


def test_varied_prefers_restaurants_with_menu_data(make_settings):
    with_menu = [1001, 1003, 1030, 1050]
    reg = make_registry(make_settings, _spread_session(with_menu))
    data = ok_data(reg.invoke(TOOL, {"area": "강남역", "max_results": 6, "order": "varied", "seed": 1}))
    flags = {c["source_id"]: c["menu_available"] for c in data["candidates"]}
    assert {str(i) for i in with_menu} <= set(flags)  # 메뉴 정보가 있는 곳이 먼저 뽑힘
    assert all(flags[str(i)] is True for i in with_menu)
    assert sum(v is False for v in flags.values()) == 2


def test_varied_menu_lookup_failure_keeps_candidates(make_settings):
    session = (FakeSession()
               .route(MENU_URL, lambda *_: (_ for _ in ()).throw(RuntimeError("menu down")))
               .route(REDTABLE, redtable_pages(_spread_rows(), page_size=50))
               .route(SEOUL, seoul_rows(SERVICE_GANGNAM_GENERAL_RESTAURANT, [])))
    data = ok_data(make_registry(make_settings, session).invoke(
        TOOL, {"area": "강남역", "max_results": 5, "order": "varied", "seed": 3}))
    assert len(data["candidates"]) == 5
    assert all(c["menu_available"] is None for c in data["candidates"])  # 확인 못 하면 null, 만들지 않음


def test_radius_limits_pool_and_bands_scale(make_settings):
    """사용자가 거리 제한을 말하면 그 반경 안에서만 고른다 (700m 전체에서 섞었다가 대부분 제외되는 문제)."""
    reg = make_registry(make_settings, _spread_session([]))
    data = ok_data(reg.invoke(TOOL, {"area": "강남역", "max_results": 6, "order": "varied", "seed": 2, "radius_m": 200}))
    assert data["radius_m"] == 200 and data["pool_size"] == 18  # 0~189m 의 18곳
    dists = [c["distance_m"] for c in data["candidates"]]
    assert len(dists) == 6 and max(dists) <= 200
    assert sum(d < 250 * 200 / 700 for d in dists) == 2  # 구간 경계도 반경에 비례 (구간마다 2곳)
    assert fail_code(reg.invoke(TOOL, {"area": "강남역", "radius_m": 30})) == "INVALID_INPUT"  # 50m 미만 거부

"""F3004 주변 카페 검색 Tool - Mock 단위 테스트 (외부 호출 없음)."""
from __future__ import annotations

from datetime import date

import pytest

from app.clients.seoul_opendata import SERVICE_GANGNAM_GENERAL_RESTAURANT
from app.tools.catalog import build_default_registry
from tests.fakes import FakeResponse, FakeSession, json_response, raise_timeout, redtable_pages, seoul_rows
from app.clients.seoul_opendata import SERVICE_GANGNAM_REST_FOOD
from tests.unit.test_f3002_restaurant_candidates import LIC_ROWS, RT_ROWS, lic_row

TOOL = "search_nearby_cafes"
KAKAO = "dapi.kakao.com/v2/local/search/category.json"
REST_FOOD = "LOCALDATA_072405_GN"
REST_ROWS = [
    lic_row("3220000-104-2020-00001", "인허가 커피숍", 37.4987, 127.0282, cat="커피숍"),
    lic_row("3220000-104-2020-00002", "폐업 커피숍", 37.4986, 127.0281, cat="커피숍", status="03", closed="20240101"),
    lic_row("3220000-104-2020-00003", "편의점", 37.4986, 127.0281, cat="편의점"),
    lic_row("3220000-104-2020-00004", "먼 커피숍", 37.5200, 127.0500, cat="커피숍"),
]


def with_rest_food(sess, rows=REST_ROWS):
    return sess.route(REST_FOOD, seoul_rows(SERVICE_GANGNAM_REST_FOOD, rows))
ARGS = {"latitude": 37.4985, "longitude": 127.0280, "radius_m": 300, "max_results": 5}


def doc(i, **kw):
    d = {
        "id": str(1000 + i), "place_name": f"카페{i}", "category_name": "음식점 > 카페",
        "category_group_code": "CE7", "phone": "02-000-0000" if i % 2 else "",
        "address_name": f"서울 강남구 역삼동 {i}", "road_address_name": f"서울 강남구 테헤란로 {i}",
        "x": f"{127.0280 + i * 0.0001:.7f}", "y": f"{37.4985 + i * 0.0001:.7f}",
        "place_url": f"http://place.map.kakao.com/{1000 + i}", "distance": str(10 * i),
    }
    d.update(kw)
    return d


def kakao_pages(docs, page_size=15):
    def handler(url, params, headers):
        assert headers.get("Authorization", "").startswith("KakaoAK ")
        assert params["category_group_code"] == "CE7" and params["sort"] == "distance"
        page = int(params["page"])
        chunk = docs[(page - 1) * page_size : page * page_size]
        return json_response({
            "meta": {"total_count": len(docs), "pageable_count": len(docs), "is_end": page * page_size >= len(docs)},
            "documents": chunk,
        })

    return handler


def registry(make_settings, sess, **kw):
    return build_default_registry(make_settings(**kw), session=sess, today_fn=lambda: date(2026, 11, 18))


def ok_data(result):
    assert result["ok"] is True, result
    return result["data"]


def fail(result, code):
    assert result == {"ok": False, "data": None, "error": {"code": code, "message": result["error"]["message"]}}
    assert result["error"]["message"]


def test_registered_with_schema(make_settings):
    desc = {d["name"]: d for d in registry(make_settings, FakeSession()).describe()}[TOOL]
    assert desc["kind"] == "external_api"
    assert set(desc["input_schema"]["required"]) == {"latitude", "longitude"}
    assert {"radius_m", "max_results"} <= set(desc["input_schema"]["properties"])


def test_success_fields(make_settings):
    sess = FakeSession().route(KAKAO, kakao_pages([doc(i) for i in range(1, 4)]))
    data = ok_data(registry(make_settings, sess).invoke(TOOL, ARGS))
    assert data["total_count"] == 3 and len(data["cafes"]) == 3
    assert data["not_provided_fields"] == ["opening_hours", "power_outlet", "wifi", "congestion"]
    for c in data["cafes"]:
        assert c["name"].startswith("카페")
        assert c["address"].startswith("서울 강남구") and c["road_address"].startswith("서울 강남구")
        assert 37.0 < c["latitude"] < 38.0 and 126.5 < c["longitude"] < 127.5
        assert c["place_url"].startswith("http://place.map.kakao.com/")
        assert isinstance(c["distance_m"], int)
        assert c["source"] == "kakao_local_category_CE7" and c["distance_basis"] == "카카오 제공 직선거리"
        assert c["estimated_walk_minutes"] >= 1
        # 카카오가 주지 않는 정보는 생성하지 않는다
        assert c["opening_hours"] is None and c["power_outlet"] is None and c["wifi"] is None and c["congestion"] is None
    assert [c["distance_m"] for c in data["cafes"]] == [10, 20, 30]
    call = sess.calls[0]
    assert call["params"]["x"].startswith("127.028") and call["params"]["y"].startswith("37.4985")
    assert call["params"]["radius"] == 300 and call["timeout"] == 3.0


def test_pagination_respects_max_results(make_settings):
    sess = FakeSession().route(KAKAO, kakao_pages([doc(i) for i in range(1, 41)]))
    data = ok_data(registry(make_settings, sess).invoke(TOOL, {**ARGS, "max_results": 20}))
    assert len(data["cafes"]) == 20
    assert [c["params"]["page"] for c in sess.calls] == [1, 2]
    assert len({c["source_id"] for c in data["cafes"]}) == 20


def test_documents_without_coords_or_link_are_dropped(make_settings):
    docs = [doc(1), doc(2, x="", y=""), doc(3, place_url=""), doc(4, place_name="")]
    sess = FakeSession().route(KAKAO, kakao_pages(docs))
    data = ok_data(registry(make_settings, sess).invoke(TOOL, ARGS))
    assert [c["name"] for c in data["cafes"]] == ["카페1"]


def test_empty_address_becomes_null(make_settings):
    sess = FakeSession().route(KAKAO, kakao_pages([doc(1, road_address_name="", phone="")]))
    cafe = ok_data(registry(make_settings, sess).invoke(TOOL, ARGS))["cafes"][0]
    assert cafe["road_address"] is None and cafe["phone"] is None


def test_no_result(make_settings):
    sess = with_rest_food(FakeSession().route(KAKAO, kakao_pages([])), rows=[])
    fail(registry(make_settings, sess).invoke(TOOL, ARGS), "NO_RESULT")


def test_walk_minutes_is_estimate_from_straight_distance():
    from app.tools.nearby_cafes import WALK_BASIS, estimate_walk_minutes

    assert estimate_walk_minutes(None) is None
    assert estimate_walk_minutes(0) == 1
    assert estimate_walk_minutes(670) == 13  # 670*1.3/67
    assert "실제 경로 아님" in WALK_BASIS


def test_kakao_failure_falls_back_to_rest_food_license(make_settings):
    sess = with_rest_food(FakeSession().route(KAKAO, lambda *a: FakeResponse(403, '{"errorType":"NotAuthorizedError"}')))
    data = ok_data(registry(make_settings, sess).invoke(TOOL, ARGS))
    assert [c["name"] for c in data["cafes"]] == ["인허가 커피숍"]  # 폐업·편의점·반경 밖 제외
    cafe = data["cafes"][0]
    assert cafe["source"] == "gangnam_rest_food_license" and cafe["place_url"] is None
    assert "직선거리" in cafe["distance_basis"] and cafe["distance_m"] <= 300
    st = {s["source"]: s for s in data["source_status"]}
    assert st["kakao_local_category_CE7"]["ok"] is False and st["kakao_local_category_CE7"]["error_code"] == "API_ERROR"
    assert st["gangnam_rest_food_license"]["ok"] is True


def test_kakao_success_does_not_call_fallback(make_settings):
    sess = with_rest_food(FakeSession().route(KAKAO, kakao_pages([doc(1)])))
    ok_data(registry(make_settings, sess).invoke(TOOL, ARGS))
    assert not any(REST_FOOD in c["url"] for c in sess.calls)


@pytest.mark.parametrize("args", [
    {}, {"latitude": 37.49}, {"latitude": 91, "longitude": 127.0}, {**ARGS, "radius_m": 0},
    {**ARGS, "radius_m": 20001}, {**ARGS, "max_results": 0}, {**ARGS, "latitude": "강남"},
])
def test_invalid_input(make_settings, args):
    sess = FakeSession()
    fail(registry(make_settings, sess).invoke(TOOL, args), "INVALID_INPUT")
    assert sess.calls == []


def test_missing_api_key(make_settings):
    sess = FakeSession()
    fail(registry(make_settings, sess, kakao=None, seoul=None).invoke(TOOL, ARGS), "MISSING_API_KEY")
    assert sess.calls == []


def test_missing_kakao_key_uses_fallback(make_settings):
    sess = with_rest_food(FakeSession())
    data = ok_data(registry(make_settings, sess, kakao=None).invoke(TOOL, ARGS))
    assert data["source_status"][0]["error_code"] == "MISSING_API_KEY"
    assert data["cafes"][0]["source"] == "gangnam_rest_food_license"


def test_timeout(make_settings):
    sess = FakeSession().route(KAKAO, raise_timeout).route(REST_FOOD, raise_timeout)
    fail(registry(make_settings, sess).invoke(TOOL, ARGS), "TIMEOUT")


@pytest.mark.parametrize("status, body", [
    (401, '{"errorType":"AccessDeniedError","message":"wrong appKey"}'),
    (429, '{"errorType":"RequestThrottled"}'),
    (500, "internal"),
    (200, "not-json"),
    (200, '{"meta": {}}'),
])
def test_api_errors(make_settings, status, body):
    sess = FakeSession().route(KAKAO, lambda *a: FakeResponse(status, body))
    result = registry(make_settings, sess, kakao="kakao-secret-xyz", seoul=None).invoke(TOOL, ARGS)
    fail(result, "API_ERROR")
    assert "kakao-secret-xyz" not in result["error"]["message"]


def test_restaurant_to_cafe_flow(make_settings):
    """F3002 후보 좌표 → F3004 입력으로 이어지는 흐름. 카카오 장애가 앞 Tool 결과에 영향을 주지 않는다."""
    sess = (
        FakeSession()
        .route("redtable.global/api/rstr", redtable_pages(RT_ROWS))
        .route("openapi.seoul.go.kr", seoul_rows(SERVICE_GANGNAM_GENERAL_RESTAURANT, LIC_ROWS))
        .route(KAKAO, raise_timeout)
        .route(REST_FOOD, raise_timeout)
    )
    reg = registry(make_settings, sess)
    cand = ok_data(reg.invoke("search_restaurant_candidates", {"area": "강남역"}))["candidates"][0]
    cafes = reg.invoke(TOOL, {"latitude": cand["latitude"], "longitude": cand["longitude"]})
    fail(cafes, "TIMEOUT")
    assert reg.invoke("search_restaurant_candidates", {"area": "강남역"})["ok"] is True


def test_kakao_error_not_hidden_when_fallback_empty(make_settings):
    sess = with_rest_food(FakeSession().route(KAKAO, lambda *a: FakeResponse(500, "x")), rows=[])
    fail(registry(make_settings, sess).invoke(TOOL, ARGS), "API_ERROR")

"""추가 기능 — 기상청 날씨 조회 Tool Mock 단위 테스트."""
from __future__ import annotations

from datetime import datetime

import pytest

from app.clients.kma import latlon_to_grid
from app.datasets.cache import KST
from app.tools.catalog import build_default_registry
from app.tools.weather import base_before, latest_base
from tests.fakes import FakeResponse, FakeSession, json_response, raise_timeout

TOOL = "get_weather_context"
KMA = "apis.data.go.kr/1360000/VilageFcstInfoService_2.0/getVilageFcst"
NOW = datetime(2026, 11, 19, 11, 30, tzinfo=KST)


def items(fdate="20261119", ftime="1300", **vals):
    base = {"TMP": "4", "POP": "70", "PTY": "1", "SKY": "4", "PCP": "1mm", "REH": "80", "WSD": "3.1"}
    base.update(vals)
    return [{"category": k, "fcstDate": fdate, "fcstTime": ftime, "fcstValue": v} for k, v in base.items() if v is not None]


def kma_handler(rows, code="00"):
    def handler(url, params, headers):
        assert "serviceKey=test-kma" in url  # 인코딩된 키를 URL 에 그대로 붙임
        handler.calls.append(params)
        return json_response({"response": {"header": {"resultCode": code, "resultMsg": "X"},
                                           "body": {"items": {"item": rows}, "totalCount": len(rows)}}})

    handler.calls = []
    return handler


def reg(make_settings, sess, **kw):
    from dataclasses import replace

    settings = replace(make_settings(), kma_api_key=kw.pop("kma", "test-kma"))
    return build_default_registry(settings, session=sess, now_fn=lambda: NOW)


def ok_data(r):
    assert r["ok"] is True, r
    return r["data"]


def fail_code(r):
    assert r["ok"] is False and r["data"] is None
    return r["error"]["code"]


def test_grid_conversion_known_points():
    assert latlon_to_grid(37.497952, 127.027619) == (61, 125)  # 강남역
    assert latlon_to_grid(37.5665, 126.9780) == (60, 127)  # 서울시청


def test_base_time_selection():
    assert latest_base(datetime(2026, 11, 19, 11, 30, tzinfo=KST)).hour == 11
    assert latest_base(datetime(2026, 11, 19, 11, 5, tzinfo=KST)).hour == 8  # 발표 10분 전
    first = latest_base(datetime(2026, 11, 19, 1, 0, tzinfo=KST))
    assert (first.day, first.hour) == (18, 23)
    assert base_before(datetime(2026, 11, 19, 9, 0, tzinfo=KST)).hour == 8


def test_registered(make_settings):
    desc = {d["name"]: d for d in reg(make_settings, FakeSession()).describe()}[TOOL]
    assert desc["kind"] == "external_api"
    assert {"area", "visit_date", "visit_time"} <= set(desc["input_schema"]["properties"])


def test_success_with_explicit_time(make_settings):
    h = kma_handler(items())
    data = ok_data(reg(make_settings, FakeSession().route(KMA, h)).invoke(
        TOOL, {"area": "강남역", "visit_date": "2026-11-19", "visit_time": "13:00"}))
    assert data["grid"] == {"nx": 61, "ny": 125}
    assert data["temperature_c"] == 4.0 and data["precipitation_probability"] == 70
    assert data["precipitation_type"] == "비" and data["sky"] == "흐림"
    assert data["forecast_datetime"].startswith("2026-11-19T13:00")
    assert data["base_datetime"].startswith("2026-11-19T11:00")
    assert data["default_applied"] == [] and data["missing_fields"] == []
    assert h.calls[0]["base_time"] == "1100" and h.calls[0]["nx"] == 61


def test_defaults_applied(make_settings):
    h = kma_handler(items(ftime="1200"))
    data = ok_data(reg(make_settings, FakeSession().route(KMA, h)).invoke(TOOL, {"area": "역삼역"}))
    assert data["default_applied"] == ["visit_date=오늘", "visit_time=12:00"]
    assert data["forecast_datetime"].startswith("2026-11-19T12:00")


def test_minute_rounding_note(make_settings):
    h = kma_handler(items())
    data = ok_data(reg(make_settings, FakeSession().route(KMA, h)).invoke(
        TOOL, {"area": "강남역", "visit_date": "2026-11-19", "visit_time": "13:40"}))
    assert any("정시" in n for n in data["notes"])


def test_past_hour_today_uses_earlier_base(make_settings):
    h = kma_handler(items(ftime="0900"))
    data = ok_data(reg(make_settings, FakeSession().route(KMA, h)).invoke(
        TOOL, {"area": "강남역", "visit_date": "2026-11-19", "visit_time": "09:00"}))
    assert h.calls[0]["base_time"] == "0800"
    assert any("실측값 아님" in n for n in data["notes"])


def test_missing_values_stay_null(make_settings):
    h = kma_handler(items(POP=None, SKY=None, PCP=None))
    data = ok_data(reg(make_settings, FakeSession().route(KMA, h)).invoke(
        TOOL, {"area": "강남역", "visit_date": "2026-11-19", "visit_time": "13:00"}))
    assert data["precipitation_probability"] is None and data["sky"] is None
    assert set(data["missing_fields"]) == {"precipitation_probability", "sky", "precipitation_amount"}


@pytest.mark.parametrize("args, code", [
    ({"area": "강남역", "visit_date": "2026-11-18", "visit_time": "12:00"}, "NO_RESULT"),  # 과거 날짜
    ({"area": "강남역", "visit_date": "2026-11-30", "visit_time": "12:00"}, "NO_RESULT"),  # 범위 밖
    ({}, "INVALID_INPUT"),
    ({"area": "홍대"}, "INVALID_INPUT"),
    ({"latitude": 37.5}, "INVALID_INPUT"),
])
def test_out_of_range_and_invalid(make_settings, args, code):
    sess = FakeSession()
    assert fail_code(reg(make_settings, sess).invoke(TOOL, args)) == code
    assert sess.calls == []


def test_target_not_in_response(make_settings):
    h = kma_handler(items(ftime="1500"))
    r = reg(make_settings, FakeSession().route(KMA, h)).invoke(TOOL, {"area": "강남역", "visit_date": "2026-11-19", "visit_time": "13:00"})
    assert fail_code(r) == "NO_RESULT"


def test_missing_key(make_settings):
    sess = FakeSession()
    assert fail_code(reg(make_settings, sess, kma=None).invoke(TOOL, {"area": "강남역"})) == "MISSING_API_KEY"
    assert sess.calls == []


def test_timeout(make_settings):
    assert fail_code(reg(make_settings, FakeSession().route(KMA, raise_timeout)).invoke(TOOL, {"area": "강남역"})) == "TIMEOUT"


def test_xml_key_error(make_settings):
    xml = "<OpenAPI_ServiceResponse><cmmMsgHeader><returnAuthMsg>SERVICE_KEY_IS_NOT_REGISTERED_ERROR</returnAuthMsg></cmmMsgHeader></OpenAPI_ServiceResponse>"
    r = reg(make_settings, FakeSession().route(KMA, lambda *a: FakeResponse(200, xml))).invoke(TOOL, {"area": "강남역"})
    assert fail_code(r) == "API_ERROR" and "test-kma" not in r["error"]["message"]


def test_no_data_code(make_settings):
    r = reg(make_settings, FakeSession().route(KMA, kma_handler([], code="03"))).invoke(TOOL, {"area": "강남역"})
    assert fail_code(r) == "NO_RESULT"

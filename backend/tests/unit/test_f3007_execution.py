"""F3007 Tool 호출 및 결과 통합 - 단위 테스트 (Mock 외부 API)."""
from __future__ import annotations

from app.agent.graph import MainAgent
from tests.fakes import raise_timeout
from tests.unit.agent_fixtures import KAKAO, KMA, TODAY, kakao_handler, make_registry, make_session


def agent(make_settings, session, **keys):
    return MainAgent(make_registry(make_settings, session, **keys), today_fn=lambda: TODAY)


def test_graph_has_analyze_plan_execute_respond(make_settings):
    s = agent(make_settings, make_session()).graph_structure()
    assert {"analyze", "plan", "execute", "respond"} <= set(s["nodes"])


def test_previous_outputs_feed_next_inputs(make_settings):
    result = agent(make_settings, make_session()).run("강남역에서 점심 먹고 카공할 건데 추천해줘")
    calls = result["tool_calls"]
    tools = [c["tool"] for c in calls]
    assert tools[0] == "get_weather_context" and tools[1] == "search_restaurant_candidates"
    data = result["data"]
    # 후보 Tool 의 source/source_id 가 상세 Tool 입력으로 그대로 전달됨
    detail_args = [c["args"] for c in calls if c["tool"] == "get_restaurant_details"]
    first_six = [{"source": c["source"], "source_id": c["source_id"]} for c in data.candidates[:6]]
    assert detail_args == first_six
    # 후보 좌표가 카페 Tool 입력으로 전달됨
    cafe_args = [c["args"] for c in calls if c["tool"] == "search_nearby_cafes"]
    assert cafe_args and cafe_args[0]["latitude"] == data.candidates[0]["latitude"]
    assert data.weather["temperature_c"] == 12.0
    assert all(c["duration_ms"] >= 0 for c in calls)


def test_one_tool_failure_does_not_stop_others(make_settings):
    session = make_session(kma=raise_timeout, kakao=kakao_handler(fail=True))
    result = agent(make_settings, session).run("강남역 점심 추천해줘")
    data = result["data"]
    assert data.weather is None and data.weather_error["code"] == "TIMEOUT"
    assert data.candidates and data.details  # 날씨 실패 후에도 후보·상세 진행
    assert data.cafe_errors and all(e["code"] == "API_ERROR" for e in data.cafe_errors.values())
    assert any(not c["ok"] for c in result["tool_calls"])


def test_detail_failure_recorded_and_next_candidate_continues(make_settings):
    session = make_session()
    calls = {"n": 0}
    original = [r for r in session.routes if r[0].endswith("/api/menu/korean")][0][1]

    def flaky_menu(url, params, headers):
        calls["n"] += 1
        return original(url, params, headers)

    session.routes = [(p, h) for p, h in session.routes if not p.endswith("/api/menu/korean")]
    session.route("seoul.openapi.redtable.global/api/menu/korean", raise_timeout)
    result = agent(make_settings, session).run("강남역 점심 추천해줘")
    data = result["data"]
    # 메뉴 API 실패는 상세 Tool 내부에서 섹션 오류로 격리되어 상세 결과는 계속 반환됨
    assert len(data.details) == 6
    assert all(d["menu_status"] == "error" for d in data.details.values())


def test_no_tool_request_calls_nothing(make_settings):
    session = make_session()
    result = agent(make_settings, session).run("안녕!")
    assert result["tool_calls"] == [] and session.calls == []
    assert result["plan"] is None


def test_area_hint_from_ui(make_settings):
    result = agent(make_settings, make_session()).run("점심 추천해줘", area_hint="역삼역")
    assert result["conditions"].preference.area == "역삼역"
    assert result["tool_calls"][1]["args"]["area"] == "역삼역"

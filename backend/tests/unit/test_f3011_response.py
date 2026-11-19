"""F3011 최종 응답 생성 - 단위 테스트 (Mock 외부 API)."""
from __future__ import annotations

import json

from app.agent.graph import MainAgent
from tests.fakes import raise_timeout
from tests.unit.agent_fixtures import TODAY, kakao_handler, make_registry, make_session


def run(make_settings, msg, session=None, llm=None, **keys):
    agent = MainAgent(make_registry(make_settings, session or make_session(), **keys), today_fn=lambda: TODAY, llm=llm)
    return agent.run(msg)["response"]


def test_recommendation_contains_items_aux_criteria_evidence_excluded(make_settings):
    body = run(make_settings, "강남역에서 1만원 이하로 12시 점심 먹고 카공")
    rec = body["recommendations"][0]
    assert rec["name"] == "김치찌개집" and rec["source"] == "seoul_tourism_redtable" and rec["source_id"] == "1"
    assert rec["matched_menus"] == [{"name": "김치찌개", "price_krw": 9000}]
    assert rec["business_hours"] == "매일 11:00~21:00" and rec["estimated_walk_minutes"] >= 1
    assert any(c["criterion"] == "예산" and c["result"] == "pass" for c in rec["checks"])
    cafe = rec["cafes"][0]
    assert cafe["name"] and cafe["place_url"].startswith("http") and cafe["distance_m"] is not None
    assert any("예산" in c for c in body["criteria"]) and any("도보 시간" in c for c in body["criteria"])
    assert {e["tool"] for e in body["evidence"]} >= {"search_restaurant_candidates", "get_restaurant_details", "search_nearby_cafes"}
    reasons = {x["name"]: x["reason"] for x in body["excluded"]}
    assert "최저가" in reasons["스시하우스"] and "판단 불가" in reasons["가격미상 국밥"]
    assert "김치찌개집" in body["message"] and "9,000원" in body["message"]
    assert "콘센트" in body["message"]  # 카페 미확인 정보 안내
    assert body["disclaimer"] is None and body["message_by"] == "template"


def test_no_result_gives_reason_and_suggestions(make_settings):
    body = run(make_settings, "강남역 3천원 이하 점심")
    assert body["recommendations"] == []
    assert body["stop_reason"] and body["suggestions"]
    assert "찾지 못했어요" in body["message"] and "예산" in body["message"]


def test_health_disclaimer(make_settings):
    body = run(make_settings, "강남역 점심 추천해줘, 갑각류 알레르기 있어")
    assert body["disclaimer"] and body["disclaimer"] in body["message"]


def test_tool_failure_notice_without_internal_details(make_settings):
    body = run(make_settings, "강남역 점심 추천", session=make_session(kma=raise_timeout, kakao=kakao_handler(fail=True)),
               kakao="kakao-secret-123")
    text = json.dumps(body, ensure_ascii=False)
    assert "날씨 조회: 외부 서비스 응답이 늦어" in text
    assert "kakao-secret-123" not in text and "Traceback" not in text and "HTTP 500" not in body["message"]
    assert body["weather"] is None and "날씨 미확인" in body["weather_policy"][0]


def test_missing_key_notice(make_settings):
    body = run(make_settings, "강남역 점심 추천", redtable=None, seoul=None)
    assert any("API 키가 설정되지 않아" in n for n in body["notices"])
    assert "MISSING_API_KEY" in body["stop_reason"]


def test_non_tool_responses(make_settings):
    assert "밥카공" in run(make_settings, "안녕")["message"]
    help_body = run(make_settings, "사용법 알려줘")
    assert "예:" in help_body["message"] and help_body["evidence"] == []
    clarify = run(make_settings, "점심 먹고 카공할 곳 추천")
    assert clarify["clarify"] is True and "강남역 또는 역삼역" in clarify["message"]


def test_llm_message_only_when_available(make_settings):
    class StubLLM:
        def __init__(self):
            self.seen = None

        def with_structured_output(self, schema):
            raise RuntimeError("분석은 규칙으로")  # 분석 단계 LLM 실패 → 규칙 대체

        def invoke(self, messages):
            self.seen = messages
            return type("Msg", (), {"content": self.reply})()

    llm = StubLLM()
    llm.reply = ("1. 김치찌개집 — 카페1 (직선 30m)\n2. 일요일휴무 백반 — 카페1 (직선 30m)\n3. 칼국수집 — 카페1 (직선 30m)\n"
                 "카페 영업시간·콘센트·와이파이·혼잡도는 확인되지 않았어요")
    body = run(make_settings, "강남역 1만원 이하 12시 점심", llm=llm)
    assert body["message_by"] == "llm" and body["message"] == llm.reply
    assert "김치찌개집" in llm.seen[1][1]  # 확정된 JSON 만 근거로 전달
    # 카페(보조 정보)나 미확인 안내가 빠진 LLM 문장은 쓰지 않고 템플릿으로 대체
    llm.reply = "김치찌개집을 추천해요. 분위기가 아주 좋아요!"
    body2 = run(make_settings, "강남역 1만원 이하 12시 점심", llm=llm)
    assert body2["message_by"] == "template" and "카페1" in body2["message"]


def test_user_reported_rain_vs_forecast_notice(make_settings):
    body = run(make_settings, "비가 오는데 강남역 점심 추천")  # 예보는 강수확률 20%
    assert any("말씀하신 날씨(비)" in n for n in body["notices"])

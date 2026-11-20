"""Codex 2차 검증 결함 2: 전체 답변의 근거 없는 주장, 카페 미확인 식당의 코스 개수."""
from __future__ import annotations

from app.agent.graph import MainAgent
from app.agent.respond import _count_line, _summary
from tests.unit.agent_fixtures import TODAY, kakao_handler, make_registry, make_session


class FakeMessageLLM:
    """분석은 규칙으로 넘어가며, 문장을 요청하면 잘못된 가격과 편의시설을 반환한다."""

    def __init__(self, text):
        self.text = text
        self.response_calls = 0

    def with_structured_output(self, schema):
        raise RuntimeError("분석은 규칙 사용")

    def invoke(self, _messages):
        self.response_calls += 1
        return type("Msg", (), {"content": self.text})()


def run(make_settings, llm=None, kakao=None):
    agent = MainAgent(make_registry(make_settings, make_session(kakao=kakao)), today_fn=lambda: TODAY,
                      llm=llm, seed_fn=lambda: 1)
    return agent.run("강남역 1만원 이하로 12시 점심 먹고 카공")["response"]


def test_full_message_keeps_distance_price_and_amenities_separate(make_settings):
    base = run(make_settings)
    top = base["recommendations"][0]
    distance = top["distance_m"]
    price = top["matched_menus"][0]["price_krw"]
    assert distance != price
    names = " / ".join(f"{r['name']} {r['cafes'][0]['name']}" for r in base["recommendations"])
    llm = FakeMessageLLM(f"{names}. 메뉴 가격은 {distance}원. 콘센트 제공이며 영업시간 미확인.")

    body = run(make_settings, llm)

    assert llm.response_calls == 0
    assert body["message_by"] == "template"
    assert body["message"] == base["message"]
    assert f"직선 {distance}m" in body["message"] and f"{price:,}원" in body["message"]
    assert f"{distance}원" not in body["message"] and "콘센트 제공" not in body["message"]
    assert "확인이 필요합니다" in body["message"]


def test_summary_counts_only_courses_with_cafe(make_settings):
    body = run(make_settings, kakao=kakao_handler(empty=True))  # 카페 조회 결과 없음
    recs = body["recommendations"]
    assert recs and all(not r["cafes"] for r in recs)
    assert body["summary"].startswith(f"조건에 맞는 식당 {len(recs)}곳을 찾았어요. 식사 후 카페까지 확인된 코스는 0개")
    assert "식사 후 카페: 주변 카페를 확인하지 못했어요" in body["summary"]
    assert "코스 5개" not in body["message"]


def test_count_line_mixed():
    recs = [{"cafes": [{}]}, {"cafes": []}, {"cafes": [{}]}]
    assert _count_line(recs) == "조건에 맞는 식당 3곳을 찾았어요. 식사 후 카페까지 확인된 코스는 2개이고, 1곳은 주변 카페를 확인하지 못했어요."
    assert _count_line([{"cafes": [{}]}]) == "조건에 맞는 코스 1개를 찾았어요."
    assert _summary("recommend", {"recommendations": [{"name": "A", "cafes": [], "distance_m": 10, "distance_from": "강남역"}]}).splitlines()[2] \
        == "식사 후 카페: 주변 카페를 확인하지 못했어요"

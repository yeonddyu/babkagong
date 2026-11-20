"""Codex 2차 검증 결함 2: 전체 답변의 근거 없는 주장, 카페 미확인 식당의 코스 개수."""
from __future__ import annotations

from app.agent.graph import MainAgent
from app.agent.respond import _count_line, _llm_facts_only, _summary
from tests.unit.agent_fixtures import TODAY, kakao_handler, make_registry, make_session


class FakeMessageLLM:
    """분석은 실패시키고(규칙 사용), 응답 문장 생성만 주어진 문장을 돌려준다."""

    def __init__(self, text):
        self.text = text

    def with_structured_output(self, schema):
        raise RuntimeError("분석은 규칙 사용")

    def invoke(self, _messages):
        return type("Msg", (), {"content": self.text})()


def run(make_settings, llm_text, kakao=None):
    agent = MainAgent(make_registry(make_settings, make_session(kakao=kakao)), today_fn=lambda: TODAY,
                      llm=FakeMessageLLM(llm_text))
    return agent.run("강남역 1만원 이하로 12시 점심 먹고 카공")["response"]


def names_line(body):
    return " / ".join(f"{r['name']} {r['cafes'][0]['name'] if r['cafes'] else ''}" for r in body["recommendations"])


def test_llm_message_with_invented_price_or_amenity_is_rejected(make_settings):
    base = run(make_settings, "x")  # 템플릿
    names = names_line(base)
    bad = run(make_settings, f"{names}. 식당 500원, 카페 콘센트 보장. 영업시간 미확인")
    assert bad["message_by"] == "template" and "500원" not in bad["message"] and "보장" not in bad["message"]
    good = run(make_settings, f"{names}. 카페 영업시간·콘센트·와이파이·혼잡도는 확인되지 않았어요")
    assert good["message_by"] == "llm"


def test_facts_only_rules():
    body = {"recommendations": [{"name": "김치찌개집", "matched_menus": [{"name": "김치찌개", "price_krw": 9000}], "distance_m": 120}]}
    assert _llm_facts_only("1. 김치찌개집 김치찌개 9,000원, 역에서 120m", body)
    assert not _llm_facts_only("김치찌개집 8,000원", body)  # 결과에 없는 가격
    assert not _llm_facts_only("김치찌개집은 분위기가 조용해요", body)  # 확인할 수 없는 단정
    assert _llm_facts_only("콘센트·와이파이는 확인되지 않았어요", body)  # 미확인 안내는 허용


def test_summary_counts_only_courses_with_cafe(make_settings):
    body = run(make_settings, "x", kakao=kakao_handler(empty=True))  # 카페 조회 결과 없음
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

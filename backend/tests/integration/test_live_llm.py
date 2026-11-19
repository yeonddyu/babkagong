"""LLM(SSAFY GMS) 실제 호출 통합 테스트. 실행: pytest -m integration -rs"""
from __future__ import annotations

from datetime import date, time

import pytest

from app.agent.analysis import analyze
from app.agent.graph import MainAgent
from app.core.llm_provider import create_llm, llm_status
from app.tools.catalog import build_default_registry
from tests.integration.conftest import require_key

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def llm(live_settings):
    st = llm_status(live_settings)
    require_key(live_settings.gms_api_key if st.provider == "gms" else live_settings.openai_api_key,
                "GMS_API_KEY" if st.provider == "gms" else "OPENAI_API_KEY")
    return create_llm(live_settings)


def test_llm_analysis_extracts_only_stated_conditions(llm):
    r = analyze("내일 12시 반에 역삼역에서 1만 5천원 이하로 점심 먹고 카공", date(2026, 11, 19), llm)
    assert r.decided_by == "llm" and r.intent == "recommend" and r.reason
    c = r.conditions
    assert c.preference.area == "역삼역" and c.constraint.budget_max == 15000
    assert c.base.visit_date == date(2026, 11, 20) and c.base.meal_time == time(12, 30)
    assert c.preference.prefer_short_walk is None and c.constraint.max_walk_m is None  # 말하지 않은 조건은 비움


def test_llm_analysis_smalltalk(llm):
    r = analyze("안녕!", date(2026, 11, 19), llm)
    assert r.decided_by == "llm" and r.intent == "smalltalk" and r.conditions.filled_fields() == {}


def test_agent_end_to_end_with_llm(live_settings, llm):
    agent = MainAgent(build_default_registry(live_settings), llm=llm)
    body = agent.run("역삼역에서 1만 5천원 이하로 12시에 점심 먹고 카공할래")["response"]
    assert body["decided_by"] == "llm" and body["recommendations"]
    assert body["message_by"] == "llm" and body["message"]
    # LLM 문장은 확정된 추천 이름을 벗어나지 않아야 한다
    assert body["recommendations"][0]["name"].split("(")[0] in body["message"]

"""F3005 사용자 요청 분석 - 단위 테스트 (규칙 분석 + LLM 경로 스텁)."""
from __future__ import annotations

from datetime import date, time

import pytest

from app.agent.analysis import analyze, parse_budget, parse_date, rule_analyze
from app.agent.conditions import AnalysisResult, Conditions

TODAY = date(2026, 11, 19)  # 목요일


def run(msg):
    return rule_analyze(msg, TODAY)


def test_scenario_a_basic():
    r = run("강남역에서 점심 먹고 카공할 건데 추천해줘")
    assert r.intent == "recommend" and r.decided_by == "rule" and r.reason
    f = r.conditions.filled_fields()
    assert f == {"base.meal_period": "점심", "preference.area": "강남역"}  # 없던 조건을 채우지 않음


def test_scenario_b_budget():
    r = run("역삼역에서 1만 5천 원 이하로 점심 먹고 카페 가고 싶어")
    assert r.conditions.preference.area == "역삼역"
    assert r.conditions.constraint.budget_max == 15000


def test_scenario_c_weather_and_walk():
    r = run("오늘 비가 오는데 강남역에서 점심 먹고 카공하고 싶어. 많이 걷기는 싫어.")
    c = r.conditions
    assert c.base.visit_date == TODAY
    assert c.preference.prefer_short_walk is True
    assert c.constraint.max_walk_m is None  # '많이 걷기 싫다'를 숫자로 만들지 않음
    assert r.user_reported_weather == "비"


def test_scenario_d_followup():
    r = run("같은 조건에서 한식 말고 일식으로 바꿔줘")
    assert r.intent == "recommend" and r.is_followup
    assert r.conditions.preference.food_type == "일식"
    assert r.conditions.preference.exclude_food_types == ["한식"]
    assert r.conditions.preference.area is None  # 직전 조건 병합은 F3010 에서


def test_scenario_e_save():
    assert run("이 코스로 저장해줘").intent == "save_plan"


@pytest.mark.parametrize("msg, intent", [("안녕!", "smalltalk"), ("고마워", "smalltalk"), ("사용법 알려줘", "help"),
                                         ("오늘 주식 어때?", "out_of_scope")])
def test_non_tool_intents(msg, intent):
    r = run(msg)
    assert r.intent == intent and r.conditions.filled_fields() == {}


@pytest.mark.parametrize("text, expected", [
    ("1만 5천 원 이하", 15000), ("15000원", 15000), ("15,000원 이내", 15000), ("만원 이하로", 10000),
    ("만오천원까지", 15000), ("2만원", 20000), ("1.2만원", 12000), ("8천원", 8000), ("예산은 12000", 12000),
    ("12시에 먹자", None), ("500m 이내", None),
])
def test_budget_parsing(text, expected):
    assert parse_budget(text) == expected


@pytest.mark.parametrize("text, expected", [
    ("오늘", TODAY), ("내일", date(2026, 11, 20)), ("모레", date(2026, 11, 21)), ("토요일", date(2026, 11, 21)),
    ("다음주 월요일", date(2026, 11, 23)), ("11월 25일", date(2026, 11, 25)), ("1월 3일", date(2027, 1, 3)), ("점심", None),
])
def test_date_parsing(text, expected):
    assert parse_date(text, TODAY) == expected


def test_times_meal_cafe_end():
    c = run("내일 12시 반에 강남역에서 점심 먹고 2시부터 카공해서 6시까지 있을래").conditions
    assert c.base.visit_date == date(2026, 11, 20)
    assert c.base.meal_time == time(12, 30)
    assert c.base.cafe_time == time(14, 0)
    assert c.constraint.end_by == time(18, 0)


def test_dinner_time_and_walk_limit():
    c = run("역삼역 저녁 7시, 도보 5분 이내 중식").conditions
    assert c.base.meal_time == time(19, 0) and c.base.meal_period == "저녁"
    assert c.constraint.max_walk_minutes == 5 and c.preference.food_type == "중식"
    c2 = run("강남역 300m 이내 분식").conditions
    assert c2.constraint.max_walk_m == 300 and c2.preference.food_type == "분식"


def test_health_flag_and_reset():
    r = run("처음부터 다시, 강남역 점심 추천해줘. 땅콩 알레르기 있어")
    assert r.reset is True and r.is_followup is False and r.mentions_health is True


def test_conditions_merge_only_updates_filled():
    prev = run("내일 12시 강남역에서 1만원 이하로 한식 점심").conditions
    upd = run("같은 조건에서 한식 말고 일식으로").conditions
    merged = prev.merged_with(upd)
    assert merged.preference.food_type == "일식"
    assert merged.constraint.budget_max == 10000 and merged.preference.area == "강남역"
    assert merged.base.visit_date == date(2026, 11, 20) and merged.base.meal_time == time(12, 0)


# ---------------------------------------------------------------- LLM 경로 (스텁, 실제 호출 아님)
class StubLLM:
    def __init__(self, result=None, error=None):
        self.result, self.error, self.messages = result, error, None

    def with_structured_output(self, schema):
        assert schema is AnalysisResult
        return self

    def invoke(self, messages):
        self.messages = messages
        if self.error:
            raise self.error
        return self.result


def test_llm_path_used_and_guarded():
    fake = AnalysisResult(intent="recommend", reason="추천 요청", decided_by="rule", conditions=Conditions.model_validate({
        "preference": {"area": "역삼역"}, "constraint": {"budget_max": 20000}, "base": {"meal_time": "12:00"}}))
    llm = StubLLM(result=fake)
    r = analyze("강남역 점심 추천", TODAY, llm)
    assert r.decided_by == "llm"
    assert "2026-11-19" in llm.messages[0][1]
    # 발화 근거가 없는 값(역삼역, 2만원, 12시)은 버림
    assert r.conditions.preference.area == "강남역"
    assert r.conditions.constraint.budget_max is None and r.conditions.base.meal_time is None


def test_llm_failure_falls_back_to_rule():
    r = analyze("강남역 점심 추천", TODAY, StubLLM(error=TimeoutError()))
    assert r.decided_by == "rule" and "LLM 분석 실패" in r.reason
    assert r.conditions.preference.area == "강남역"


def test_condition_only_message_is_recommend():
    r = run("강남역 1만원 이하")
    assert r.intent == "recommend" and r.conditions.constraint.budget_max == 10000


def test_llm_guard_drops_unstated_walk_preference_and_timezone():
    from datetime import timezone, timedelta

    kst = timezone(timedelta(hours=9))
    fake = AnalysisResult(intent="recommend", reason="r", decided_by="rule", conditions=Conditions.model_validate({
        "base": {"meal_time": time(12, 30, tzinfo=kst), "meal_period": "점심"},
        "preference": {"area": "역삼역", "prefer_short_walk": True}}))
    r = analyze("내일 12시 반에 역삼역에서 점심", TODAY, StubLLM(result=fake))
    assert r.conditions.preference.prefer_short_walk is None  # 발화에 근거 없음 (실제 GMS 응답 재현)
    assert r.conditions.base.meal_time == time(12, 30) and r.conditions.base.meal_time.tzinfo is None
    fake2 = AnalysisResult(intent="recommend", reason="r", decided_by="rule", conditions=Conditions.model_validate({
        "preference": {"area": "강남역", "prefer_short_walk": True}}))
    assert analyze("강남역 많이 걷기 싫어", TODAY, StubLLM(result=fake2)).conditions.preference.prefer_short_walk is True

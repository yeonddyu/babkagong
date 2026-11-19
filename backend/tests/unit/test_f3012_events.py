"""F3012 실행 이벤트 발행 - 단위 테스트."""
from __future__ import annotations

from app.agent.graph import MainAgent
from app.events.bus import Event, EventBus, RunPublisher
from tests.unit.agent_fixtures import TODAY, make_registry, make_session


def run(make_settings, msg, bus=None, session_id=None):
    agent = MainAgent(make_registry(make_settings, make_session()), today_fn=lambda: TODAY, bus=bus)
    return agent.run(msg, session_id=session_id)


def test_stage_and_tool_events_in_order(make_settings):
    bus = EventBus()
    got: list[Event] = []
    bus.subscribe(got.append)
    r = run(make_settings, "강남역 1만원 이하 12시 점심", bus=bus, session_id="sess-1")
    types = [e.type for e in got]
    assert types[0] == "run_start" and types[-1] == "run_end"
    assert [e.seq for e in got] == list(range(1, len(got) + 1))
    assert all(e.session_id == "sess-1" and e.run_id == r["run_id"] for e in got)
    stages = [e.stage for e in got if e.type == "stage_start"]
    assert stages == ["analyze", "plan", "execute", "judge", "respond"]
    # 각 단계 진입·종료 쌍
    assert [e.stage for e in got if e.type == "stage_end"] == stages
    # Tool 호출 요청·응답·소요 시간
    calls = [e for e in got if e.type == "tool_call"]
    results = [e for e in got if e.type == "tool_result"]
    assert len(calls) == len(results) > 0
    assert all("duration_ms" in e.payload and "ok" in e.payload for e in results)
    assert calls[0].payload["tool"] == "get_weather_context" and "args" in calls[0].payload
    assert r["events"] == [e.to_dict() for e in got]  # 응답에도 같은 이벤트 사본


def test_llm_decision_and_reason_recorded(make_settings):
    got: list[Event] = []
    bus = EventBus()
    bus.subscribe(got.append)
    run(make_settings, "안녕", bus=bus)
    decision = next(e for e in got if e.type == "llm_decision")
    assert decision.payload["decision"] == "intent=smalltalk" and decision.payload["reason"]
    assert decision.payload["decided_by"] in ("llm", "rule")
    end = next(e for e in got if e.type == "stage_end" and e.stage == "analyze")
    assert end.payload["intent"] == "smalltalk" and end.payload["reason"]  # 의도 분석 종료 이벤트에 의도·이유


def test_replan_event_published(make_settings):
    from tests.unit.test_f3002_restaurant_candidates import rt_row
    from tests.unit.agent_fixtures import YEOKSAM

    got: list[Event] = []
    bus = EventBus()
    bus.subscribe(got.append)
    rows = [rt_row(2, "스시하우스", 37.4983, 127.0279, cat="일식")] + YEOKSAM
    agent = MainAgent(make_registry(make_settings, make_session(rt_rows=rows)), today_fn=lambda: TODAY, bus=bus)
    agent.run("강남역 9천원 이하 점심")
    rp = [e for e in got if e.type == "replan"]
    assert rp and rp[0].payload["strategy"] == "adjacent_area" and rp[0].payload["count"] == 1


def test_agent_works_without_subscribers(make_settings):
    bus = EventBus()
    assert bus.subscriber_count == 0
    r = run(make_settings, "강남역 점심 추천", bus=bus)
    assert r["response"]["recommendations"] and r["events"]


def test_subscriber_failure_isolated(make_settings):
    bus = EventBus()

    def broken(_):
        raise RuntimeError("logger crashed")

    bus.subscribe(broken)
    r = run(make_settings, "강남역 점심 추천", bus=bus)
    assert r["response"]["recommendations"]


def test_publisher_does_not_know_subscribers():
    bus = EventBus()
    pub = RunPublisher(bus, "s", "r")
    e = pub.emit("tool_call", stage="execute", tool="x", args={"a": 1})
    assert e.seq == 1 and e.payload == {"tool": "x", "args": {"a": 1}}
    unsubscribe = bus.subscribe(lambda ev: None)
    unsubscribe()
    assert bus.subscriber_count == 0

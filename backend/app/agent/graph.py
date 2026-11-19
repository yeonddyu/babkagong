"""메인 Agent (LangGraph): 분석 → 계획 → 실행 → 판단 → (재계획 → 실행) → 응답.

재계획(F3009): 충족 후보가 0건일 때만, 상한 MAX_REPLANS(기본 3)까지. 키 누락처럼 다시 해도
같은 실패는 재계획하지 않는다. 이미 호출한 (tool, args) 결과는 ToolExecutor 캐시에서 재사용한다.
"""
from __future__ import annotations

import uuid
from dataclasses import asdict
from datetime import date, datetime
from typing import Any, Callable, TypedDict

from langgraph.graph import END, START, StateGraph

from app.agent.analysis import analyze
from app.agent.conditions import AnalysisResult, Conditions
from app.agent.execution import ExecutionData, ToolExecutor, run_cafes, run_candidates, run_details, run_weather
from app.agent.judge import Evaluation, cafe_radius, evaluate
from app.agent.memory import InMemoryMemoryStore, MemoryStore, build_memory, resolve_conditions
from app.agent.planning import CAFE_TARGETS, Plan, build_plan
from app.agent.respond import build_response
from app.datasets.cache import now_kst
from app.events.bus import EventBus, RunPublisher
from app.tools.registry import ToolRegistry


class AgentState(TypedDict, total=False):
    session_id: str
    run_id: str
    message: str
    area_hint: str | None
    previous: dict[str, Any] | None
    analysis: AnalysisResult
    conditions: Conditions
    changed_fields: list[str]
    used_previous: bool
    plan: Plan
    executor: ToolExecutor
    data: ExecutionData
    evaluation: Evaluation
    search_area: str | None
    replan_count: int
    replan_history: list[dict[str, Any]]
    stop_reason: str | None
    judge_route: str
    publisher: RunPublisher
    response: dict[str, Any]


class MainAgent:
    def __init__(
        self,
        registry: ToolRegistry,
        *,
        llm: Any | None = None,
        max_replans: int = 3,
        memory: MemoryStore | None = None,
        bus: EventBus | None = None,
        today_fn: Callable[[], date] = lambda: now_kst().date(),
        now_fn: Callable[[], datetime] = now_kst,
    ):
        self.registry = registry
        self.llm = llm
        self.max_replans = max_replans
        self.memory = memory or InMemoryMemoryStore()
        self.bus = bus or EventBus()  # 구독자가 없어도 동작 (발행자는 구독자를 모름)
        self.today_fn = today_fn
        self.now_fn = now_fn
        self.graph = self._build()

    # ------------------------------------------------------------ graph
    def _build(self):
        g = StateGraph(AgentState)
        g.add_node("analyze", self._stage("analyze", self.analyze_node))
        g.add_node("plan", self._stage("plan", self.plan_node))
        g.add_node("execute", self._stage("execute", self.execute_node))
        g.add_node("judge", self._stage("judge", self.judge_node))
        g.add_node("replan", self._stage("replan", self.replan_node))
        g.add_node("respond", self._stage("respond", self.respond_node))
        g.add_edge(START, "analyze")
        g.add_conditional_edges("analyze", self._after_analyze, {"plan": "plan", "respond": "respond"})
        g.add_conditional_edges("plan", self._after_plan, {"execute": "execute", "respond": "respond"})
        g.add_edge("execute", "judge")
        g.add_conditional_edges("judge", self._after_judge, {"replan": "replan", "respond": "respond"})
        g.add_conditional_edges("replan", self._after_replan, {"execute": "execute", "respond": "respond"})
        g.add_edge("respond", END)
        return g.compile()

    def _stage(self, name: str, fn: Callable[[AgentState], dict[str, Any]]) -> Callable[[AgentState], dict[str, Any]]:
        """노드 진입·종료를 이벤트로 발행하는 래퍼 (F3012)."""

        def wrapped(state: AgentState) -> dict[str, Any]:
            pub: RunPublisher = state["publisher"]
            pub.emit("stage_start", stage=name)
            update = fn(state)
            pub.emit("stage_end", stage=name, **self._stage_summary(name, {**state, **update}))
            return update

        return wrapped

    @staticmethod
    def _stage_summary(name: str, st: dict[str, Any]) -> dict[str, Any]:
        if name == "analyze":
            a: AnalysisResult = st["analysis"]
            return {"intent": a.intent, "reason": a.reason, "decided_by": a.decided_by,
                    "conditions": st["conditions"].filled_fields(), "changed_fields": st.get("changed_fields", [])}
        if name == "plan":
            p: Plan = st["plan"]
            return {"mode": p.mode, "tools": [x.tool for x in p.steps], "reason": p.reason}
        if name == "execute":
            d: ExecutionData = st["data"]
            return {"candidates": len(d.candidates), "detailed": d.detailed_count, "cafes_for": len(d.cafes),
                    "weather": d.weather is not None, "area": st.get("search_area") or st["conditions"].preference.area}
        if name == "judge":
            ev: Evaluation = st["evaluation"]
            return {"satisfied": len(ev.satisfied), "excluded": len(ev.excluded), "next": st.get("judge_route"),
                    "stop_reason": st.get("stop_reason")}
        if name == "replan":
            return {"replan": (st.get("replan_history") or [{}])[-1]}
        if name == "respond":
            r = st["response"]
            return {"recommendations": len(r.get("recommendations", [])), "message_by": r.get("message_by")}
        return {}

    def graph_structure(self) -> dict[str, list[str]]:
        drawable = self.graph.get_graph()
        return {"nodes": [n for n in drawable.nodes], "edges": [f"{e.source}->{e.target}" for e in drawable.edges]}

    # ------------------------------------------------------------ nodes
    def analyze_node(self, state: AgentState) -> dict[str, Any]:
        analysis = analyze(state["message"], self.today_fn(), self.llm)
        conditions, changed, used_previous = resolve_conditions(analysis, state.get("previous"))
        if analysis.intent == "recommend" and state.get("area_hint") and conditions.preference.area is None:
            conditions = conditions.model_copy(deep=True)
            conditions.preference.area = state["area_hint"]
            changed.append("preference.area")
        state["publisher"].emit("llm_decision", stage="analyze", decision=f"intent={analysis.intent}", reason=analysis.reason,
                                decided_by=analysis.decided_by, used_previous=used_previous)
        return {"analysis": analysis, "conditions": conditions, "changed_fields": changed, "used_previous": used_previous}

    def _after_analyze(self, state: AgentState) -> str:
        return "plan" if state["analysis"].intent == "recommend" else "respond"

    def plan_node(self, state: AgentState) -> dict[str, Any]:
        plan = build_plan(state["analysis"], state["conditions"], self.today_fn())
        state["publisher"].emit("plan_created", stage="plan", mode=plan.mode, reason=plan.reason,
                                steps=[s.model_dump() for s in plan.steps], excluded_tools=plan.excluded_tools, missing=plan.missing)
        return {"plan": plan}

    def _after_plan(self, state: AgentState) -> str:
        return "execute" if state["plan"].mode == "tools" else "respond"

    def execute_node(self, state: AgentState) -> dict[str, Any]:
        ex: ToolExecutor = state["executor"]
        data: ExecutionData = state["data"]
        cond: Conditions = state["conditions"]
        area = state.get("search_area") or cond.preference.area
        tools = [s.tool for s in state["plan"].steps]
        today = self.today_fn()
        if "get_weather_context" in tools and data.weather is None and data.weather_error is None:
            run_weather(ex, data, cond, area, today)
        if area not in data.areas_searched:
            run_candidates(ex, data, cond, area)
        if data.candidates:
            run_details(ex, data)
            self._search_cafes(ex, data, cond, today)
        return {}

    def _search_cafes(self, ex: ToolExecutor, data: ExecutionData, cond: Conditions, today: date) -> None:
        """판단 기준을 충족한 상위 식당만 주변 카페를 찾는다 (이미 찾은 식당은 제외)."""
        preliminary = evaluate(data, cond, today)
        by_key = {f"{c['source']}:{c['source_id']}": c for c in data.candidates}
        targets = [by_key[e.key] for e in preliminary.satisfied[:CAFE_TARGETS]
                   if e.key not in data.cafes and e.key not in data.cafe_errors]
        run_cafes(ex, data, targets, cafe_radius(cond, data.weather))

    def judge_node(self, state: AgentState) -> dict[str, Any]:
        ev = evaluate(state["data"], state["conditions"], self.today_fn())
        route, stop_reason = self._replan_decision(state, ev)
        return {"evaluation": ev, "judge_route": route, "stop_reason": stop_reason}

    def _replan_decision(self, state: AgentState, ev: Evaluation) -> tuple[str, str | None]:
        if ev.satisfied:
            return "respond", None
        data: ExecutionData = state["data"]
        if ev.hard_failure:
            return "respond", f"재시도해도 같은 실패({ev.hard_failure['code']})라 재계획하지 않음"
        if data.candidate_error and not data.candidates and data.candidate_error.get("code") != "NO_RESULT":
            return "respond", f"음식점 후보 조회 실패({data.candidate_error['code']})로 재계획하지 않음"
        if state.get("replan_count", 0) >= self.max_replans:
            return "respond", f"재계획 상한({self.max_replans}회)에 도달"
        return "replan", None

    def _after_judge(self, state: AgentState) -> str:
        return state["judge_route"]

    def replan_node(self, state: AgentState) -> dict[str, Any]:
        """충족 후보가 없을 때 대안 전략을 고른다. 이미 확보한 결과는 그대로 둔다."""
        data: ExecutionData = state["data"]
        cond: Conditions = state["conditions"]
        count = state.get("replan_count", 0) + 1
        history = list(state.get("replan_history", []))
        ev: Evaluation = state["evaluation"]
        reason = f"충족 후보 0건 (판단한 {len(ev.excluded)}곳 모두 제외)"
        if data.detailed_count < len(data.candidates):
            strategy = "next_batch"
            detail = f"상세정보를 아직 조회하지 않은 후보 {data.detailed_count + 1}~{min(len(data.candidates), data.detailed_count + 6)}번째 조회"
            update: dict[str, Any] = {}
        else:
            current = state.get("search_area") or cond.preference.area
            other = "역삼역" if current == "강남역" else "강남역"
            if other not in data.areas_searched:
                strategy = "adjacent_area"
                detail = f"{current} 후보를 모두 확인해 인접한 {other} 주변을 같은 조건으로 탐색"
                update = {"search_area": other}
            else:
                strategy = "none"
                detail = "더 탐색할 후보와 지역이 없음"
                update = {"stop_reason": "탐색 가능한 대안이 없음"}
        history.append({"count": count, "reason": reason, "strategy": strategy, "detail": detail})
        state["publisher"].emit("replan", stage="replan", count=count, reason=reason, strategy=strategy, detail=detail,
                                limit=self.max_replans)
        return {"replan_count": count, "replan_history": history, **update}

    def _after_replan(self, state: AgentState) -> str:
        return "respond" if state["replan_history"][-1]["strategy"] == "none" else "execute"

    def respond_node(self, state: AgentState) -> dict[str, Any]:
        body = build_response(
            state["analysis"], state["conditions"], state.get("plan"), state.get("data"), state.get("evaluation"),
            state.get("executor"), state.get("replan_history", []), state.get("stop_reason"),
            state.get("changed_fields", []), self.llm,
        )
        return {"response": body}

    # ------------------------------------------------------------ run
    def run(self, message: str, *, session_id: str | None = None, area_hint: str | None = None) -> dict[str, Any]:
        session_id = session_id or uuid.uuid4().hex
        run_id = uuid.uuid4().hex
        publisher = RunPublisher(self.bus, session_id, run_id, clock=self.now_fn)
        previous = self._load_memory(session_id)
        publisher.emit("run_start", message=message, area_hint=area_hint, has_previous=previous is not None)
        state: AgentState = {
            "session_id": session_id,
            "previous": previous,
            "run_id": run_id,
            "message": message,
            "area_hint": area_hint,
            "executor": ToolExecutor(self.registry, emit=publisher.emit),
            "data": ExecutionData(),
            "search_area": None,
            "replan_count": 0,
            "replan_history": [],
            "stop_reason": None,
            "publisher": publisher,
        }
        final = self.graph.invoke(state)
        ex: ToolExecutor = final["executor"]
        self._save_memory(final, previous)
        publisher.emit("run_end", intent=final["analysis"].intent,
                       recommendations=len(final["response"].get("recommendations", [])),
                       tool_calls=ex.fresh_call_count, replans=len(final.get("replan_history", [])))
        return {
            "session_id": final["session_id"],
            "run_id": final["run_id"],
            "analysis": final["analysis"],
            "conditions": final["conditions"],
            "changed_fields": final.get("changed_fields", []),
            "used_previous": final.get("used_previous", False),
            "previous": previous,
            "plan": final.get("plan"),
            "tool_calls": [asdict(c) for c in ex.calls],
            "data": final["data"],
            "evaluation": final.get("evaluation"),
            "replans": final.get("replan_history", []),
            "stop_reason": final.get("stop_reason"),
            "response": final["response"],
            "events": [e.to_dict() for e in publisher.events],
        }

    # ------------------------------------------------------------ memory
    def _load_memory(self, session_id: str) -> dict[str, Any] | None:
        try:
            return self.memory.load(session_id)
        except Exception:  # noqa: BLE001 - 맥락 저장소 장애가 대화를 막지 않도록
            return None

    def _save_memory(self, final: AgentState, previous: dict[str, Any] | None) -> None:
        analysis: AnalysisResult = final["analysis"]
        if analysis.intent not in ("recommend",) and previous is not None:
            return  # 인사·사용법 등은 직전 맥락을 유지
        try:
            self.memory.save(final["session_id"], build_memory(
                final["conditions"], analysis.intent, final["response"]["recommendations"], previous))
        except Exception:  # noqa: BLE001
            pass

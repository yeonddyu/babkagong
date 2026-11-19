"""메인 Agent (LangGraph): 분석 → 계획 → 실행 → 판단 → 응답."""
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
from app.agent.planning import CAFE_TARGETS, Plan, build_plan
from app.datasets.cache import now_kst
from app.tools.registry import ToolRegistry


class AgentState(TypedDict, total=False):
    session_id: str
    run_id: str
    message: str
    area_hint: str | None
    previous: dict[str, Any] | None
    analysis: AnalysisResult
    conditions: Conditions
    plan: Plan
    executor: ToolExecutor
    data: ExecutionData
    evaluation: Evaluation
    response: dict[str, Any]


class MainAgent:
    def __init__(
        self,
        registry: ToolRegistry,
        *,
        llm: Any | None = None,
        today_fn: Callable[[], date] = lambda: now_kst().date(),
        now_fn: Callable[[], datetime] = now_kst,
    ):
        self.registry = registry
        self.llm = llm
        self.today_fn = today_fn
        self.now_fn = now_fn
        self.graph = self._build()

    # ------------------------------------------------------------ graph
    def _build(self):
        g = StateGraph(AgentState)
        g.add_node("analyze", self.analyze_node)
        g.add_node("plan", self.plan_node)
        g.add_node("execute", self.execute_node)
        g.add_node("judge", self.judge_node)
        g.add_node("respond", self.respond_node)
        g.add_edge(START, "analyze")
        g.add_conditional_edges("analyze", self._after_analyze, {"plan": "plan", "respond": "respond"})
        g.add_conditional_edges("plan", self._after_plan, {"execute": "execute", "respond": "respond"})
        g.add_edge("execute", "judge")
        g.add_edge("judge", "respond")
        g.add_edge("respond", END)
        return g.compile()

    def graph_structure(self) -> dict[str, list[str]]:
        drawable = self.graph.get_graph()
        return {"nodes": [n for n in drawable.nodes], "edges": [f"{e.source}->{e.target}" for e in drawable.edges]}

    # ------------------------------------------------------------ nodes
    def analyze_node(self, state: AgentState) -> dict[str, Any]:
        analysis = analyze(state["message"], self.today_fn(), self.llm)
        conditions = analysis.conditions
        if state.get("area_hint") and conditions.preference.area is None:
            conditions = conditions.model_copy(deep=True)
            conditions.preference.area = state["area_hint"]
        return {"analysis": analysis, "conditions": conditions}

    def _after_analyze(self, state: AgentState) -> str:
        return "plan" if state["analysis"].intent == "recommend" else "respond"

    def plan_node(self, state: AgentState) -> dict[str, Any]:
        return {"plan": build_plan(state["analysis"], state["conditions"], self.today_fn())}

    def _after_plan(self, state: AgentState) -> str:
        return "execute" if state["plan"].mode == "tools" else "respond"

    def execute_node(self, state: AgentState) -> dict[str, Any]:
        ex: ToolExecutor = state["executor"]
        data: ExecutionData = state["data"]
        cond: Conditions = state["conditions"]
        area = cond.preference.area
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
        return {"evaluation": evaluate(state["data"], state["conditions"], self.today_fn())}

    def respond_node(self, state: AgentState) -> dict[str, Any]:
        analysis: AnalysisResult = state["analysis"]
        data: ExecutionData | None = state.get("data")
        ev: Evaluation | None = state.get("evaluation")
        recs = []
        if data and ev:
            for e in ev.satisfied[:CAFE_TARGETS]:
                recs.append({"evaluation": e, "cafes": (data.cafes.get(e.key) or {}).get("cafes", [])})
        return {"response": {"intent": analysis.intent, "recommendations": recs,
                             "excluded": [e for e in (ev.excluded if ev else [])]}}

    # ------------------------------------------------------------ run
    def run(self, message: str, *, session_id: str | None = None, area_hint: str | None = None) -> dict[str, Any]:
        state: AgentState = {
            "session_id": session_id or uuid.uuid4().hex,
            "run_id": uuid.uuid4().hex,
            "message": message,
            "area_hint": area_hint,
            "executor": ToolExecutor(self.registry),
            "data": ExecutionData(),
        }
        final = self.graph.invoke(state)
        ex: ToolExecutor = final["executor"]
        return {
            "session_id": final["session_id"],
            "run_id": final["run_id"],
            "analysis": final["analysis"],
            "conditions": final["conditions"],
            "plan": final.get("plan"),
            "tool_calls": [asdict(c) for c in ex.calls],
            "data": final["data"],
            "evaluation": final.get("evaluation"),
            "response": final["response"],
        }

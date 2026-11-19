"""F3005 사용자 요청 분석.

- LLM(OpenAI) 이 있으면 구조화 출력으로 의도·조건을 추출하고, 숫자·지역 같은 값은
  발화에 근거가 있을 때만 받아들인다 (지어낸 값 차단).
- LLM 이 없거나 실패하면 규칙 기반 분석기로 처리한다. 어떤 경로인지 decided_by 로 남긴다.
- 발화에 없는 조건은 채우지 않는다.
"""
from __future__ import annotations

import logging
import re
from datetime import date, time, timedelta
from typing import Any

from app.agent.conditions import AnalysisResult, Conditions

logger = logging.getLogger(__name__)

WEEKDAYS = ["월", "화", "수", "목", "금", "토", "일"]

FOOD_KEYWORDS: dict[str, tuple[str, ...]] = {
    "한식": ("한식", "백반", "국밥", "김치찌개", "된장찌개", "비빔밥", "삼겹살", "갈비", "냉면", "칼국수"),
    "중식": ("중식", "중국집", "중국 음식", "짜장", "짬뽕", "마라", "탕수육"),
    "일식": ("일식", "초밥", "스시", "라멘", "돈카츠", "돈까스", "우동", "소바", "덮밥"),
    "양식": ("양식", "파스타", "피자", "스테이크", "햄버거", "버거", "리조또"),
    "분식": ("분식", "떡볶이", "김밥", "라볶이", "순대"),
}
RECOMMEND_WORDS = ("추천", "먹", "점심", "저녁", "아침", "식사", "카공", "카페", "식당", "맛집", "밥", "코스", "바꿔", "말고", "대신")
GREETING_WORDS = ("안녕", "하이", "hello", "hi", "반가", "고마워", "감사", "ㅎㅇ")
HELP_WORDS = ("사용법", "어떻게 써", "어떻게 사용", "뭘 할 수", "무엇을 할 수", "도움말", "기능이 뭐", "뭐 할 수")
SAVE_WORDS = ("저장", "등록해", "담아")
FOLLOWUP_WORDS = ("같은 조건", "그대로", "말고", "바꿔", "대신", "다른 곳", "다른 데", "다른 식당", "다른 카페", "이번엔", "그럼")
RESET_WORDS = ("처음부터", "새로 추천", "초기화", "새로 시작", "리셋")
SHORT_WALK_PATTERN = re.compile(r"걷기\s*(?:는|도|가)?\s*싫|많이\s*(?:안|못)\s*걷|조금만\s*걷|가까운|가깝게|멀지\s*않|안\s*먼|근처로")
HEALTH_WORDS = ("알레르기", "알러지", "당뇨", "다이어트", "임신", "질환", "건강", "저염", "글루텐")
WEATHER_WORDS = {"비": ("비가", "비 오", "비오", "우산"), "눈": ("눈이", "눈 오", "눈오"), "추움": ("춥", "추워"), "더움": ("덥", "더워")}


# ---------------------------------------------------------------- 날짜·시각
def parse_date(text: str, today: date) -> date | None:
    if "오늘" in text:
        return today
    if "내일" in text:
        return today + timedelta(days=1)
    if "모레" in text:
        return today + timedelta(days=2)
    m = re.search(r"(\d{1,2})\s*월\s*(\d{1,2})\s*일", text) or re.search(r"(?<!\d)(\d{1,2})/(\d{1,2})(?!\d)", text)
    if m:
        month, day = int(m.group(1)), int(m.group(2))
        try:
            candidate = date(today.year, month, day)
        except ValueError:
            return None
        return candidate if candidate >= today else date(today.year + 1, month, day)
    m = re.search(r"(다음\s*주|이번\s*주)?\s*([월화수목금토일])요일", text)
    if m:
        target = WEEKDAYS.index(m.group(2))
        if m.group(1) and "다음" in m.group(1):
            monday_next = today + timedelta(days=7 - today.weekday())
            return monday_next + timedelta(days=target)
        delta = (target - today.weekday()) % 7
        return today + timedelta(days=delta)
    return None


_TIME = re.compile(
    r"(오전|오후|낮|저녁|밤|새벽)?\s*(\d{1,2})\s*(?:시\s*(?:(\d{1,2})\s*분|(반))?|:(\d{2}))"
)


def _to_time(ampm: str | None, hour: int, minute: int, period_hint: str | None) -> time | None:
    if ampm in ("오후", "저녁", "밤") and hour < 12:
        hour += 12
    elif ampm in ("오전", "새벽") and hour == 12:
        hour = 0
    elif ampm is None and 1 <= hour <= 6:
        hour += 12  # 식사·카공 맥락에서 1~6시는 오후로 해석 (분석 규칙)
    elif ampm is None and period_hint == "저녁" and 7 <= hour <= 11:
        hour += 12
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        return None
    return time(hour, minute)


def parse_times(text: str, period_hint: str | None) -> list[tuple[int, int, time]]:
    """[(시작 위치, 끝 위치, 시각)]"""
    out = []
    for m in _TIME.finditer(text):
        hour = int(m.group(2))
        minute = int(m.group(3) or m.group(5) or (30 if m.group(4) else 0))
        t = _to_time(m.group(1), hour, minute, period_hint)
        if t:
            out.append((m.start(), m.end(), t))
    return out


# ---------------------------------------------------------------- 금액·거리
_MONEY = re.compile(r"(\d+(?:\.\d+)?)?\s*만\s*(?:(\d)\s*천|(\d{1,4}))?\s*원?|(\d{1,3}(?:,\d{3})+|\d{4,7})\s*원?|(\d)\s*천\s*원")
_KOR_NUM = {"일": 1, "이": 2, "삼": 3, "사": 4, "오": 5, "육": 6, "칠": 7, "팔": 8, "구": 9}


def _normalize_korean_money(text: str) -> str:
    # "만오천원" → "1만 5천원", "만원" → "1만원", "2만 5천" 유지
    text = re.sub(r"(?<![\d.])만\s*([일이삼사오육칠팔구])\s*천", lambda m: f"1만 {_KOR_NUM[m.group(1)]}천", text)
    text = re.sub(r"(\d)\s*만\s*([일이삼사오육칠팔구])\s*천", lambda m: f"{m.group(1)}만 {_KOR_NUM[m.group(2)]}천", text)
    text = re.sub(r"(?<![\d.])만\s*원", "1만원", text)
    return text


def parse_budget(text: str) -> int | None:
    norm = _normalize_korean_money(text)
    for m in _MONEY.finditer(norm):
        if m.group(4):
            value = int(m.group(4).replace(",", ""))
        elif m.group(5):
            value = int(m.group(5)) * 1000
        elif m.group(1):
            value = int(float(m.group(1)) * 10000)
            if m.group(2):
                value += int(m.group(2)) * 1000
            elif m.group(3):
                value += int(m.group(3))
        else:
            continue
        # 금액 표현 주변에 예산 의미가 있거나 '원' 이 붙은 경우만 인정
        window = norm[m.start(): m.end() + 8]
        if "원" in window or any(w in window for w in ("이하", "이내", "까지", "안으로", "아래")) or "예산" in norm:
            if 1000 <= value <= 500000:
                return value
    return None


def parse_walk(text: str) -> tuple[int | None, int | None]:
    m = re.search(r"(\d{2,5})\s*(?:m|미터)\s*(?:이내|이하|안|까지)?", text)
    meters = int(m.group(1)) if m else None
    m = re.search(r"(?:도보|걸어서)\s*(\d{1,2})\s*분|(\d{1,2})\s*분\s*(?:이내|안|거리|이하)", text)
    minutes = int(m.group(1) or m.group(2)) if m else None
    return meters, minutes


# ---------------------------------------------------------------- 규칙 기반 분석
def _food(text: str) -> tuple[str | None, list[str]]:
    excluded: list[str] = []
    for ftype, words in FOOD_KEYWORDS.items():
        for w in words:
            if re.search(re.escape(w) + r"\s*(?:은|는|이|가)?\s*(?:말고|빼고|제외|싫)", text):
                excluded.append(ftype)
                break
    chosen = None
    best_pos = None
    for ftype, words in FOOD_KEYWORDS.items():
        if ftype in excluded:
            continue
        for w in words:
            pos = text.find(w)
            if pos >= 0 and (best_pos is None or pos < best_pos):
                chosen, best_pos = ftype, pos
    return chosen, excluded


def rule_analyze(message: str, today: date) -> AnalysisResult:
    text = message.strip()
    low = text.lower()
    has_reco = (any(w in text for w in RECOMMEND_WORDS) or any(any(w in text for w in ws) for ws in FOOD_KEYWORDS.values())
                or "강남" in text or "역삼" in text or parse_budget(text) is not None)
    reset = any(w in text for w in RESET_WORDS)

    if any(w in text for w in SAVE_WORDS) and any(w in text for w in ("코스", "계획", "이거", "이걸", "그거", "일정", "추천")):
        intent, reason = "save_plan", "저장 요청 표현('저장' + 코스/계획)이 있어 직전 추천을 계획으로 저장하는 요청으로 판단"
    elif any(w in text for w in HELP_WORDS):
        intent, reason = "help", "사용법·기능 질문 표현이 있어 Tool 호출이 필요 없는 안내 요청으로 판단"
    elif has_reco:
        intent, reason = "recommend", "식사·카공·추천 관련 표현이 있어 음식점·카페 추천 요청으로 판단"
    elif any(w in low for w in GREETING_WORDS):
        intent, reason = "smalltalk", "인사·감사 표현만 있어 Tool 호출이 필요 없는 대화로 판단"
    else:
        intent, reason = "out_of_scope", "식사·카페 추천과 관련된 표현을 찾지 못함"

    c = Conditions()
    period = "점심" if "점심" in text else "저녁" if "저녁" in text else "아침" if "아침" in text else None
    c.base.meal_period = period
    c.base.visit_date = parse_date(text, today)
    times = parse_times(text, period)
    end_by = None
    meal_time = cafe_time = None
    for start, end, t in times:
        after = text[end: end + 8]
        if "까지" in after:
            end_by = t
        elif re.match(r"\s*(?:부터|에)?\s*(?:카공|카페)", after) or ("먹고" in text[:start] and meal_time is not None):
            cafe_time = t
        elif meal_time is None:
            meal_time = t
        elif cafe_time is None:
            cafe_time = t
    c.base.meal_time, c.base.cafe_time = meal_time, cafe_time
    c.constraint.end_by = end_by

    c.preference.area = "강남역" if "강남" in text else "역삼역" if "역삼" in text else None
    c.preference.food_type, c.preference.exclude_food_types = _food(text)
    if SHORT_WALK_PATTERN.search(text):
        c.preference.prefer_short_walk = True
    c.constraint.budget_max = parse_budget(text)
    c.constraint.max_walk_m, c.constraint.max_walk_minutes = parse_walk(text)

    if intent in ("smalltalk", "help", "out_of_scope"):
        c = Conditions()  # Tool 이 필요 없는 요청은 조건을 추출하지 않는다
    weather = next((label for label, words in WEATHER_WORDS.items() if any(w in text for w in words)), None)
    return AnalysisResult(
        intent=intent, reason=reason, decided_by="rule", conditions=c,
        is_followup=any(w in text for w in FOLLOWUP_WORDS) and not reset,
        reset=reset, mentions_health=any(w in text for w in HEALTH_WORDS),
        user_reported_weather=weather,
    )


# ---------------------------------------------------------------- LLM 분석
LLM_SYSTEM = """너는 강남역·역삼역 식사+카공 카페 추천 서비스 '밥카공'의 요청 분석기다.
사용자 발화에서 의도와 조건을 추출한다. 규칙:
- intent: recommend(식사/카페 추천·조건 변경), smalltalk(인사), help(사용법), save_plan(직전 추천 저장), out_of_scope
- 발화에 명시된 값만 채운다. 언급하지 않은 날짜·시각·예산·거리·지역·음식 종류는 반드시 null.
- visit_date 는 오늘({today}, {weekday}요일) 기준으로 계산한 YYYY-MM-DD.
- budget_max 는 1인 메뉴 상한 금액(원, 정수). max_walk_m 은 미터.
- '많이 걷기 싫다/가까운 곳' 은 prefer_short_walk=true (숫자로 바꾸지 말 것).
- 'X 말고 Y' 는 food_type=Y, exclude_food_types=[X].
- reason 에 의도를 그렇게 판단한 이유를 한 문장으로 쓴다."""


def _evidence_guard(result: AnalysisResult, message: str, rule: AnalysisResult) -> AnalysisResult:
    """LLM 이 발화 근거 없이 채운 값은 규칙 분석값(없으면 None)으로 되돌린다."""
    c = result.conditions
    if c.preference.area and c.preference.area[:2] not in message:
        c.preference.area = rule.conditions.preference.area
    if c.constraint.budget_max and rule.conditions.constraint.budget_max is None and not re.search(
            r"\d\s*(?:원|만|천)|만\s*원|[일이삼사오육칠팔구]\s*천\s*원", message):
        c.constraint.budget_max = None
    if c.constraint.max_walk_m and not re.search(r"\d", message):
        c.constraint.max_walk_m = None
    if c.base.visit_date and rule.conditions.base.visit_date is None and not re.search(r"\d|오늘|내일|모레|요일", message):
        c.base.visit_date = None
    if (c.base.meal_time or c.base.cafe_time) and not re.search(r"\d", message):
        c.base.meal_time = c.base.cafe_time = None
    if c.constraint.end_by and not re.search(r"\d", message):
        c.constraint.end_by = None
    # 시각 표현이 하나뿐이면 카페 시각을 따로 정할 근거가 없다 (실제 GMS 가 '12시 점심'에서 카페 13:00 을 만든 사례)
    time_mentions = parse_times(message, rule.conditions.base.meal_period)
    if c.base.cafe_time and rule.conditions.base.cafe_time is None and len(time_mentions) < 2:
        c.base.cafe_time = None
    if c.constraint.end_by and rule.conditions.constraint.end_by is None and not re.search(r"까지|전에|안에|끝나", message):
        c.constraint.end_by = None
    if c.constraint.max_walk_minutes and not re.search(r"\d", message):
        c.constraint.max_walk_minutes = None
    # '가까운 곳/많이 걷기 싫다' 표현이 없는데 도보 선호를 넣은 경우 제거 (실제 GMS 응답에서 확인된 문제)
    if c.preference.prefer_short_walk and not SHORT_WALK_PATTERN.search(message):
        c.preference.prefer_short_walk = None
    if c.base.meal_period and c.base.meal_period not in message:
        c.base.meal_period = rule.conditions.base.meal_period
    # LLM 이 시각에 시간대(+09:00)를 붙여 주면 다른 시각과 비교할 수 없으므로 떼어 낸다
    for group, name in (("base", "meal_time"), ("base", "cafe_time"), ("constraint", "end_by")):
        value = getattr(getattr(c, group), name)
        if value is not None and value.tzinfo is not None:
            setattr(getattr(c, group), name, value.replace(tzinfo=None))
    return result


def analyze(message: str, today: date, llm: Any | None = None) -> AnalysisResult:
    rule = rule_analyze(message, today)
    if llm is None:
        return rule
    try:
        structured = llm.with_structured_output(AnalysisResult)
        prompt = LLM_SYSTEM.format(today=today.isoformat(), weekday=WEEKDAYS[today.weekday()])
        result: AnalysisResult = structured.invoke([("system", prompt), ("human", message)])
        result.decided_by = "llm"
        return _evidence_guard(result, message, rule)
    except Exception as exc:  # noqa: BLE001 - LLM 실패 시 규칙 분석으로 대체
        logger.warning("LLM 분석 실패, 규칙 분석으로 대체: %s", type(exc).__name__)
        rule.reason = f"LLM 분석 실패({type(exc).__name__})로 규칙 분석 사용: " + rule.reason
        return rule

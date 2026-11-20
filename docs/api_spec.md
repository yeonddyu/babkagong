# 백엔드 API 명세 (F3017)

Base: `http://localhost:8000`, 문서: `/docs` (Swagger), `/openapi.json`

| 메서드 | 경로 | 설명 | 요구사항 |
|---|---|---|---|
| GET | `/api/stations` | 서비스 역 목록 (역삼역 주변 6곳) `{stations:[{name, lines, latitude, longitude}], complete}` | - |
| GET | `/api/health` | 서버 상태, API 키 **존재 여부**(값 미노출), LLM 사용 가능 여부 | F3019 |
| POST | `/api/chat` | 대화 요청 → Agent 실행 결과 + 실행 이벤트 | F3005~F3012 |
| GET | `/api/plans` | 계획 목록 (`?date=YYYY-MM-DD`) | F3015 |
| POST | `/api/plans` | 계획 저장 → `{plan, conflicts[]}` | F3015 |
| GET | `/api/plans/{id}` | 계획 상세 | F3015 |
| PUT | `/api/plans/{id}` | 계획 수정 → `{plan, conflicts[]}` | F3016 |
| DELETE | `/api/plans/{id}` | 계획 삭제 | F3016 |
| GET | `/api/logs` | 세션별 실행 로그 목록 | F3014 |
| GET | `/api/logs/{session_id}` | 세션 실행 로그 상세 (seq 순) | F3014 |
| DELETE | `/api/logs/{session_id}` | 세션 실행 로그 삭제 | F3014 |

실행 로그 수정(PUT/PATCH) 경로는 두지 않는다.

## POST /api/chat
요청
```json
{"session_id": "선택, 없으면 새로 발급", "message": "강남역에서 점심 먹고 카공할 건데 추천해줘", "area": "서비스 역 이름(선택, UI 선택값, 서비스 역이 아니면 무시)"}
```
응답 (주요 필드)
```json
{
  "session_id": "...", "run_id": "...",
  "intent": "recommend", "message": "사용자에게 보여줄 문장",
  "origin": {"kind": "station|exit", "label": "강남역 11번 출구", "latitude": 0.0, "longitude": 0.0, "source": "카카오 로컬 '강남역 2호선 11번출구'"} | null,
  "summary": "대화창용 짧은 요약 (코드 생성: 코스 개수·1순위 식당·첫 카페·거리) | null (추천이 없거나 추천 의도가 아니면)",
  "conditions": {"base": {...}, "preference": {...}, "constraint": {...}, "missing": [...]},
  "weather": {...} | null,
  "recommendations": [{"restaurant": {...}, "cafes": [...], "reasons": [...], "unverified": [...], "score": 0}],
  "excluded": [{"name": "...", "source": "...", "reason": "..."}],
  "criteria": ["판단 기준 문장"],
  "evidence": [{"tool": "...", "ok": true, "summary": "..."}],
  "replans": [{"count": 1, "reason": "...", "strategy": "..."}],
  "notices": ["API 키 누락·Tool 실패 안내"],
  "saved_plan": {...} | null, "plan_conflicts": [...],
  "events": [{"seq": 1, "type": "stage_start", "stage": "analyze", ...}]
}
```

## POST /api/plans
```json
{"title": "강남 점심+카공", "plan_date": "2026-11-20", "start_time": "12:00", "end_time": "15:00",
 "area": "강남역", "restaurant_name": "...", "restaurant_source": "...", "restaurant_source_id": "...",
 "restaurant_address": "...", "cafe_name": "...", "cafe_place_id": "...", "cafe_address": "...", "cafe_url": "...", "memo": ""}
```
응답 201: `{"plan": {..., "id": 1, "created_at": "..."}, "conflicts": [{"id": 2, "title": "...", "start_time": "...", "end_time": "..."}]}`

오류 응답 형식: `{"detail": {"code": "INVALID_INPUT|NOT_FOUND|INTERNAL_ERROR", "message": "사용자용 문장"}}` — 내부 예외·키 미노출 (NF3002).

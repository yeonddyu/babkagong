# Codex 독립 검증 요청서 — 밥카공

- 대상 커밋: `2d2b51d` (main, GitHub `yeonddyu/babkagong` 와 동일)
- 작성: Claude Code (구현 담당). **아래 PASS 는 모두 Claude Code 자체 검증 결과이며, 이 문서의 목적은 그 주장을 독립적으로 확인·반박하는 것이다.**
- 최상위 기준: `AI코어프로젝트_3회차_요구사항정의서.pdf` (저장소 루트, 대외비·gitignore) — 필수 F3001~F3019, 비기능 NF3001~NF3007. 심화 F3020~F3023 은 미착수(검증 대상 아님).

## 0. 검증 원칙 (Codex 에 요청)
1. **읽기 전용.** 코드·문서·`.env` 를 수정하지 않는다. 커밋·push 하지 않는다.
2. `.env` 의 키 값을 출력하거나 보고서에 적지 않는다 (존재 여부만).
3. 각 항목을 **PASS / FAIL / 판단 불가** 로 판정하고, FAIL 은 파일:줄·재현 방법·기대 동작을 적는다.
4. 실제 외부 API 를 부르는 검사(`-m integration`, `run_scenarios`)는 호출 한도를 소모한다. 필요한 만큼만 실행한다.
5. Claude Code 가 적은 결과(PLAN.md, docs/*)를 근거로 삼지 말고 코드·테스트·실행 결과로 확인한다.

## 1. 실행 방법
```bash
# 준비 (이미 되어 있으면 생략)
python3.12 -m venv .venv && .venv/bin/pip install -r backend/requirements.txt
cd frontend && npm install && cd ..

# 백엔드 단위 테스트 (외부 호출 없음) — 기대: 241 passed
cd backend && ../.venv/bin/python -m pytest -q

# 실제 외부 API 통합 테스트 — 기대: 18 passed, 0 skipped (키는 .env)
cd backend && ../.venv/bin/python -m pytest -m integration -v -rs

# 대표 시나리오 10개 (실제 API + GMS LLM) — 기대: 10/10 PASS, docs/scenario_results.md 재생성
cd backend && ../.venv/bin/python -m scripts.run_scenarios

# 외부 API 연결 점검 (키 마스킹)
cd backend && ../.venv/bin/python -m scripts.verify_apis

# 저장소·문서·빌드 결과에 키 값이 없는지
.venv/bin/python backend/scripts/check_secrets.py

# 프론트엔드 — 기대: vitest 10 passed, build 성공
cd frontend && npx vitest run && npm run build

# 서버 (수동 확인용)
cd backend && ../.venv/bin/uvicorn app.main:app --port 8000     # /docs
cd frontend && npm run dev                                       # http://127.0.0.1:5173
```
주의: 외부 데이터 캐시(`backend/data/cache`, gitignore)가 없으면 첫 실행에서 레드테이블 전체 페이지를 순회해 약 5분 걸린다 (`scripts.build_cache`).

## 2. 구조 (NF3006)
```
backend/app/core       설정(.env), 오류 코드, 좌표 변환, LLM provider(GMS 기본)
backend/app/clients    외부 API Client: redtable(서울관광재단), seoul_opendata, kakao_local, kma
backend/app/datasets   지역 필터 없는 API 데이터 정규화 + JSON 캐시
backend/app/tools      Tool envelope·레지스트리 + 4개 Tool
backend/app/agent      LangGraph 메인 Agent (analysis, planning, execution, judge, replan, memory, respond, course)
backend/app/events     EventBus(발행·구독) + LoggingAgent
backend/app/storage    SQLite: plans, execution_logs, sessions
backend/app/api        FastAPI 라우터·스키마
frontend/src           Vue 3: ChatView, PlansView, RecommendationCard, RunTimeline, StatusBanner
```
외부 API: 서울관광재단 음식관광(레드테이블), 서울 열린데이터광장(강남구 일반·휴게음식점 인허가), 기상청 단기예보, 카카오 로컬. LLM: SSAFY GMS(OpenAI 호환, gpt-4o-mini).

## 3. 요구사항별 검증 포인트

| ID | 주장 | 확인할 곳 | 특히 확인할 것 |
|---|---|---|---|
| F3001 | Tool 명세·등록, 외부/로컬 구분, 공통 envelope, 오류 코드 6종 | `tools/common.py`, `registry.py`, `catalog.py` | 어떤 예외도 `invoke()` 밖으로 나오지 않는가, 오류 메시지에 키·내부 예외가 없는가 |
| F3002 | 후보 조회, 기준일 기본값·미래 기준일 차이 명시, 출처 보완 | `tools/restaurant_candidates.py`, `datasets/restaurants.py` | 다른 출처 ID 를 같은 식당으로 연결하지 않는가(이름·위치 같은 보완 행은 **제외만** 함 — 이 처리가 '연결 금지'에 부합하는지 판단 요망) |
| F3003 | 후보 ID 로 메뉴·가격·영업시간, 미확인은 null | `tools/restaurant_details.py` | 가격 0 → null 처리, 인허가 출처는 `DETAIL_NOT_AVAILABLE` 사유 + 기본정보만 |
| F3004 | 다른 출처(카카오)로 카페, 결과 없음 형식, 카카오 실패 시 휴게음식점 보조 | `tools/nearby_cafes.py`, `clients/kakao_local.py` | 영업시간·콘센트·와이파이·혼잡도가 항상 null, 직선거리와 도보 추정의 구분 |
| weather | 기상청 예보, 격자 변환, 발표 시각 선택 | `tools/weather.py`, `clients/kma.py` | `base_before`/`latest_base` 경계(발표 10분 전, 자정), 지난 시각 처리 |
| F3005 | 기준/선호/제약 추출, 없는 조건 비움, LLM+규칙 | `agent/analysis.py`, `conditions.py` | `_evidence_guard` 가 LLM 이 지어낸 값을 충분히 막는가 (금액·시각·지역·도보·식사 구분) |
| F3006 | 필요한 Tool·순서 계획, 인사·사용법은 생략, 지역 없으면 되묻기 | `agent/planning.py` | |
| F3007 | 앞 결과 → 다음 입력, Tool 실패 후 진행 | `agent/execution.py`, `graph.py` | |
| F3008 | 예산·영업시간·휴무·거리·종료시각 계산, 미확인은 추정 안 함·역산 기준 | `agent/judge.py`, `policy.py` | `open_at` 파서(쉼표 구간·공휴일·브레이크·자정 넘김), `SIDE_MENU`·`is_meal_menu` 오탐/누락, 영업시간 미확인은 **제외하지 않고 경고**하는 정책의 타당성 |
| F3009 | 충족 0건일 때만 재계획, 결과 재사용, 상한 3 | `graph.py` (`_replan_decision`, `replan_node`) | 같은 (tool,args) 재호출이 정말 없는가, 상한 도달 사유 |
| F3010 | 후속 요청 변경 필드만 갱신, 원본 응답 미보관 | `agent/memory.py`, `storage/sessions.py` | 병합 조건(후속 표현 또는 지역 미언급)이 의도치 않게 이전 조건을 끌고 오는 경우 |
| F3011 | 추천·보조·기준·근거·제외 사유, 건강 안내, LLM 문장 검증 | `agent/respond.py` | LLM 문장 검증(`_llm_message_ok`)이 사실 아닌 수식어(예: "합리적인 가격")까지는 막지 못함 — 허용 수준인지 판단 요망 |
| F3012 | 단계·Tool·LLM 판단 이벤트, 발행자는 구독자 모름 | `events/bus.py`, `graph.py` (`_stage`) | |
| F3013 | 로깅 Agent 구독·세션 단위 저장, LLM 미사용, 실패 격리 | `events/logging_agent.py`, `storage/logs.py` | |
| F3014 | 로그 목록·상세·삭제, 수정 API 없음 | `storage/logs.py`, `api/routes.py` | `PUT /api/logs/{id}` → 405 |
| F3015 | 계획 저장·조회, 날짜 포함, 시간 겹침은 저장 후 안내 | `storage/plans.py`, `agent/course.py` | 대화 저장 시 시각 기본값(점심 12:00, +3시간) 가정 안내 |
| F3016 | 계획 수정·삭제, 화면 반영 | `storage/plans.py`, `frontend/src/views/PlansView.vue` | |
| F3017 | FastAPI 대화·계획·로그 API | `app/main.py`, `api/*` | 오류 응답 `{detail:{code,message}}`, 500 시 내부 상세 미노출 |
| F3018 | Vue 화면, 실제 API 연동 | `frontend/src/**` | 확인되지 않은 데이터를 정상 추천처럼 보이게 하지 않는가 |
| F3019 | 실행 단계·Tool 이력·재계획·처리 중·오류·키 누락 표시 | `RunTimeline.vue`, `StatusBanner.vue`, `POST /api/chat/stream` | SSE 스트림의 세션 필터·스레드 종료 처리 |

| NF | 확인 방법 |
|---|---|
| NF3001 | `check_secrets.py`, 코드에 키 하드코딩 여부 grep |
| NF3002 | `/api/*` 오류 응답·화면 문구에 키·스택트레이스가 없는지 |
| NF3003 | 외부 API 하나씩 실패시켜도 응답이 나오는지 (단위 테스트 + 수동) |
| NF3004 | `MAX_REPLANS` 상한, 무한 루프 경로가 없는지 |
| NF3005 | 대표 요청 소요 시간 (주장: GMS 사용 2.0~7.7초, 캐시 구축 후) |
| NF3007 | `docs/api_verification.md` 출처·호출 한도·이용 조건 |

## 4. Claude Code 가 스스로 알린 문제 (확인 요청)
1. `f0fc2de` (F3016) 은 테스트 1건 실패 상태로 커밋됨 → `ca1879d` 에서 수정. 현재 HEAD 에서 모두 통과하는지 확인.
2. 커밋 메시지 테스트 수 오기: `9bddf88` 138→실제 137, `494becf` 235→실제 233.
3. 시나리오 S2 는 1차에 FAIL(재계획이 안 일어나는 요청을 고름) → 요청 교체. 교체가 결과를 유리하게 만든 것이 아닌지 판단 요망.
4. 2026-11-18 STEP1 커밋은 키 미발급으로 'BLOCKED' 로 커밋됨, 이후 실제 검증.
5. `refactor` 커밋 `8c2b642` 에 requirements.txt 의존성 추가가 함께 들어감, `docs` 커밋 `0752ddd` 에 `verify_apis.py`(스크립트) 변경이 함께 들어감 — 커밋 단위 규칙 위반 여부.

## 5. 알려진 한계 (결함 여부 판단 요청)
- 레드테이블은 지역·ID 필터가 없어 전체 페이지를 받아 강남·역삼 1.5km 만 캐시(TTL 168h). 메뉴 등록 식당은 8,125곳 중 1,560곳 → 예산 조건 시 '가격 미확인' 제외·재계획이 잦음.
- 강남구 인허가 데이터에는 강남역 서측(서초구) 업소가 없음 (응답 notes 로 안내).
- 공휴일 여부는 판단하지 않음. 영업시간 문장 중 '공휴일' 구간은 무시.
- 식사 메뉴 판정·온열/냉 음식 판정은 키워드 정책(`judge.py SIDE_MENU`, `policy.py`). 날씨 임계값(5°C/28°C/60%)은 밥카공 초기 정책.
- 도보 시간은 직선거리×1.3÷67m/분 추정치.
- `.env` 의 `GMS_MODEL` 은 안내 문구라 코드가 무시하고 gpt-4o-mini 사용.
- 실행 로그·세션 Memory 는 SQLite 단일 파일, 동시성 고려는 최소 수준.

## 6. 보고 형식 (요청)
```
| 항목 | 판정(PASS/FAIL/판단 불가) | 근거(파일:줄 또는 실행 결과) | 재현 방법 | 권고 |
```
마지막에: 필수 요구사항 누락 여부, 보안 위험, 우선 수정이 필요한 상위 5개.

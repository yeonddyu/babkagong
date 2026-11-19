# 구현 결과 보고서

- 작성: 2026-11-19, Claude Code (자체 검증). **Codex 독립 검증 전**이며 아래 판정은 독립 감사 결과가 아니다.
- 기준: `AI코어프로젝트_3회차_요구사항정의서.pdf` F3001~F3019, NF3001~NF3007 (F3020~F3023 심화는 미착수)

## 1. 최종 판정

| 구분 | 결과 |
|---|---|
| 필수 기능 F3001~F3019 | 19개 **PASS** (F3004 카카오는 사용자가 카카오맵 활성화 후 재검증해 PASS) |
| LLM | SSAFY GMS(gpt-4o-mini) 실제 호출로 요청 분석·응답 문장 검증 PASS (OpenAI 직접 호출은 미사용) |
| 추가 기능 (기상청 날씨) | PASS (실제 호출) |
| 비기능 NF3001~NF3007 | 7개 PASS (NF3005 는 캐시 사전 구축 조건) |
| 대표 시나리오 | 실제 API 10/10 PASS (`docs/scenario_results.md`) |
| 테스트 | 백엔드 단위 242 passed / 통합 18 passed·0 skipped (GMS LLM 3건 포함) / 프론트 vitest 41 passed / build 통과 |

요구사항별 상세는 `PLAN.md`.

## 2. 요구사항별 구현·검증

| ID | 구현 파일 | 테스트 | 실제 검증 | 커밋 |
|---|---|---|---|---|
| F3001 | `app/tools/common.py`, `registry.py`, `catalog.py` | `test_f3001_registry.py` | - | c1e33eb |
| F3002 | `app/tools/restaurant_candidates.py`, `app/datasets/restaurants.py`, `app/clients/redtable.py`, `seoul_opendata.py` | `test_f3002_*`, `test_live_f3002.py` | 레드테이블·인허가 실제 | 7de2352, de6c462 |
| F3003 | `app/tools/restaurant_details.py` | `test_f3003_*`, `test_live_f3003.py` | 후보 ID→상세 실제 | 296297b, 6c53d15 |
| F3004 | `app/tools/nearby_cafes.py`, `app/clients/kakao_local.py` | `test_f3004_*`, `test_live_f3004.py` | 카카오 실제 PASS, 휴게음식점 보조 실제 PASS | 24b6aeb, 89a2176, cfa4460 |
| weather | `app/tools/weather.py`, `app/clients/kma.py` | `test_weather.py`, `test_live_weather.py` | 기상청 실제 | 0f5e27d |
| F3005 | `app/agent/analysis.py`, `conditions.py`, `app/core/llm_provider.py` | `test_f3005_analysis.py`, `test_live_llm.py` | GMS LLM 실제 + 규칙 | 730901d, f09a082, f618501, 4e71de8 |
| F3006 | `app/agent/planning.py` | `test_f3006_planning.py` | S1·S5·S6 | 9bddf88 |
| F3007 | `app/agent/execution.py`, `graph.py` | `test_f3007_execution.py` | S1·S4 | d08983a |
| F3008 | `app/agent/judge.py`, `policy.py` | `test_f3008_judge.py` | S1~S3 | d5193e7, f373ea3, bc2851f |
| F3009 | `app/agent/graph.py` (replan) | `test_f3009_replan.py` | S2·S3 | e31408f |
| F3010 | `app/agent/memory.py`, `app/storage/sessions.py` | `test_f3010_memory.py` | S8 | dd56ea1 |
| F3011 | `app/agent/respond.py` | `test_f3011_response.py` | 전 시나리오 | ad30e41, d21a0c8 |
| F3012 | `app/events/bus.py` | `test_f3012_events.py` | 실서버 | 51e10bc |
| F3013 | `app/events/logging_agent.py`, `app/storage/logs.py` | `test_f3013_logging_agent.py` | 실서버 SQLite | 57c6905 |
| F3014 | `app/storage/logs.py`, `app/api/routes.py` | `test_f3014_logs_query.py`, `test_f3017_api.py` | API | 5cdc6b4 |
| F3015 | `app/storage/plans.py`, `app/agent/course.py` | `test_f3015_plans.py` | S9·S10, 브라우저 | b75eae3 |
| F3016 | `app/storage/plans.py` | `test_f3016_plan_edit.py` | 브라우저 | f0fc2de, ca1879d |
| F3017 | `app/main.py`, `app/api/*` | `test_f3017_api.py`, `test_f3019_stream.py` | uvicorn 실기동 | 4466d98 |
| F3018 | `frontend/src/**` | `frontend/tests/f3018.spec.ts` | 브라우저 실연동 (추천→저장→상세→수정) | fbc308f |
| F3019 | `RunTimeline.vue`, `StatusBanner.vue`, `/api/chat/stream` | `f3019.spec.ts`, `test_f3019_stream.py` | 브라우저 실시간 진행·재계획 | 494becf |

## 3. 실제 데이터 실행에서 발견해 수정한 문제
| 문제 | 수정 커밋 |
|---|---|
| 카카오 실패 + 보조 0건이 '결과 없음'으로 보고됨 | cfa4460 |
| 조건만 있는 발화('강남역 1만원 이하')가 범위 밖으로 분류 | f09a082 |
| 도넛·타로카페 등 비식사 업종이 식사 후보로 추천 | de6c462 |
| 메뉴 원본 중복 행 | 6c53d15 |
| '공휴일' 영업시간 구간을 매일로 해석, 다른 요일 휴무를 경고, 곁들임·1원 메뉴로 예산 충족, 같은 매장 중복 추천 | f373ea3 |
| 사용자가 말한 날씨와 예보 불일치 안내 없음 | d21a0c8 |
| SQLite 에서 읽은 일시의 시간대 손실 | ca1879d |
| 주류가 대표 메뉴로 표시 | bc2851f |
| 상세조회마다 5MB 캐시 재로딩 (160ms) | 4a3c0a9 |
| GMS LLM 이 말하지 않은 도보 선호를 채우고 시각에 시간대를 붙임 | 4e71de8 |
| GMS LLM 문장에서 추천 카페·미확인 안내 누락 | e759e58 |
| 버블티 가게(음료만)가 점심 식당으로 추천 | 998599b |
| GMS 사용 중에도 OPENAI 키 누락 경고 표시 | 2b7acd2 |

## 4. 기록해야 할 절차상 문제 (숨기지 않음)
1. **F3016 커밋 f0fc2de 는 테스트 1건 실패 상태로 생성됨.** 커밋 명령에서 pytest 종료 코드 대신 `tail` 종료 코드를 확인한 실수. 직후 ca1879d 에서 원인(SQLite 시간대 손실)을 수정하고 전체 통과 확인. 이후 커밋은 pytest 종료 코드로 검사.
2. 커밋 메시지의 테스트 수 오기: 9bddf88(F3006) "138 passed" → 실제 137, 494becf(F3019) "235 passed" → 실제 233. 승인 없는 amend 금지 규칙에 따라 커밋은 수정하지 않고 여기에 기록.
3. 대표 시나리오 S2 1차 실행 FAIL — 실제 데이터에서 재계획이 일어나지 않는 요청을 고른 시나리오 선택 오류. 요청을 교체 후 PASS, `docs/scenario_results.md` 에 기록.
4. 2026-11-18 STEP1 커밋(F3002~F3004)은 당시 키 미발급으로 'BLOCKED' 표기. 2026-11-19 실제 키로 통합 테스트 통과, 카카오는 같은 날 사용자가 카카오맵을 활성화한 뒤 재검증해 통과.

## 5. 미해결
| 항목 | 영향 | 조치 |
|---|---|---|
| 첫 캐시 구축 약 5분 | 캐시 없을 때 첫 요청 지연 | `scripts.build_cache` 사전 실행 |
| 레드테이블 메뉴 보유 식당 19% | 예산 조건 시 '가격 미확인' 제외가 많아 재계획 빈발 | 데이터 한계, 응답에 사유·제안 표시 |
| 강남역 서측(서초구) 인허가 데이터 없음 | 보완 후보 누락 | notes 로 안내 |
| 공휴일 판단 불가 | 공휴일 휴무 여부 미판단 | 문서화 |
| Codex 독립 검증 | 미수행 | 검증 요청 필요 |

## 6. 실행 방법
README.md 참고. 백엔드 `cd backend && ../.venv/bin/uvicorn app.main:app --port 8000`, 프론트 `cd frontend && npm run dev`.

## 7. UI/UX 개선 (2026-11-19, 필수 기능 유지)

| 항목 | 구현 | 커밋 |
|---|---|---|
| 2단 레이아웃·모바일 탭 | 대화 / 코스 패널 분리, 900px 이하 탭 전환, 추천 카드는 코스 패널에만 | 6ab2026 |
| 추천 지도 | 카카오 지도 SDK(`VITE_KAKAO_MAP_KEY`) 또는 좌표 위치도(SVG), 식당·카페·역 핀, 선택 코스 강조, 식당→카페 점선 직선 | 31998c6, 91d8678 |
| 시각적 추천 카드 | 칩·배지 중심, 대표 카페만 펼치고 근거·다른 카페·점수는 접기 | c53d039 |
| 코스 타임라인 | 식사(요청 시각)·이동(직선거리·도보 추정)·카공 시작(요청한 카페 시각) — 시각을 계산해 만들지 않음 | adb6aa8 |
| 메뉴 룰렛 | 추천 코스의 가격 확인 메뉴만, 결과에 출처 코스 | 0abfcbc |
| 날씨 반응형 UI | 기상청 응답 기준 띠·색조·비/눈 효과, 백엔드 정책과 같은 기준 | 82b8c91 |

UI 확인 중 발견한 백엔드 문제: GMS LLM 이 말하지 않은 카페 시각(13:00)을 채움 → `7c854cb` 에서 발화 근거 검사 추가.

회귀 테스트: 백엔드 단위 242 passed, 통합 18 passed, 프론트 vitest 41 passed (기존 F3018·F3019 테스트 포함), build 통과.
실제 확인: 브라우저에서 실제 백엔드(카카오·기상청·GMS)로 데스크톱 2단·모바일 탭·지도·타임라인·룰렛·날씨 띠 확인.

카카오 지도 실화면: 루트 `.env` 의 `VITE_KAKAO_MAP_KEY` + 카카오 앱 JavaScript SDK 도메인(`http://localhost:5173`) 등록 후 브라우저에서 확인 — 실제 지도 위 식당·카페·역 핀, 선택 코스 점선 직선, 데스크톱·모바일 탭 모두 정상. 확인 중 숨겨진 탭에서 지도가 만들어지면 타일·핀이 안 그려지는 문제를 발견해 크기 변화 시 relayout 하도록 수정. `127.0.0.1:5173` 은 도메인 미등록(401)이라 `localhost` 로 접속해야 함.

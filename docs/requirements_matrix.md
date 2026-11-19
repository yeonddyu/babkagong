# 요구사항 매핑표

요구사항정의서(3회차) → 밥카공 도메인 표현 → 구현 위치 → 검증.

| ID | 정의서 요구 | 밥카공 표현 | 구현 위치 | 테스트 |
|---|---|---|---|---|
| F3001 | Tool 이름·설명·입출력 스키마 정의, 외부/로컬 구분 | 4개 외부 API Tool, 공통 envelope·오류 코드 | `app/tools/common.py`, `registry.py`, `catalog.py` | `test_f3001_registry.py` |
| F3002 | 후보 목록 확보, 부족하면 다른 API 로 보충 | 강남·역삼 음식점 후보 (레드테이블 → 강남구 인허가 보충) | `app/tools/restaurant_candidates.py` | `test_f3002_*`, `test_live_f3002.py` |
| F3003 | 제약 판단에 필요한 속성 확보 | 메뉴·가격·영업시간·휴무·편의시설 | `app/tools/restaurant_details.py` | `test_f3003_*`, `test_live_f3003.py` |
| F3004 | 다른 출처 API 로 보조 정보 | 카카오 주변 카페 (보조: 강남구 휴게음식점) | `app/tools/nearby_cafes.py` | `test_f3004_*`, `test_live_f3004.py` |
| (추가) | — | 기상청 날씨 조회 Tool | `app/tools/weather.py` | `test_weather_*` |
| F3005 | 날짜·시각(기준), 지역·분류·예산(선호), 상한(제약) 추출 | 방문 날짜·식사/카페 시각, 역·음식 종류·가까운 곳 선호, 예산·최대 거리 | `app/agent/analysis.py` | `test_f3005_*` |
| F3006 | Tool 과 호출 순서 계획, 불필요 Tool 제외 | 날씨→후보→상세→카페, 인사·사용법은 계획 생략 | `app/agent/planning.py` | `test_f3006_*` |
| F3007 | 계획대로 호출, 앞 결과 → 다음 입력, 실패 시 사유 기록 후 진행 | 후보 ID → 상세, 좌표 → 카페 | `app/agent/execution.py` | `test_f3007_*` |
| F3008 | 속성으로 계산·비교, 확인 불가 값은 역산 기준 | 예산·영업시간·휴무·거리·날씨 가산점 | `app/agent/judge.py`, `policy.py` | `test_f3008_*` |
| F3009 | 대안 탐색, 결과 재사용, 상한 시 사유 응답 | 다음 후보 묶음·인접 역, 상한 3 | `app/agent/graph.py` (replan) | `test_f3009_*` |
| F3010 | 이전 요청·결과 기억, 변경 조건만 갱신 | 세션 Memory (조건·추천 요약) | `app/agent/memory.py`, `storage` | `test_f3010_*` |
| F3011 | 추천·보조·판단 근거·Tool 근거·제외 사유, 위험 도메인 안내 | 식당+카페 코스, 판단 기준, 제외 사유, 알레르기·건강 안내 | `app/agent/respond.py` | `test_f3011_*` |
| F3012 | 단계·Tool·LLM 판단 이벤트 발행 (구독자 비의존) | | `app/events/bus.py`, agent | `test_f3012_*` |
| F3013 | 로깅 Agent 구독·세션 단위 저장, LLM 미사용 | | `app/events/logging_agent.py`, `storage` | `test_f3013_*` |
| F3014 | 로그 목록·상세·삭제, 수정 불가 | | `app/storage/logs.py`, `api/logs.py` | `test_f3014_*` |
| F3015 | 계획 저장·조회, 날짜 필수, 시간 겹침 안내 | 식사·카페 코스 계획 | `app/storage/plans.py` | `test_f3015_*` |
| F3016 | 계획 수정·삭제, 화면 반영 | | `app/storage/plans.py`, `api/plans.py` | `test_f3016_*` |
| F3017 | FastAPI 대화·계획·로그 API | | `app/main.py`, `app/api/*` | `test_f3017_*` |
| F3018 | 화면 구현·API 연동 | Vue 3 채팅·추천·계획 화면 | `frontend/src` | build + 브라우저 |
| F3019 | 실행 단계·Tool 이력·진행·오류 표시 | 실행 타임라인 | `frontend/src/components/RunTimeline.vue` | build + 브라우저 |
| NF3001~7 | 보안·안정성·성능·구조·출처 | | 전체 | `docs/implementation_report.md` |

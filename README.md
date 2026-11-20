# 밥카공 (BabCaGong)
https://github.com/yeonddyu/babkagong

역삼역(SSAFY) 주변 6개 역(역삼·강남·언주·신논현·선릉·선정릉)에서 **식사할 곳과 식사 후 카공할 카페를 함께** 추천하는 AI Agent 웹서비스 (SSAFY AI 코어 3회차).
메뉴 가격·영업시간은 서울관광재단 데이터, 업소 보완은 서울 열린데이터광장, 날씨는 기상청, 카페는 카카오 로컬 API 로 확인하며
**확인되지 않은 값은 만들지 않고 '미확인'으로 표시**한다.

요구사항정의서의 기본 범위는 강남역·역삼역이며, 2026-11-20 사용자 요청으로 역삼역에서 가까운 역 4곳
(언주·신논현·선릉·선정릉, 역삼역에서 직선 0.8~1.3km)을 더했다.

## 주요 기능
- **조건 이해**: 역·날짜·시각·예산·음식 종류·제외 음식·'많이 걷기 싫어'·'도보 N분 이내'·'Nm 이내'·'N번 출구 근처'를 발화에서 추출 (SSAFY GMS LLM + 규칙, 발화에 없는 값은 비움)
- **Agent 실행**: 분석 → 계획 → Tool 실행 → 판단 → (재계획 최대 3회) → 응답. 예산·영업시간·휴무·거리·종료 시각을 코드로 판정하고 제외 사유를 남김
- **추천**: 식당 5곳과 식사 후 카페, '다른 곳 더 보기'(이미 보여 준 곳 제외), 요청마다 반경 안 후보를 고르게 골라 같은 식당만 반복되지 않게 함
- **역 선택**: 역 버튼 6개, 역 이름 없이 보내면 고른 역에서 찾고, 서비스 밖 역을 말하면 그렇다고 안내
- **화면**: 짧은 요약 대화, 카카오 지도(장소 정보 카드·다른 카페로 바꾸기), 코스 흐름, 원형 메뉴 룰렛, 날씨 반응형 마스코트, 실시간 실행 과정
- **계획**: 대화에서 고른 코스를 저장하고 조회·수정·삭제, 같은 날 시간 겹침 안내, 저장한 코스를 지도에 다시 표시
- **실행 로그**: 단계·Tool·재계획 이벤트를 로깅 Agent(LLM 미사용)가 세션 단위로 저장

## 구성
```
backend/   FastAPI + LangGraph 메인 Agent + Tool + 외부 API Client + 로깅 Agent + SQLite
frontend/  Vue 3 + TypeScript + Vite
docs/      설계·명세·검증 문서
```
자세한 구조는 [docs/architecture.md](docs/architecture.md).

## 준비
```bash
python3.12 -m venv .venv
.venv/bin/pip install -r backend/requirements.txt
cp .env.example .env        # 발급받은 키를 .env 에만 입력 (커밋 금지)
cd frontend && npm install
```

외부 데이터를 미리 받아 두면 첫 응답이 빠르다 (약 5분: 서울관광재단 API 전체를 훑어 6개 역 1.5km 안 식당·메뉴·운영정보만 SQLite 에 저장, 7일 뒤 다시 수집).
서버를 켜면 같은 준비가 백그라운드로 시작된다.
```bash
cd backend && ../.venv/bin/python -m scripts.build_cache
```

## 실행
백엔드 (http://localhost:8000, 문서: /docs)
```bash
cd backend && ../.venv/bin/uvicorn app.main:app --port 8000
```
프론트엔드 (http://localhost:5173, /api 는 8000 으로 프록시)
```bash
cd frontend && npm run dev
```
카카오 지도(선택): 저장소 루트 `.env` (또는 `frontend/.env.local`) 에 `VITE_KAKAO_MAP_KEY=JavaScript키` 를 넣고, 카카오 앱 > 플랫폼 > Web 에
`http://localhost:5173` 을 등록한다. 키가 없으면 실제 좌표로 그린 위치도로 표시된다. (`frontend/.env.example` 참고)

### Docker 로 실행 (선택)
루트 `Dockerfile` 은 Vue 를 빌드해 FastAPI 와 같은 주소(http://127.0.0.1:8000)에서 제공한다. 이 이미지는 공개 데모 모드라 계획 저장과 계획·로그 관리 API 가 꺼진다.
```bash
docker build -t babkagong-demo .
docker volume create babkagong-data
docker run --rm -p 127.0.0.1:8000:8000 --env-file .env -v babkagong-data:/data babkagong-demo
```

## 배포
공개 배포는 하지 않는다. 로컬(위 '실행' 또는 Docker)에서 실행해 사용한다.

## 화면별 기능
아래 화면은 모두 2026-11-20 로컬 서버(실제 외부 API·SSAFY GMS·카카오 지도)에서 캡처했다. 데스크톱 1440×900, 모바일 390×844.

### 1. 첫 화면 — 날씨 마스코트, 역 선택, 예시 질문
역 버튼 6개 중 하나를 고르면 예시 질문과 입력창 안내가 그 역 이름으로 바뀐다. 역 이름 없이 보내면 고른 역 주변에서 찾는다.

![첫 화면](docs/screenshots/01-home.png)

### 2. 추천 결과와 카카오 지도
대화창에는 코드가 확정 값으로 만든 짧은 요약만 보이고, 오른쪽 지도에 식당(번호)·카페·역 위치와 식당→카페 직선이 표시된다.

![추천 결과와 지도](docs/screenshots/02-recommendation.png)

### 3. 전체 답변과 Agent 실행 과정
'전체 답변 보기' 를 펼치면 코스별 메뉴·가격·영업시간·거리를, '실행 과정' 을 펼치면 요청 분석 → 계획 → Tool 실행(날씨·후보·상세·카페) 순서와 소요 시간을 볼 수 있다.

![전체 답변과 실행 과정](docs/screenshots/03-full-answer-and-run.png)

### 4. 지도 장소 정보 카드
식당 핀이나 카드의 '지도에서 식당 보기' 를 누르면 확인된 메뉴·가격·영업시간·추천 이유가 담긴 정보 카드가 열린다. 확인되지 않은 값은 '확인 필요' 로 표시한다.

![지도 장소 정보 카드](docs/screenshots/04-map-place-card.png)

### 5. 코스 흐름
식사 → 카페로 이동 → 카공 시작. 사용자가 말한 시각과 확인된 거리만 쓰고, 도보 시간은 직선거리 기준 추정임을 밝힌다.

![코스 흐름](docs/screenshots/05-course-timeline.png)

### 6. 추천 카드
식당 주소·거리·영업시간·음식 종류, 예산 안 메뉴와 가격, 통과한 판단 기준, 식사 후 카공 카페와 '이 코스 저장' 버튼.

![추천 카드](docs/screenshots/06-recommendation-card.png)

### 7. 다른 카페로 바꾸기
'근처 카페 더 보기' 에서 카페를 바꾸면 카드·지도 연결선·코스 흐름·저장 대상이 함께 바뀐다. 지도에는 고른 코스의 다른 카페 후보가 점선 핀으로 보인다.

| 카드 | 지도 |
|---|---|
| ![카페 바꾸기 카드](docs/screenshots/07-change-cafe-card.png) | ![카페 바꾸기 지도](docs/screenshots/07-change-cafe-map.png) |

### 8. 오늘 뭐 먹지? — 원형 메뉴 룰렛
추천 코스에서 가격이 확인된 메뉴만 칸에 올리고, 바늘이 멈춘 칸이 결과가 된다. '이 메뉴로 식당 찾기' 를 누르면 그 코스를 고르고 지도 정보 카드를 연다. 메뉴가 부족하면 식당 뽑기로 바뀐다.

![원형 메뉴 룰렛](docs/screenshots/08-menu-roulette.png)

### 9. 다른 곳 더 보기
같은 조건에서 이미 보여 준 곳을 빼고 다시 5곳을 고른다.

![다른 곳 더 보기](docs/screenshots/09-more-results.png)

### 10. 코스 저장과 시간 겹침 안내
'이 코스 저장' 으로 고른 카페까지 계획에 저장한다. 같은 날 시간이 겹치는 계획이 있으면 저장은 하고 겹침을 알린다.

![코스 저장](docs/screenshots/10-save-plan-chat.png)

### 11. 출구 기준 검색 — '강남역 11번 출구 근처'
카카오 로컬의 지하철 출구 좌표를 기준점으로 거리를 계산한다. 지도에 기준 출구(초록 핀)와 '거리 기준' 범례가 표시되고, 출구를 찾지 못하면 역 중심으로 찾고 안내한다.

![출구 기준 검색](docs/screenshots/11-exit-origin.png)

### 12. 걷는 거리 제한 — '도보 5분 이내'
'도보 N분 이내'·'Nm 이내' 는 판정과 같은 추정식으로 검색 반경을 줄여 그 안에서만 고른다.

![도보 5분 이내](docs/screenshots/12-walk-limit.png)

### 13. 인사와 서비스 밖 역 안내
인사·도움말은 규칙으로 바로 답하고(외부 호출 0회), 서비스 밖 역을 말하면 추천하지 않고 6개 역 중에서 고르도록 안내한다.

![인사와 서비스 밖 역](docs/screenshots/13-unsupported-station.png)

### 14. 재계획 상한 도달
충족 후보가 없으면 다음 후보 묶음 → 인접 역 순으로 최대 3회 재계획하고, 멈춘 이유·제외 사유·조건 완화 제안을 보여 준다.

![재계획 상한](docs/screenshots/14-replan-limit.png)

### 15. 날씨 반응형 마스코트
기상청 단기예보(방문 시각)로 상태가 바뀐다: 대기·날씨 미확인·쌀쌀함·비 예보·비 올 수도(강수확률만 높음)·더움·맑음·흐림·눈. 모든 값은 '예보 · 실측값 아님' 으로 표시한다.

![날씨 마스코트 상태](docs/screenshots/19-weather-mascot-states.png)

### 16. 저장한 계획 — 목록·상세·지도
저장한 계획을 날짜로 거르고, 상세에서 저장 당시 좌표로 식당·카페를 지도에 다시 표시한다.

![저장한 계획 상세](docs/screenshots/15-plan-detail.png)

### 17. 계획 수정
제목·날짜·시각·식당·카페·메모를 수정하고 삭제할 수 있다. 수정 후에도 시간 겹침을 다시 확인한다.

![계획 수정](docs/screenshots/16-plan-edit.png)

### 18. 모바일 — 대화·추천 / 지도 탭
900px 이하에서는 탭으로 전환하고(방향키로도 이동), 입력창은 화면 아래에 고정된다. 카드의 '지도 보기' 를 누르면 지도 탭으로 넘어간다.

| 대화·추천 | 지도 |
|---|---|
| ![모바일 대화](docs/screenshots/17-mobile-chat.png) | ![모바일 지도](docs/screenshots/18-mobile-map.png) |

### 19. 백엔드 API 문서
FastAPI 자동 문서(`/docs`)에서 대화·SSE 스트림·계획·실행 로그·역 목록 API 를 확인할 수 있다.

![API 문서](docs/screenshots/20-api-docs.png)

## 테스트
```bash
cd backend && ../.venv/bin/python -m pytest                      # Mock 단위 테스트 (304 passed)
cd backend && ../.venv/bin/python -m pytest -m integration -rs   # 실제 외부 API 18개 (키가 없으면 BLOCKED skip)
cd backend && ../.venv/bin/python -m scripts.run_scenarios       # 대표 시나리오 10개 (캐시·실제 API) → docs/scenario_results.md
cd backend && ../.venv/bin/python -m scripts.verify_apis         # API 연결 검증 (키 마스킹)
.venv/bin/python backend/scripts/check_secrets.py                # 저장소에 키 값이 없는지 점검
cd frontend && npm test && npm run build                          # vitest 87 passed, 빌드
```
마지막 실행(2026-11-20): 단위 304 passed, 프론트 87 passed, 빌드 통과, 키 포함 파일 없음.
실제 외부 API 는 15 passed, 서울관광재단 API 를 직접 부르는 3개는 호출 한도 초과(HTTP 429)로 BLOCKED.

## 문서
| 문서 | 내용 |
|---|---|
| [PLAN.md](PLAN.md) | 요구사항별 진행 상태 (PASS/BLOCKED) |
| [CLAUDE.md](CLAUDE.md) | 개발 규칙 |
| [docs/requirements_matrix.md](docs/requirements_matrix.md) | 요구사항 ↔ 구현 ↔ 테스트 |
| [docs/architecture.md](docs/architecture.md) | 시스템·Agent 그래프·날씨 정책·이벤트 |
| [docs/tool_spec.md](docs/tool_spec.md) | Tool 명세 |
| [docs/api_spec.md](docs/api_spec.md) | 백엔드 API |
| [docs/db_schema.md](docs/db_schema.md) | DB 스키마 |
| [docs/api_verification.md](docs/api_verification.md) | 외부 API 실제 연결·이용 조건 |
| [docs/test_plan.md](docs/test_plan.md) | 테스트 계획 |
| [docs/scenario_results.md](docs/scenario_results.md) | 대표 시나리오 결과, [docs/samples/](docs/samples) 실행 로그 샘플 |
| [docs/implementation_report.md](docs/implementation_report.md) | 구현 결과 보고 (독립 검증 결함 수정 포함) |
| [docs/codex_review_brief.md](docs/codex_review_brief.md) | 독립 검증 요청서 |
| [셀프체크리스트_최종검증.xlsx](셀프체크리스트_최종검증.xlsx) | 최종 제출 점검 결과 |

## 현재 제한
- 서비스 지역은 역삼역 주변 6개 역. 다른 역은 '서비스 지역이 아니에요' 로 안내한다.
- LLM: SSAFY GMS(gpt-4o-mini)로 요청을 분석하고, 키가 없거나 분석이 실패하면 규칙을 적용한다. 응답 문장은 구조화된 결과로 생성한다.
- 보완 출처(인허가 정보)는 강남구만 있어, 강남구 밖 업소는 서울관광재단 정보로만 찾는다. 서울관광재단 데이터에는 폐업 여부가 없다.
- 도보 시간은 직선거리×1.3÷67m/분 추정이며 실제 경로가 아니다. 카페 영업시간·콘센트·와이파이·혼잡도는 확인하지 않는다.
- 카카오 장소 정보: 출구 좌표는 메모리에 24시간만 두고, 대화 맥락·저장한 계획에는 카페 이름·링크·좌표를 보관한다.
  카카오 운영정책상 이 보관이 허용되는지는 확인되지 않았다 ([docs/api_verification.md](docs/api_verification.md) 2.4).
- 출처 표기: 날씨 정보 출처 기상청(공공누리 제1유형)

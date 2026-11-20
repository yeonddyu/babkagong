# 밥카공 (BabCaGong)

역삼역(SSAFY) 주변 6개 역(역삼·강남·언주·신논현·선릉·선정릉)에서 **식사할 곳과 식사 후 카공할 카페를 함께** 추천하는 AI Agent 웹서비스 (SSAFY AI 코어 3회차).
요구사항정의서의 기본 범위는 강남역·역삼역이며, 2026-11-20 사용자 요청으로 역삼역에서 가까운 역 4곳(언주·신논현·선릉·선정릉, 역삼역에서 직선 0.8~1.3km)을 더했다.
메뉴 가격·영업시간은 서울관광재단 데이터, 업소 보완은 서울 열린데이터광장, 날씨는 기상청, 카페는 카카오 로컬 API 로 확인하며
**확인되지 않은 값은 만들지 않고 '미확인'으로 표시**한다.

## 구성
```
backend/   FastAPI + LangGraph 메인 Agent + Tool + 외부 API Client + 로깅 Agent + SQLite
frontend/  Vue 3 + TypeScript + Vite
docs/      설계·명세·검증 문서
```
Agent 흐름: 분석 → 계획 → 실행(Tool) → 판단 → (재계획 ≤3회) → 응답, 저장 요청은 save 노드(Tool 아님).
자세한 구조는 [docs/architecture.md](docs/architecture.md).

## 준비
```bash
python3.12 -m venv .venv
.venv/bin/pip install -r backend/requirements.txt
cp .env.example .env        # 발급받은 키를 .env 에만 입력 (커밋 금지)
cd frontend && npm install
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

## 화면
- 데스크톱(45:55): 왼쪽 날씨 마스코트 → 지역 선택 → 대화(짧은 요약, 전체 답변은 펼치기) → 원형 메뉴 룰렛 → 코스 흐름 → 추천 카드(저장) /
  오른쪽 화면을 따라오는 카카오 지도(핀을 누르면 장소 정보 카드, 다른 카페 후보로 바꾸기)
- 모바일(900px 이하): '대화·추천' / '지도' 탭 전환, 입력창은 화면 아래 고정
- 저장한 계획 상세에서 저장 당시 좌표로 식당·카페를 지도에 다시 표시
- 지역: 역 버튼 6개(역삼·강남·언주·신논현·선릉·선정릉), 다른 역을 말하면 서비스 지역이 아니라고 안내
- '강남역 11번 출구 근처', '도보 5분 이내', '200m 이내' 처럼 기준점·거리 제한을 말하면 그 기준으로 거리 계산 (출구 좌표: 카카오 로컬, 찾지 못하면 역 중심 + 안내)
- 지도의 식당→카페 선은 직선이며 실제 경로가 아님을 표시, 시각·영업시간·편의시설 등 확인되지 않은 값은 '미확인'·'시각 미지정'으로 표시
첫 요청 전에 외부 데이터를 미리 받아 두면 응답이 빠르다 (약 5분: API 전체를 훑어 6개 역 1.5km 안 식당·메뉴만 SQLite 에 저장).
서버를 켜면 같은 준비가 백그라운드로 시작된다.
```bash
cd backend && ../.venv/bin/python -m scripts.build_cache
```

## 테스트
```bash
cd backend && ../.venv/bin/python -m pytest                      # Mock 단위 테스트 (259)
cd backend && ../.venv/bin/python -m pytest -m integration -rs   # 실제 외부 API (키가 없으면 BLOCKED skip)
cd backend && ../.venv/bin/python -m scripts.run_scenarios       # 대표 시나리오 10개 (실제 API) → docs/scenario_results.md
cd backend && ../.venv/bin/python -m scripts.verify_apis         # API 연결 검증 (키 마스킹)
.venv/bin/python backend/scripts/check_secrets.py                # 저장소에 키 값이 없는지 점검
cd frontend && npm test && npm run build                          # vitest 78, 빌드
```

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
| [docs/implementation_report.md](docs/implementation_report.md) | 구현 결과 보고 |

## 현재 제한
- LLM: SSAFY GMS(gpt-4o-mini)로 요청 분석·응답 문장 생성. 키가 없거나 실패하면 규칙/템플릿으로 동작
- 출처 표기: 날씨 정보 출처 기상청(공공누리 제1유형)

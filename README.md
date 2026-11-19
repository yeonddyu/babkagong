# 밥카공 (BabCaGong)

강남역·역삼역 일대에서 **식사할 곳과 식사 후 카공할 카페를 함께** 추천하는 AI Agent 웹서비스 (SSAFY AI 코어 3회차).
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
첫 요청 전에 외부 데이터 캐시를 미리 만들어 두면 응답이 빠르다 (약 5분, 지역 필터 없는 API 전체 순회)
```bash
cd backend && ../.venv/bin/python -m scripts.build_cache
```

## 테스트
```bash
cd backend && ../.venv/bin/python -m pytest                      # Mock 단위 테스트 (233)
cd backend && ../.venv/bin/python -m pytest -m integration -rs   # 실제 외부 API (키가 없으면 BLOCKED skip)
cd backend && ../.venv/bin/python -m scripts.run_scenarios       # 대표 시나리오 10개 (실제 API) → docs/scenario_results.md
cd backend && ../.venv/bin/python -m scripts.verify_apis         # API 연결 검증 (키 마스킹)
.venv/bin/python backend/scripts/check_secrets.py                # 저장소에 키 값이 없는지 점검
cd frontend && npm test && npm run build
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
- OpenAI 키 없음: 요청 분석·응답 문장은 규칙/템플릿으로 처리 (LLM 경로는 코드·스텁 테스트만)
- SSAFY GMS: 키만 등록, 모델 연동은 범위 밖
- 출처 표기: 날씨 정보 출처 기상청(공공누리 제1유형)

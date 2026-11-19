# CLAUDE.md — 밥카공 개발 규칙

## 프로젝트
- 밥카공: 강남역·역삼역 일대 식사 + 카공 카페 코스 추천 AI Agent 웹서비스 (SSAFY AI 코어 3회차)
- 최상위 요구사항: `AI코어프로젝트_3회차_요구사항정의서.pdf` (대외비, 커밋 금지) — F3001~F3019, NF3001~NF3007
- 진행 상태: `PLAN.md`, 요구사항 매핑: `docs/requirements_matrix.md`

## 기술 스택
- Backend: Python 3.12, FastAPI, Pydantic v2, SQLAlchemy 2 + SQLite, requests
- Agent: LangGraph 1.2.10, LangChain 1.3.14, langchain-openai 1.4.3 (OpenAI). SSAFY GMS 는 키만 등록, 연동하지 않음
- Frontend: Vue 3 + TypeScript + Vite
- Test: pytest (backend), vue-tsc + vite build + vitest (frontend)

## 디렉터리
```
backend/
  app/core/       설정(.env), 오류 코드, 좌표, LLM provider
  app/clients/    외부 API Client (레드테이블, 서울 열린데이터, 카카오, 기상청)
  app/datasets/   외부 데이터 정규화·로컬 캐시
  app/tools/      Tool 공통 형식, 레지스트리, 개별 Tool
  app/agent/      LangGraph 메인 Agent (분석·계획·실행·판단·재계획·응답, 맥락)
  app/events/     이벤트 버스(발행·구독), 로깅 서브 Agent
  app/storage/    SQLite 모델·리포지토리 (계획, 실행 로그, 대화 맥락)
  app/api/        FastAPI 라우터
  tests/unit/     Mock 단위 테스트 (외부 호출 없음)
  tests/integration/  실제 API 호출 (pytest -m integration)
  scripts/        Tool 명세 출력, API 검증, 캐시 구축
frontend/         Vue 3 앱
docs/             설계·검증 문서
```

## 실행
```bash
cd backend && ../.venv/bin/python -m pytest            # 단위 테스트
cd backend && ../.venv/bin/python -m pytest -m integration -rs   # 실제 API
cd backend && ../.venv/bin/uvicorn app.main:app --reload --port 8000
cd frontend && npm run dev
```

## 코딩 규칙
- Tool 은 항상 `{"ok","data","error"}` envelope 으로 응답하고 예외를 밖으로 던지지 않는다.
- 외부 API 에서 확인되지 않은 값(가격·영업시간·거리·편의시설)은 null 로 두고 생성하지 않는다.
- 서로 다른 출처의 ID 를 같은 장소로 연결하지 않는다.
- 모델 판단이 필요 없는 작업(계획 저장, 제약 계산)은 Tool/LLM 이 아니라 코드로 수행한다.
- 로깅 Agent 는 LLM 을 쓰지 않는다. 이벤트 발행 쪽은 구독자를 모른다.

## 보안
- API 키는 `.env` (저장소 루트)에만. 코드·문서·로그·응답에 값 출력 금지. `key_status()` 로 존재 여부만 확인.
- 사용자 응답에는 내부 예외 상세를 넣지 않는다.

## 테스트 판정
- PASS: 검증 기준을 실제로 충족 / FAIL: 실행했으나 실패 / BLOCKED: 외부 의존성으로 검증 불가
- Mock 통과 ≠ 실제 API 연동 성공. 실행하지 않은 테스트는 PASS 로 보고하지 않는다.

## Git
- 요구사항 ID 단위: 구현 → 테스트 → 관련 파일만 stage → 커밋 (Conventional Commits)
- `git add .`/`-A` 금지, `.env`·키·PDF 커밋 금지
- push, amend, rebase, reset, force push 는 사용자 승인 후에만
- 커밋 메시지에 AI 공동작성자(Co-Authored-By) 줄을 넣지 않는다

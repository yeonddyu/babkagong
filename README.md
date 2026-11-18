# 밥카공 (AI 식사 메뉴 결정 + 주변 카공 카페 추천 Agent)

서비스 지역: 서울 강남역·역삼역 일대. 현재 단계(STEP 1)는 Agent 가 사용할 Tool(F3001~F3004)만 구현한다.

## 구조

```
app/
  core/      설정(.env), 공통 오류 코드
  clients/   외부 API Client (Tool 과 분리)
  tools/     Tool 공통 형식, 레지스트리, 개별 Tool
scripts/     Tool 명세 출력, 실제 API 검증 스크립트
tests/
  unit/        Mock 단위 테스트 (외부 호출 없음)
  integration/ 실제 API 통합 테스트 (키 필요, -m integration)
docs/        Tool 명세서, API 연결 검증 기록
```

## 실행 방법

```bash
python3.12 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env   # 발급받은 키를 .env 에만 입력
```

Mock 단위 테스트 (기본):

```bash
.venv/bin/python -m pytest -v
```

실제 API 통합 테스트 (키가 없는 API 는 skip 으로 표시됨):

```bash
.venv/bin/python -m pytest -m integration -v -rs
```

등록된 Tool 목록·스키마 출력:

```bash
.venv/bin/python -m scripts.print_tools
```

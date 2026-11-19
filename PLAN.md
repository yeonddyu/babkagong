# PLAN — 밥카공 구현 진행 상태

상태: TODO / IN_PROGRESS / PASS / FAIL / BLOCKED. "단위"는 Mock 단위 테스트, "실제"는 실제 외부 API·LLM 검증.
Codex 독립 검증 결과는 별도 열에 기록한다 (Claude Code 자체 검증과 구분).

| ID | 내용 | 단위 | 실제 | 상태 | 커밋 | Codex |
|---|---|---|---|---|---|---|
| F3001 | Tool 명세 정의 및 등록 | PASS | 해당 없음 | PASS | c1e33eb | - |
| F3002 | 음식점 후보 조회 | PASS | TODO | IN_PROGRESS | 7de2352 | - |
| F3003 | 음식점 상세정보 조회 | PASS | TODO | IN_PROGRESS | 296297b | - |
| F3004 | 주변 카페 검색 | PASS | BLOCKED (카카오 앱 카카오맵 비활성) | IN_PROGRESS | 24b6aeb | - |
| weather | 기상청 날씨 조회 | TODO | TODO | TODO | | - |
| F3005 | 사용자 요청 분석 | TODO | BLOCKED (OPENAI_API_KEY 없음) | TODO | | - |
| F3006 | 작업 계획 수립 | TODO | | TODO | | - |
| F3007 | Tool 호출 및 결과 통합 | TODO | | TODO | | - |
| F3008 | 제약 적합성 판단 | TODO | | TODO | | - |
| F3009 | 재계획 | TODO | | TODO | | - |
| F3010 | 대화 맥락 유지 | TODO | | TODO | | - |
| F3011 | 최종 응답 생성 | TODO | | TODO | | - |
| F3012 | 실행 이벤트 발행 | TODO | | TODO | | - |
| F3013 | 실행 로그 저장 | TODO | | TODO | | - |
| F3014 | 실행 로그 조회·삭제 | TODO | | TODO | | - |
| F3015 | 계획 저장·조회 | TODO | | TODO | | - |
| F3016 | 계획 수정·삭제 | TODO | | TODO | | - |
| F3017 | 백엔드 API 서버 | TODO | | TODO | | - |
| F3018 | 프론트엔드 화면 | TODO | | TODO | | - |
| F3019 | 실행 과정·상태 표시 | TODO | | TODO | | - |

| NF | 내용 | 상태 |
|---|---|---|
| NF3001 | API 키 환경변수 관리 | TODO |
| NF3002 | 화면 노출 제한 | TODO |
| NF3003 | Tool 실패 처리 | TODO |
| NF3004 | 재계획 상한 | TODO |
| NF3005 | 응답 시간 | TODO |
| NF3006 | 모듈 분리 | TODO |
| NF3007 | 출처·이용 조건 | TODO |

## 외부 의존성 현황 (2026-11-19)
| 항목 | 상태 |
|---|---|
| 서울관광재단(레드테이블) | 키 설정, 실제 호출 200 |
| 서울 열린데이터광장 | 키 설정, 실제 호출 200 |
| 카카오 로컬 | 키 설정, **403 App disabled OPEN_MAP_AND_LOCAL** → 앱에서 카카오맵 활성화 필요 |
| 기상청 단기예보 | 키 설정, 실제 호출 200 |
| OpenAI | **키 없음** → LLM 경로 BLOCKED, 규칙 기반 대체 경로로 동작 |
| SSAFY GMS | 키만 등록 (연동 범위 밖) |

## 진행 순서
환경 확인 → 설계 문서 → STEP1 보완 → weather → F3005~F3011 → F3012~F3016 → F3017~F3019 → 통합·시나리오·NF 검증 → 최종 보고

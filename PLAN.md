# PLAN — 밥카공 구현 진행 상태

상태: TODO / IN_PROGRESS / PASS / FAIL / BLOCKED. "단위" = Mock 단위 테스트, "실제" = 실제 외부 API·브라우저 검증.
**Codex 독립 검증은 아직 수행되지 않았다** (아래 Codex 열은 모두 미검증). 이 문서의 PASS 는 Claude Code 자체 검증 결과다.

최종 갱신: 2026-11-19

| ID | 내용 | 단위 | 실제 | 상태 | 주요 커밋 | Codex |
|---|---|---|---|---|---|---|
| F3001 | Tool 명세 정의 및 등록 | PASS | 해당 없음 | PASS | c1e33eb | 미검증 |
| F3002 | 음식점 후보 조회 | PASS | PASS (레드테이블·인허가 실제 호출) | PASS | 7de2352, de6c462 | 미검증 |
| F3003 | 음식점 상세정보 조회 | PASS | PASS (후보 ID → 상세 실제 호출) | PASS | 296297b, 6c53d15 | 미검증 |
| F3004 | 주변 카페 검색 | PASS | PASS (카카오 실제 호출 2026-11-19 카카오맵 활성화 후, 보조 출처 휴게음식점도 PASS) | PASS | 24b6aeb, 89a2176, cfa4460 | 미검증 |
| weather | 기상청 날씨 조회 | PASS | PASS | PASS | 0f5e27d | 미검증 |
| F3005 | 사용자 요청 분석 | PASS | 규칙 경로 PASS / **LLM 경로 BLOCKED** (OPENAI_API_KEY 없음) | PASS (규칙) | 730901d, f09a082 | 미검증 |
| F3006 | 작업 계획 수립 | PASS | PASS (시나리오 S1·S5·S6) | PASS | 9bddf88 | 미검증 |
| F3007 | Tool 호출 및 결과 통합 | PASS | PASS (S1·S4) | PASS | d08983a | 미검증 |
| F3008 | 제약 적합성 판단 | PASS | PASS (S1~S3) | PASS | d5193e7, f373ea3, bc2851f | 미검증 |
| F3009 | 재계획 | PASS | PASS (S2 재계획, S3 상한) | PASS | e31408f | 미검증 |
| F3010 | 대화 맥락 유지 | PASS | PASS (S8) | PASS | dd56ea1 | 미검증 |
| F3011 | 최종 응답 생성 | PASS | 템플릿 PASS / LLM 문장 BLOCKED | PASS (템플릿) | ad30e41, d21a0c8 | 미검증 |
| F3012 | 실행 이벤트 발행 | PASS | PASS | PASS | 51e10bc | 미검증 |
| F3013 | 실행 로그 저장 | PASS | PASS (실서버 SQLite) | PASS | 57c6905 | 미검증 |
| F3014 | 실행 로그 조회·삭제 | PASS | PASS (API) | PASS | 5cdc6b4 | 미검증 |
| F3015 | 계획 저장·조회 | PASS | PASS (S9·S10, 브라우저) | PASS | b75eae3 | 미검증 |
| F3016 | 계획 수정·삭제 | PASS | PASS (브라우저 수정 반영) | PASS | f0fc2de (실패 상태 커밋), ca1879d (수정) | 미검증 |
| F3017 | 백엔드 API 서버 | PASS | PASS (uvicorn 실기동) | PASS | 4466d98 | 미검증 |
| F3018 | 프론트엔드 화면 | PASS (vitest·build) | PASS (브라우저 실연동) | PASS | fbc308f | 미검증 |
| F3019 | 실행 과정·상태 표시 | PASS | PASS (브라우저 실시간 진행·재계획 표시) | PASS | 494becf | 미검증 |

| NF | 내용 | 근거 | 상태 |
|---|---|---|---|
| NF3001 | API 키 환경변수 관리 | `.env` 만 사용, `scripts/check_secrets.py` 결과 키 포함 파일 없음 | PASS |
| NF3002 | 화면 노출 제한 | API 오류 공통 형식·내부 예외 미노출 테스트, 타임라인은 오류 코드 안내만 | PASS |
| NF3003 | Tool 실패 처리 | 레지스트리 예외 차단, 출처별 격리, S4 (날씨 키 없음) 추천 계속, 카카오 실패 시 보조 출처 전환(통합 테스트) | PASS |
| NF3004 | 재계획 상한 | MAX_REPLANS=3, S3 에서 3회 후 중단 | PASS |
| NF3005 | 응답 시간 | 대표 요청 0.0~3.1초 (캐시 구축 후). 첫 캐시 구축은 약 5분 → `scripts.build_cache` 로 사전 구축. 상세조회 160ms→0.2ms 개선 | PASS (조건부) |
| NF3006 | 모듈 분리 | backend/frontend 분리, agent·tools·clients·events·storage·api 파일 분리 | PASS |
| NF3007 | 출처·이용 조건 | `docs/api_verification.md` | PASS |

## 남은 외부 조치
| 항목 | 조치 |
|---|---|
| OpenAI | `.env` 에 `OPENAI_API_KEY` 설정 후 LLM 경로 검증 |
| Codex | 독립 검증 수행 |

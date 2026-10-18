# 지표·데이터 계획 v1.3.0 검증 기록

2026-10-18 (한국 시간), 기반 main d09e99b. CR-0003 / WBS 1.9–1.19 인계. 이번 변경은 문서·기준선 등록이며 지표/원천/모델/주문 기능 구현이 아니다.

- 새 WBS: 47개. 기존 상태 보존(16 done / 1 in_progress / 1 blocked), 신규 11개 모두 not_started로 전체 미착수 29개.
- 기존 v1.0 설계·v1.1/v1.2 WBS/해시 불변을 검사했다. 새 v1.3 WBS SHA-256: `3414ae2e001899c8b86e1b6c25b1b57238ca683b50d0320d0f0c2c914555b147`. 생성 시 현행 WBS와 새 기준선 바이트 일치를 확인했다.
- 선행 조건: 3.2의 3.1/0.6 보존 + 1.19 추가, 4.1에도 1.19 추가. 순환/선행 일정·완료 증거 검사 통과, 기존 작업의 상대 일정을 앞당기지 않았다. D+n은 달력 납기가 아니다.
- 설계의 전체 지표 그룹 매핑·선택/제외 범위, 제안 저장 구조/실행 DAG와 현재 미구현 표시를 직접 검토했다. 원문 첨부의 개인 이름/담당 일정·비밀·시장 원자료는 추가하지 않았다.
- README/AGENTS/인계/설계/운용 설계/STATUS/WBS의 로컬 상대 링크 존재 검사 통과.
- `scripts/project_status.py --write/--check`, `ruff check`, `ruff format --check`, `git diff --check` 통과.
- `bash scripts/check.sh`: macOS / Python 3.12.14, **184 tests passed**, Starlette TestClient/httpx 사용 중단 예정 경고 1개. 이전 계획에서 새 기준선 변조 회귀 1개가 추가된 수치다. 앱의 실제 외부 수집/모델/브로커 호출을 검증한 결과가 아니다.
- 원격 CI는 [GitHub Actions](https://github.com/domino721/AI_Trader/actions?query=branch%3Amain)의 해당 게시 커밋 결과로 확인한다. 이전 d09e99b의 183개 성공을 새 계획 검증 결과로 대체하지 않는다. 게시 후의 최종 CI 결과/소스 tree 일치는 전달 기록에서 별도로 확인한다.

다음 Agent는 `docs/AGENT_HANDOFF.md`를 읽고 WBS 1.9 실제 데이터 실물/복원 확인부터 시작한다. 실제 Windows PC 수용·모델/예산·투자금/계좌 권한·모의/실거래 게이트는 여전히 미완료다.

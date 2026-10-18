# CR-0002 운영 기반·무결성 검증 기록

2026-10-18, Asia/Seoul. 기반 원격 8b53bdd. 계획 1.2.0, CR-0002. 상세 외부 수용 잔여는 ../OPERATIONS.md 및 ../TRADING_READINESS.md를 참조합니다.

- 수정 전 재현: `.local/audit-repro`에 원칙 스냅샷을 생성하고 chunk 제목을 변조한 뒤 load/search가 통과하는 사실을 확인했습니다. 해당 파일은 Git 제외입니다.
- 파서/청크 v2: 원문 해시·청크/문서 메타데이터·전체 ID·정정/권한·중복·레거시를 검색 전에 검증합니다. 48k 무표시 절단과 청크 경계 누락을 수정했습니다.
- 코드 검증: 환경 혼용·prod 인증 누락·잘못된 한도·의존성 역행·동시 claim·소유권 상실·실제 프로세스 강제 종료·예약 구간 중복/누락·백업 환경/무결성/경로·보호 API·DB 준비 실패를 포함합니다.
- 로컬 실제 CLI: `AI_TRADER_STATE_DIR=.local/ops-check ai-trader ops run --run-id review-first`의 네 단계가 succeeded. 생성한 지식 v2 스냅샷은 3문서 9청크. 마지막 모델은 합성 근거의 offline_fixture이며 실제 RAG 분석/브로커/외부 모델 호출이 아닙니다.
- 실제 집 Windows PC의 설치/서비스/로그온·재부팅·절전·단절·NTFS ACL·외부 경보·복원은 미검증입니다. CI와 개발 호스트의 결과로 대신 완료 표시하지 않습니다.
- PowerShell 스크립트는 비밀을 출력하지 않는 토큰 파일 생성/ACL 검사, simulation 고정·루프백·단일 worker 시작, 사용자 로그온 TaskScheduler/제한 재시작을 제공하며 실제 대상 PC에 설치하지 않았습니다.
- 실제 모델/브로커 호출·원주문·계좌 데이터 조회·기존 원자료/계좌 비밀의 외부 전송은 하지 않았습니다.

## 최종 로컬 검증

- `bash scripts/check.sh`: 기준선/WBS·Ruff 검사/포맷과 **183개 테스트 통과**. 이후 최종 경로/무결성 보완은 knowledge/ops **66개 회귀 통과**. 테스트 환경은 macOS, Python 3.12.14입니다.
- 단일 경고: Starlette TestClient의 httpx 사용 중단 예정 안내. 현재 테스트 실패는 아니며 의존성 교체는 이번 변경에 포함하지 않았습니다.
- `uv build --offline`: wheel/sdist 생성 성공. 앱의 ops/static 자산, 운영 모듈 및 sdist의 Windows 스크립트 포함을 검사하고 `.local`·실제 `.env`·DB/원자료가 패키지에 포함되지 않음을 확인했습니다. uv의 소스 안 캐시 경고가 있었으나 실제 아카이브 내용으로 제외를 확인했습니다.
- 실제 로컬 HTTP/브라우저: `ui-verification-20261018` 네 단계 완료 확인. `ui-failure-20261018`은 과거 평가 시각(2020)을 지정해 출처 검증을 의도적으로 실패시켰으며 첫 단계 failed·후속 blocked·로컬 경보 표시를 확인했습니다. 토큰/원문/전체 예외는 화면에 표시하지 않았습니다. 최종 화면에는 구현상 식별자 대신 한글 상태/원인·요약을 표시합니다.
- 사용자 AGENTS의 제한된 Opus QA 경로를 코드/합성 테스트만으로 1회 시도했으나 Antigravity가 완료되지 않아 **외부 모델 검토 결과 없음**. 권한 완화/다른 모델/반복 시도 없이 로컬 테스트와 직접 검토로 확인했습니다. 앱의 실제 모델 호출은 계속 비활성입니다.
- Windows CI 행렬과 PowerShell ParseFile 검사를 추가했지만 게시 전에는 원격 실행 결과가 없습니다. 실제 집 Windows PC 수용 0.6은 blocked입니다.

계정 권한·실제 모델/백테스트·브로커 모의·실거래 준비는 미완료로 유지합니다. Git 게시 여부와 CI 결과는 전달 보고서에서 별도로 기록합니다.

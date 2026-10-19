# AI Trader

가치·모멘텀·퀀트 관점의 근거 있는 투자 연구와 독립 위험관리, 백테스트 → 브로커 모의매매 → 제한적 실거래를 목표로 합니다.

**현재 판정: 연구·운영 기반 개발 중이며 실제 자금 자동 거래는 미준비입니다.** 데이터 수집·검수와 지식 출처/검색의 소규모 검증, 오프라인 모델 호출 기반, 단일 호스트 운영 현황판이 있습니다. 실제 AI 토론·연속 포트폴리오 백테스트·브로커 주문/잔고 대사는 아직 없습니다. 합성 데모의 성과는 투자 수익성 증거가 아닙니다.

[다음 Agent 인계](docs/AGENT_HANDOFF.md) · [지표·데이터 설계](docs/INDICATOR_DATA_DESIGN.md) · [검토 결과·문제·실거래까지의 조건](docs/TRADING_READINESS.md) · [현재 실적](docs/management/STATUS.md) · [WBS](docs/WBS.md) · [운영 지침](docs/OPERATIONS.md)

## 시작하기

Python 3.12와 uv를 사용합니다. 저장소 루트에서 실행합니다.

```bash
bash scripts/setup.sh
bash scripts/check.sh
uv run --frozen ai-trader demo --request-id first-demo
uv run --frozen ai-trader ops run --run-id first-research-check
bash scripts/serve.sh
```

Windows 설치·보호 토큰·로그온 자동 시작은 [Windows 운영 지침](docs/OPERATIONS.md)을 따릅니다. 실제 집 Windows PC의 설치·재부팅·절전·NTFS 권한·외부 경보·복원 수용은 아직 미완료입니다.

`http://127.0.0.1:8000/ops`에서 연구 점검을 실행하고 단계별 상태와 오류를 확인합니다. 현재 DAG는 원칙 문서 검증 → 색인 → 고정 검색 평가 → 합성 근거의 모의 모델입니다. 마지막 단계는 실제 RAG AI 연결이 아니며 외부 호출·주문을 만들지 않습니다. 로컬 경보만 제공하고 외부 이메일/메신저·PC 정지 감시는 미연결입니다.

## 환경·API

`AI_TRADER_ENVIRONMENT=dev|test|prod`와 별도 상태 경로를 사용합니다. 기본은 dev 및 `.local/dev`이며 기존 `.local`은 자동 이동하지 않습니다. prod는 절대 상태 경로와 최소 32자 `AI_TRADER_API_TOKEN`을 요구합니다. 상태 경로를 다른 환경과 공유하면 환경 소유권 검증이 거부합니다. 토큰·설정·백업도 환경별로 분리합니다.

prod는 **연구 운영 환경**이며 실거래 모드가 아닙니다. `AI_TRADER_EXECUTION_MODE`는 simulation만 허용합니다. 투자금·일손실·최대낙폭은 미정이며 데모의 USD 10,000은 실제 설정이 아닙니다. 실제 주문 허용 경로는 없습니다.

운영/데이터/데모 API는 토큰이 설정되면 Bearer 인증을 요구합니다. `/health`는 기본 프로세스 응답, `/ready`는 인증된 DB 쓰기·실행기 생존 점검입니다. `/ops/readiness`의 `runtime_ready`와 `live_trading_ready`는 별개이며 후자는 false입니다. 단일 worker·루프백 바인딩으로 시작합니다. 외부 노출/원격 접속은 별도 접근 경계 검증이 필요합니다.

`.env`는 선택 사항이며 비밀은 채팅/Git에 넣지 않습니다. 셸 환경변수가 `.env`보다 우선합니다. `.venv`, `.local`, 원자료·DB·비밀 설정은 Git 제외입니다. `uv.lock`과 `uv sync --locked`로 의존성을 고정합니다. 빌드는 `uv build`입니다.

## 데이터·지식·모델

```bash
uv run --frozen ai-trader data collect
uv run --frozen ai-trader data replay <snapshot_id>
uv run --frozen ai-trader llm-smoke
uv run --frozen python scripts/project_status.py --check
```

실제 수집은 네트워크·SEC 연락 식별 설정과 공급자 이용 조건 확인이 필요합니다. [데이터 MVP](docs/DATA_MVP.md)와 [연결 검증](docs/management/DATA_VALIDATION_2026-10-15.md)을 참조합니다. 연구 자료의 승인은 역사적 시점 일관성·상장폐지·전체 재무 분석·거래용 데이터 권한의 인증을 뜻하지 않습니다.

[지식 계약](docs/KNOWLEDGE_CONTRACT.md)은 출처·이용 권한·시점·정정·원문/청크 해시를 관리합니다. 원칙 3개와 공개 논문·SEC 본문 표본의 기존 검증 기록이 있습니다. 외부 원문은 Git 제외이므로 새 환경에는 허용된 고정 원문을 따로 복원해야 합니다. 파서/청크 v2는 무결성 검증과 문서 끝 누락을 보완합니다. v1 스냅샷은 현재 검색에서 거부하며 고정 원문으로 재색인해야 합니다.

[모델 호출 기반](docs/LLM_FOUNDATION.md)은 offline_fixture만 사용합니다. 공급자·모델·월 예산과 실제 연결 검증은 미정입니다. 검색의 고정 회귀 평가를 수익성이나 모델의 수치 계산 정확도로 해석하지 않습니다.

## 구조와 계획

| 모듈 | 현재 역할 |
| --- | --- |
| data | 공급자 표본 수집·검수·격리·원본/Parquet/스냅샷·재생 |
| knowledge | 출처/권한/시점 계약·간단한 파싱/검색·고정 평가 |
| llm | 모의 공급자·호출 예약/중복 방지·실패 처리·응답 보존 |
| ops | 영속 실행/단계 DAG·heartbeat·주기 점검·현황판·오프라인 백업/복원 |
| research/risk/execution | 합성 분석·위험 규칙·독립 1회 가상 체결 데모 |
| api/cli | 인증 가능한 연구 운영 API·명령 진입점 |

데이터 확장 계획 [CR-0003](docs/changes/CR-0003.md)은 지표·재무·피처·시장 데이터 운영 작업 1.9–1.19를 추가했습니다. 운영 기반은 CR-0002에 기록하며 이전 기준선은 보존합니다. 전체 47개 중 16개 완료, 3.1 진행, 0.6 대상 Windows PC 수용 차단, 29개 미착수입니다. 신규 11개는 계획이며 구현하지 않았습니다. 완료 개수는 실거래 준비율이 아닙니다.

[설계](docs/PROJECT_PLAN.md) · [결정/미정](docs/DECISIONS.md) · [운용 역할](docs/OPERATING_MODEL.md) · [변경관리](docs/management/CONTROL.md) · [최신 검증](docs/management/OPS_VALIDATION_2026-10-18.md)

현재 계획은 **v1.4.0 / [CR-0004](docs/changes/CR-0004.md)**입니다. [PM·최종 결정 백테스트 설계](docs/PORTFOLIO_BACKTEST.md)에 분산·공분산·위험 기여·비중 구성 책임과 회의 최종 결정 전체의 생성/오프라인 재생·토론 × PM 비교를 추가했습니다. 설계이며 실제 PM/역사적 백테스트 구현은 아직 없습니다. 기존 지표·운영·모델 게이트와 WBS 상태를 유지합니다.

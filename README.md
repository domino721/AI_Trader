# AI Trader

가치투자·모멘텀·퀀트 관점의 AI가 근거를 제시하고 토론한 뒤, 독립적인 위험관리 규칙을 통과한 포트폴리오를 실행하는 프로젝트입니다.

**현재 단계: 개발 기반 + 데이터 수집·검수 MVP 코드.** 실제 공급자 연결은 별도 게이트로 확인하며, 실제 LLM·RAG·증권사 연결은 아직 없습니다. 포함된 의사결정 데모는 가짜 종목 `DEMO_A/B`와 규칙 기반 분석을 사용해 분석 → 의견 취합 → 위험 검사 → 가상 체결 → 기록 흐름을 검증합니다. 투자 수익률이나 전략 성능을 입증하는 백테스트가 아닙니다.

설계: [프로젝트 계획](docs/PROJECT_PLAN.md) · [확정 사항과 보류 사항](docs/DECISIONS.md) · [환경 검증 기록](docs/VALIDATION.md)

진행 관리: **[WBS 현황](docs/WBS.md)** · [실적·차단 사항](docs/management/STATUS.md) · [기준선·변경관리](docs/management/CONTROL.md). [운용 역할과 뉴스 활용](docs/OPERATING_MODEL.md), [데이터 MVP 사용법](docs/DATA_MVP.md)에서 설계와 현재 구현을 구분합니다.

```bash
uv run --frozen ai-trader data collect
uv run --frozen ai-trader data replay <snapshot_id>
uv run --frozen python scripts/project_status.py --check
```

데이터 수집은 네트워크 허용과 실제 연락 정보가 포함된 `AI_TRADER_SEC_USER_AGENT` 설정이 필요합니다. 가격·기업행위와 공시 **메타데이터**를 검수하고 원본/스냅샷/Parquet로 저장합니다. 이 결과는 연구용이며 과거 시점 백테스트나 주문 승인이 아닙니다. 키 없는 합성 데모와 수집 기능은 분리되어 있습니다.

## 시작하기

Python 3.12와 uv가 필요합니다. 이 클라우드에는 Python 3.12.14와 uv 0.12.23이 설치되어 있습니다. 아래 명령은 저장소 루트에서 실행합니다.

```bash
cd /workspace/AI_Trader
bash scripts/setup.sh
bash scripts/check.sh
uv run --frozen ai-trader demo --request-id first-demo
bash scripts/serve.sh
```

마지막 명령은 API를 포그라운드로 실행합니다. 다른 셸에서 내부 요청으로 확인합니다.

```bash
curl --fail --silent http://127.0.0.1:8000/health
curl --fail --silent -X POST http://127.0.0.1:8000/demo/runs \
  -H 'Content-Type: application/json' -d '{"request_id":"first-api-demo"}'
curl --fail --silent http://127.0.0.1:8000/demo/runs/first-api-demo
uv run --frozen python scripts/smoke.py
```

동일 `request_id`는 저장된 결과를 반환합니다. 각 새 데모는 USD 10,000 현금에서 시작하는 독립 실험입니다. 계좌를 이어서 운용하거나 외부 주문을 보내지 않습니다. 차단 스위치도 과거 결과 조회를 바꾸지 않습니다. 설정을 바꾸어 새 실험을 할 때는 새 ID를 사용하세요. API 인증은 아직 없으므로 개발용 루프백에만 바인딩합니다.

## 구성

| 경로 | 역할 |
| --- | --- |
| `src/ai_trader/domain.py` | 분석 근거·의견·위험 검사·가상 체결의 Pydantic 계약 |
| `research.py`, `fixture.py` | 명시적으로 표시된 규칙 기반 샘플 분석과 합성 입력 |
| `risk.py` | 종목·총노출·현금·회전율·차단 스위치 검사 |
| `execution.py` | 의사결정 이후 시가, 수수료·슬리피지를 반영한 1회 가상 매수 |
| `store.py`, `service.py` | SQLite 데모 결과 기록과 요청 중복 방지 |
| `api.py`, `cli.py` | FastAPI 및 CLI 개발 진입점 |
| `tests/` | 시간 경계, 위험 차단, 비용, 재실행·API 동작 검증 |

Python/uv + FastAPI/Pydantic + NumPy/pandas/DuckDB + SQLite + pytest/Ruff를 사용합니다. 당장은 GPU, Docker, Redis, 외부 DB, LLM API 키가 필요 없습니다. 실제 증권사 모의계좌도 연결하지 않았습니다.

## 설정·재현성

`.env`는 선택 사항이며 기본 설정으로 실행됩니다. `.env.example`에는 비밀이 없는 예시만 있습니다. `AI_TRADER_EXECUTION_MODE`는 `simulation`만 허용합니다. `AI_TRADER_KILL_SWITCH=true`는 새 데모의 체결을 차단합니다. `AI_TRADER_STATE_DIR` 기본값은 작업 디렉터리 기준 `.local`입니다. 셸 환경변수가 `.env`보다 우선합니다.

`uv.lock`을 유지하고 설치에는 `uv sync --locked`를 사용합니다. `uv.toml`은 캐시를 `.local/uv-cache`에 둡니다. `.venv`, `.local`, 원자료와 비밀 설정은 Git에서 제외됩니다. 로컬 SQLite는 데모 감사 기록만 저장하며 실거래 장부를 대체하지 않습니다. 빌드는 `uv build`로 확인합니다.

다음 개발 목표는 공개 자료의 출처·시점 관리와 검색, 실제 LLM의 구조화된 분석·반론, 기준 전략과 비교할 시점 일관성 있는 백테스트입니다. [단계별 완료 조건](docs/PROJECT_PLAN.md)을 따릅니다.


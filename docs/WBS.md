# WBS 진행 현황

계획 버전 **1.2.0** · 기준일 2026-10-15 (한국 시간) · 실적 갱신 2026-10-18

이 파일은 `docs/management/wbs.toml`에서 생성합니다. `uv run --frozen python scripts/project_status.py --write`로 갱신하고 Git에 함께 커밋합니다.

D+n은 승인된 일정 기준점 이후 계획 작업일입니다. 의존성 기반 초안 추정이며 달력 마감일·자동 작업 예약이 아닙니다. 관찰 기간·접근권한·예산에 따라 달라지는 예측은 아래 차단 사유에 기록하고, 기준 일정 변경은 CR과 새 버전으로 남깁니다.

전체 36개 작업 중 16개 완료. 게이트가 통과하기 전에는 해당 단계 완료나 다음 단계 운용 준비를 주장하지 않습니다.

| WBS | 단계 / 작업 | 담당 기능 | 선행 작업 | 기준 일정 / 예상 작업일 | 상태 | 실적 완료 | 근거 / 차단 사유 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 0.1 | 0/기반 / 기존 설계·코드 기준선 보존 | 개발 | — | D+0–1 / 1일 | 완료 | 2026-10-15 | [manifest.json](../docs/baselines/v1.0/manifest.json) |
| 0.2 | 0/기반 / WBS·CR·기준선 검증 체계 | 개발 | 0.1 | D+1–2 / 1일 | 완료 | 2026-10-15 | [CONTROL.md](../docs/management/CONTROL.md) |
| 0.3 | 0/운영 기반 / 개발/운영 환경 경계·API 인증·준비 상태 | 개발/운영 | 0.2, 2.3 | D+23–25 / 2일 | 완료 | 2026-10-18 | [settings.py](../src/ai_trader/settings.py), [test_ops.py](../tests/test_ops.py), [OPERATIONS.md](../docs/OPERATIONS.md) |
| 0.4 | 0/운영 기반 / 단일 호스트 DAG·영속 상태·중복/중단 통제 | 개발/운영 | 0.3 | D+25–28 / 3일 | 완료 | 2026-10-18 | [runner.py](../src/ai_trader/ops/runner.py), [test_ops.py](../tests/test_ops.py), [OPS_VALIDATION_2026-10-18.md](../docs/management/OPS_VALIDATION_2026-10-18.md) |
| 0.5 | 0/운영 기반 / 운영 현황판·로컬 경보·백업/복원 | 개발/운영 | 0.4 | D+28–30 / 2일 | 완료 | 2026-10-18 | [api.py](../src/ai_trader/api.py), [backup.py](../src/ai_trader/ops/backup.py), [test_ops.py](../tests/test_ops.py), [OPERATIONS.md](../docs/OPERATIONS.md) |
| 0.6 | 0/운영 기반 / 실제 Windows 데스크탑 운영 수용 | 개발/운영 | 0.5 | D+30–31 / 1일 | 차단 | — | [OPERATIONS.md](../docs/OPERATIONS.md), [TRADING_READINESS.md](../docs/TRADING_READINESS.md); 실제 집 Windows 데스크탑 설치·재부팅·절전/네트워크 단절·원격 경보·백업 복원은 미검증. 현 개발 호스트의 모의 테스트로 대체하지 않음. |
| 1.1 | 1/데이터 / 종목군·연구용 공급자 계약 | 데이터 | 0.2 | D+2–3 / 1일 | 완료 | 2026-10-15 | [DATA_MVP.md](../docs/DATA_MVP.md) |
| 1.2 | 1/데이터 / 가격·기업행위·공시 수집 어댑터 | 데이터 | 1.1 | D+3–5 / 2일 | 완료 | 2026-10-15 | [providers.py](../src/ai_trader/data/providers.py) |
| 1.3 | 1/데이터 / 독립 검수·격리·품질 보고서 | 검수 | 1.2 | D+5–7 / 2일 | 완료 | 2026-10-15 | [quality.py](../src/ai_trader/data/quality.py) |
| 1.4 | 1/데이터 / 원본·Parquet·스냅샷·고정 재생 | 데이터 | 1.3 | D+7–9 / 2일 | 완료 | 2026-10-15 | [archive.py](../src/ai_trader/data/archive.py) |
| 1.5 | 1/데이터 / 오프라인 실패 시나리오·회귀 검증 | 검수 | 1.4 | D+9–11 / 2일 | 완료 | 2026-10-15 | [test_data.py](../tests/test_data.py), [STATUS.md](../docs/management/STATUS.md) |
| 1.6 | 1/데이터 / 실제 가격·기업행위 연결 검증 | 데이터 | 1.5 | D+11–12 / 1일 | 완료 | 2026-10-15 | [DATA_VALIDATION_2026-10-15.md](../docs/management/DATA_VALIDATION_2026-10-15.md), [STATUS.md](../docs/management/STATUS.md) |
| 1.7 | 1/데이터 / 실제 SEC 공시 연결 검증 | 데이터 | 1.6 | D+12–13 / 1일 | 완료 | 2026-10-15 | [DATA_VALIDATION_2026-10-15.md](../docs/management/DATA_VALIDATION_2026-10-15.md), [STATUS.md](../docs/management/STATUS.md) |
| 1.8 | 1/데이터 / 데이터 MVP 종료 게이트 | 검수 | 1.7 | D+13–14 / 1일 | 완료 | 2026-10-15 | [DATA_VALIDATION_2026-10-15.md](../docs/management/DATA_VALIDATION_2026-10-15.md), [STATUS.md](../docs/management/STATUS.md) |
| 2.1 | 1/지식 / 문헌·공시 본문·권한·출처 계약 | 리서치 | 1.8 | D+14–17 / 3일 | 완료 | 2026-10-16 | [KNOWLEDGE_CONTRACT.md](../docs/KNOWLEDGE_CONTRACT.md), [KNOWLEDGE_VALIDATION_2026-10-16.md](../docs/management/KNOWLEDGE_VALIDATION_2026-10-16.md), [test_knowledge.py](../tests/test_knowledge.py), [catalog.json](../docs/knowledge/catalog.json), [public-catalog.json](../docs/knowledge/public-catalog.json) |
| 2.2 | 1/지식 / 파싱·청크·RAG 색인·시점 필터 | 개발 | 2.1 | D+17–21 / 4일 | 완료 | 2026-10-16 | [index.py](../src/ai_trader/knowledge/index.py), [KNOWLEDGE_CONTRACT.md](../docs/KNOWLEDGE_CONTRACT.md), [KNOWLEDGE_VALIDATION_2026-10-16.md](../docs/management/KNOWLEDGE_VALIDATION_2026-10-16.md), [test_knowledge.py](../tests/test_knowledge.py) |
| 2.3 | 1/지식 / 검색·인용 품질 게이트 | 검수 | 2.2 | D+21–23 / 2일 | 완료 | 2026-10-16 | [eval-benchmark.json](../docs/knowledge/eval-benchmark.json), [public-eval-benchmark.json](../docs/knowledge/public-eval-benchmark.json), [KNOWLEDGE_CONTRACT.md](../docs/KNOWLEDGE_CONTRACT.md), [KNOWLEDGE_VALIDATION_2026-10-16.md](../docs/management/KNOWLEDGE_VALIDATION_2026-10-16.md), [test_knowledge.py](../tests/test_knowledge.py) |
| 3.1 | 2/AI / 모델·호출 예산·공급자 어댑터 | 개발 | 2.3 | D+31–33 / 2일 | 진행 | — | [LLM_FOUNDATION.md](../docs/LLM_FOUNDATION.md), [test_llm.py](../tests/test_llm.py), [runtime.py](../src/ai_trader/llm/runtime.py), [LLM_VALIDATION_2026-10-17.md](../docs/management/LLM_VALIDATION_2026-10-17.md); 사용자 선택: 공급자·모델·월 예산 미정, 실제 호출 없이 기반 구현. 실제 공급자 연결·비용/시간 초과 검증은 추후. 3.2 미착수. |
| 3.2 | 2/AI / 철학별 분석·공식 이벤트 해석 | 리서치 | 3.1, 0.6 | D+33–37 / 4일 | 미착수 | — |  |
| 3.3 | 2/AI / 반론·PM·동조 통제·호출 한도 | 개발 | 3.2 | D+37–40 / 3일 | 미착수 | — |  |
| 3.4 | 2/AI / 제안·독립 위험 엔진 계약 | 위험 | 3.3 | D+40–43 / 3일 | 미착수 | — |  |
| 3.5 | 2/AI / AI 근거 품질 종료 게이트 | 검수 | 3.4 | D+43–45 / 2일 | 미착수 | — |  |
| 4.1 | 3/연구 / PIT 데이터·XBRL·종목군·정정 검증 | 데이터 | 3.5 | D+45–50 / 5일 | 미착수 | — |  |
| 4.2 | 3/연구 / 연속 포트폴리오 회계·백테스트 | 개발 | 4.1 | D+50–55 / 5일 | 미착수 | — |  |
| 4.3 | 3/연구 / 비교군·비용·기여 분해 | 리서치 | 4.2 | D+55–58 / 3일 | 미착수 | — |  |
| 4.4 | 3/연구 / Walk-forward·미사용 구간 검증 | 검수 | 4.3 | D+58–62 / 4일 | 미착수 | — |  |
| 4.5 | 3/연구 / 연구 종료·모의매매 진입 게이트 | 위험 | 4.4 | D+62–64 / 2일 | 미착수 | — |  |
| 5.1 | 4/모의 / 브로커·모의계좌·운영 한도 결정 | 사용자/개발 | 4.5 | D+64–66 / 2일 | 미착수 | — |  |
| 5.2 | 4/모의 / 주문 상태·영속 ID·대사·복구 | 실행 | 5.1 | D+66–71 / 5일 | 미착수 | — |  |
| 5.3 | 4/모의 / 스케줄·신선도·알림·조회 화면 | 운영 | 5.2 | D+71–75 / 4일 | 미착수 | — |  |
| 5.4 | 4/모의 / 전향 관찰·장애 훈련 | 운영 | 5.3 | D+75–95 / 20일 | 미착수 | — |  |
| 5.5 | 4/모의 / 모의 운용 종료 게이트 | 위험 | 5.4 | D+95–97 / 2일 | 미착수 | — |  |
| 6.1 | 5/실거래 / 실제 자본·종목·손실·승인 정책 | 사용자/위험 | 5.5 | D+97–99 / 2일 | 미착수 | — |  |
| 6.2 | 5/실거래 / 실거래 어댑터·환경 분리 검증 | 실행 | 6.1 | D+99–103 / 4일 | 미착수 | — |  |
| 6.3 | 5/실거래 / 제한 규모·수동 승인 운영 | 운영 | 6.2 | D+103–113 / 10일 | 미착수 | — |  |
| 6.4 | 5/실거래 / 운영 인계·정기 검토·확대 판단 | 사용자/운영 | 6.3 | D+113–115 / 2일 | 미착수 | — |  |

## 완료 기준

- **0.1**: 원래 설계 원문·해시와 Git 태그 보존
- **0.2**: 끝까지의 작업·의존성·완료 근거·일정 기준선 검증
- **0.3**: 환경 혼용·인증 누락 거부와 실제 저장소 readiness 부정 테스트 통과
- **0.4**: 단계 의존성·동시 실행·프로세스 중단·소유권 상실·후속 차단 검증
- **0.5**: 인증된 현황 조회·로컬 경보·무결성/환경 검사를 포함한 오프라인 복원 검증
- **0.6**: 실제 대상 PC의 설치·로그온/재부팅·절전·단절·외부 경보·복원 관찰 증거
- **1.1**: 표본·데이터 계약·이용 한계·출처 명시
- **1.2**: 재시도·체크포인트·공시 과거 페이지와 실패 보고 구현
- **1.3**: 커버리지·중복·단위·OHLC·시점 오류 시 승인 차단
- **1.4**: 불변 원본·정정 버전·체크섬·네트워크 없는 동일 재생
- **1.5**: 오류·재수집·정정·재생·API·CLI 테스트 및 전체 회귀 통과
- **1.6**: 실제 공급자에서 주식·ETF 수집·품질·재실행 증거 확보
- **1.7**: 실제 연락 식별 정보로 공시 요청·시점·재수집 검증
- **1.8**: 1.5·1.6·1.7 완료와 미해결 품질·사용 범위 검토
- **2.1**: 자료 목록·이용 조건·시점·판본·인용 위치 확보
- **2.2**: 같은 지식 스냅샷 재생·시점 필터·문서 지시 격리
- **2.3**: 고정 평가 세트에서 검색·인용·수치·시점 정확성 확인
- **3.1**: 모델·비용 결정·시간 초과·재시도·응답 보존
- **3.2**: 구조화 제안·인용·계산 도구·근거 부족 보류
- **3.3**: 독립 초안·제한 라운드·반론·포트폴리오 조정 기록
- **3.4**: AI가 한도·거부를 무시하지 못하고 실패 시 주문 없음
- **3.5**: 소규모 평가 세트·실패 처리·비용·동조 검증
- **4.1**: 공급자/예산·재무 단위·당시 정보·상장폐지·수정 이력 검증
- **4.2**: 현금·매수/매도·기업행위·시점·주문 지연·미체결 검증
- **4.3**: 단일 전략·단순 결합·토론·뉴스 기여와 비용 차감 비교
- **4.4**: 사전 고정 기준·과최적화·지식 오염 한계 보고
- **4.5**: 품질·위험·성과·재현성 근거와 운영 잔여 과제 확인
- **5.1**: 이용 자격·API·투자금 가정·손실 한도·알림 결정
- **5.2**: 중복·부분 체결·취소·거절·통신 장애·재시작 검증
- **5.3**: 거래 일정·계좌/데이터 신선도·경보·운영 조회
- **5.4**: 사전 합의 기간의 모의 관찰·장애/차단/복구 증거; 기간 추정은 미확정
- **5.5**: 대사·손실 통제·운영 부담·관찰 결과 검토
- **6.1**: 사용자가 실제 금액·권한·승인·중지/복구 범위를 명시적으로 결정
- **6.2**: 모의/실계좌 분리·중복/대사·위험/권한·제한 규모 검증
- **6.3**: 실거래 별도 승인 후 사전 합의 기간 관찰·실행 비용 확인
- **6.4**: 운영 지침·검증·변경 이력·재평가; 규모 확대는 별도 결정

변경관리: [관리 규칙](management/CONTROL.md) · [CR-0001](changes/CR-0001.md) · [CR-0002](changes/CR-0002.md) · [일일 현황](management/STATUS.md)

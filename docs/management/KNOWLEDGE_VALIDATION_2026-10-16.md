# WBS 2.1–2.3 지식 계약·스냅샷·RAG 색인·검색 인용 품질 게이트 검증 근거

2026-10-16, Asia/Seoul. 기반 코드 `db00a47`. 범위·일정 기준선 v1.1.0 보존. **WBS 2.1·2.2·2.3 모두 완료**, 다음 작업 WBS 3.1.

## 실제 확보·로컬 검증 (WBS 2.1 완료)

- `docs/knowledge/catalog.json`: 직접 작성한 가치·모멘텀·퀀트 원칙 문서 3개(각 3개 절 marker, 총 9개 위치). 각 파일의 실제 SHA-256·절 marker·저자·판본·내부 사용 목적·관측 시각을 고정했습니다.
- `docs/knowledge/public-catalog.json`:
  - 출판사 XML 1편(`plos-0300781`), HTTP 200, 318,832바이트. SHA-256 `6452ad7c7e9a0bf32ff067f21a0cdc38784ff79a46e18f6a3c62ac0b5cb67449`. XML의 논문 제목·CC BY 4.0 고지와 `sec001`–`sec003` 위치를 확인했습니다.
  - 실제 SEC EDGAR primary filing HTML 3편(초당 1회 이하 직렬 요청, `.env`의 연락 식별자 사용, 값 비노출):
    1. `aapl-2026-q3-10q` (Form 10-Q, accession `0000320193-26-000020`, accepted `2026-07-31T14:01:02Z`): HTTP 200, 1,018,319바이트, SHA-256 `40c9a3cbbb8eadfafd4e7fdb9e066e574f06698f259c76930d0aad63d431fda0`, 고유 위치 3개(`part1-item1`, `part1-item2`, `part2-item1a`).
    2. `msft-2026-fy-10k` (Form 10-K, accession `0001193125-26-323660`, accepted `2026-07-30T00:08:01Z`): HTTP 200, 8,585,610바이트, SHA-256 `4c10956124d938070271ae73162827ed6941e11b61e1fe896a9d61a11fad6dd8`, 고유 위치 4개(`item-1`, `item-1a`, `item-7`, `item-8`).
    3. `msft-2026-0902-8k` (Form 8-K, accession `0001193125-26-380280`, accepted `2026-09-03T00:30:24Z`): HTTP 200, 28,668바이트, SHA-256 `4878b564389f1b17e3842212751d42b2920dbd308fa069ef3ca2655934f964cb`, 고유 위치 2개(`item-7-01`, `item-9-01`).
- 외부 원문은 `.local/knowledge/raw/`에만 보관(Git 제외)하며, 두 카탈로그 모두 `ai-trader knowledge --catalog <목록> --as-of 2026-10-16T23:59:59+09:00`에서 적격(`status=passed`, 종료 0)을 확인했습니다.

## 파싱·청크·지식 스냅샷·시점 필터·지시 격리 검증 (WBS 2.2 완료)

- `src/ai_trader/knowledge/index.py` 구현:
  - 원칙 카탈로그(`docs/knowledge/catalog.json`) 스냅샷 ID: `ba4191bfe186cac20fb6b15aff9b85f95eefb3a2f052edf84abc0c085324a5f8` (문서 3개, 청크 9개, `--replay-snapshot` 결과 `integrity=passed`, `replay=identical`).
  - 공개 카탈로그(`docs/knowledge/public-catalog.json`) 스냅샷 ID: `9519c2c50c12e49aaa7e1df17386edc382ee13325d7e693101fe8601aa01b9b8` (문서 4개, 청크 245개, `--replay-snapshot` 결과 `integrity=passed`, `replay=identical`).
  - HTML/XML `<script>`·`<style>` 제거, 고정 크기(600자, 100자 중첩) 분할, 각 청크 SHA-256 및 `untrusted_data_only=True` 강제, 프롬프트 삽입 의심 문구(`instruction_like=True`) 플래그 분리, 질의 시점(`decision_time`)·사용 목적(`purpose`)·정정 체인(`supersedes`) 필터링 검색 확인.

## 고정 평가 세트 기반 검색·인용 품질 게이트 (WBS 2.3 완료)

- `docs/knowledge/eval-benchmark.json` (오프라인 원칙 평가 세트 8건: 양성 7건, 시점 경계 차단 1건):
  - `hit_rate=1.0`, `citation_accuracy=1.0`, `numeric_accuracy=1.0`, `temporal_guard_accuracy=1.0`, `status=passed` (종료 0).
- `docs/knowledge/public-eval-benchmark.json` (실제 SEC 공시 3편 + PLOS 논문 1편 평가 세트 6건: 양성 5건, 접수 직후·관측 이전 시점 차단 1건):
  - Apple 10-Q 순매출(`78,678`, `30,739`, `109,417`), Microsoft 10-K 매출(`64,696`, `267,143`), Microsoft 8-K 세그먼트 개편(`FY27 Segments and Investor Metrics`, `Agents and Infra`, `Devices and Consumer`), PLOS 논문 시장 규모(`12 trillion US dollars`, `20 trillion US dollars`) 및 시점 가드 모두 `hit_rate=1.0`, `citation_accuracy=1.0`, `numeric_accuracy=1.0`, `temporal_guard_accuracy=1.0`, `status=passed` (종료 0).
- 잘못된 인용 위치·누락된 수치·시점 누수 발생 시 `status=blocked` 및 CLI 종료 코드 2로 차단됨을 단위 테스트로 검증했습니다.

## 자동 검증

- `tests/test_knowledge.py`: **46개 통과** (전체 테스트 **127개 통과**).
- 최종 `bash scripts/check.sh`: doctor, 불변 기준선·WBS·의존성·근거 검사, Ruff·포맷 및 전체 127개 테스트 통과.

## 한계 및 다음 작업 (WBS 3.1)

- 단계 1(데이터·지식) 게이트를 모두 통과했습니다. 다음 작업은 단계 2(AI 토론)의 첫 작업인 **WBS 3.1 모델·호출 예산·공급자 어댑터**입니다. `historical_backtest_approved=false`, `trading_approved=false`를 유지합니다.



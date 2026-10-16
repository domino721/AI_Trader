# 지식 자료 계약 및 스냅샷·색인 — WBS 2.1–2.2

2026-10-16, 한국 시간. 현재 계획 v1.1.0의 출처 계약(WBS 2.1)과 파싱·청크·RAG 색인·시점 필터(WBS 2.2) 구현이며 범위·순서·일정 기준선은 변경하지 않습니다. WBS 2.1 및 2.2는 **완료**했으며, 다음 순서는 고정 평가 세트를 통한 검색·인용 품질 게이트(WBS 2.3)입니다.

## 현재 확보·검증한 자료

| 목록 | 내용 | 실제 검증 | 용도와 한계 |
| --- | --- | --- | --- |
| `docs/knowledge/catalog.json` | 프로젝트가 새로 작성한 가치·모멘텀·퀀트 원칙 3개 (총 9개 절 위치) | 원문 SHA-256, 절 제목 marker, 판본, 권한과 최초 관측 시각, 스냅샷 9청크 동일 재생 | 원칙·반증·실험 기준. 저서 발췌나 실증 전략이 아님 |
| `docs/knowledge/public-catalog.json` (논문) | Wang·Wang·Zhang (2024), PLoS ONE 19(3): e0300781 | 출판사 XML HTTP 200, 318,832바이트, 본문 `sec001`–`sec003`, CC BY 4.0 고지 | 중국 주식·채권 교차 자산 방법론 비교. 미국 주식 성과 근거로 사용하지 않음 |
| `docs/knowledge/public-catalog.json` (SEC 공시 본문) | AAPL 10-Q (`0000320193-26-000020`), MSFT 10-K (`0001193125-26-323660`), MSFT 8-K (`0001193125-26-380280`) | SEC EDGAR primary HTML HTTP 200 (1,018,319 / 8,585,610 / 28,668바이트), SHA-256, Item별 고유 marker 9개, 스냅샷 105청크 동일 재생 | 기업 공시 본문 표본. 접수 시각(`accepted_at`)을 과거 피드 도착 시각으로 소급하지 않으며, 제3자 첨부물(Exhibit 99.1 등)은 제외 |

외부 논문 XML과 SEC 공시 HTML 원문은 `.local/knowledge/raw/`에만 보관하고 Git에는 메타데이터·해시·인용 위치만 넣습니다. 이 파일이 없는 새 checkout에서 공개 목록 검증이 실패하는 것은 정상입니다. 새 다운로드가 달라지면 기존 해시를 덮어쓰지 않고 새 판본으로 기록합니다. 직접 작성한 3개 원칙 문서와 검증·스냅샷·검색 테스트는 네트워크 없이 재현됩니다.

로컬 `.env`(Git 제외, 권한 `0600`)에 사용자 연락 식별 설정을 연결하여 SEC fair-access 정책(초당 1회 이하 직렬 요청)에 따라 primary document를 수집·검증했습니다. 연락 정보는 문서나 출력에 기록하지 않습니다.

## 계약과 판정 (WBS 2.1)

`src/ai_trader/knowledge/models.py`의 계약은 다음 정보를 고정합니다.

- 안정적인 `document_id`, 자료 종류, 원출처와 실제 다운로드 URL, 제목·저자·판본, 발행일.
- 시간대가 있는 최초 관측·수신 시각, 원본 파일 경로·SHA-256, 명시적으로 허용한 사용 목적과 권한 확인 근거·시각·저작자 표시·조건.
- 실제 파일에서 유일하게 찾을 수 있는 인용 위치 marker·이름. 페이지가 없는 HTML/XML에 가짜 페이지 번호를 부여하지 않음.
- SEC 자료는 CIK·accession·form·accepted_at·회계 대상일, 같은 SEC accession 디렉터리에 속하는 원문/수신 URL.
- 정정은 이전 `version_id`를 `supersedes`로 연결. 버전 ID는 원문 해시뿐 아니라 권한·시각·위치·판본 등 메타데이터까지 결합. 중복·분기·빠진 이전 판본·역행하는 정정 시각은 거부.

허용 목적은 `local_storage`, `indexing`, `model_context`로 구분합니다. 저장 허용만으로 검색 색인·모델 전달·원문 재배포·모델 훈련을 허용했다고 간주하지 않습니다. 권한 미확인/거부, 허용하지 않은 목적, 체크섬 오류, 누락/중복 인용 위치, 의사결정 이후 자료를 판정에서 제외합니다. URL에 사용자명·비밀번호를 넣을 수 없습니다. 경로 이탈·루트 밖으로 향하는 심볼릭 링크도 거부합니다.

## 파싱·청크·지식 스냅샷·시점 필터·지시 격리 (WBS 2.2)

`src/ai_trader/knowledge/index.py`는 검증된 문서를 결정론적으로 파싱·청크화하고 스냅샷 재생 및 시점/권한 필터 검색을 수행합니다.

- **파싱 및 청크 고정 (`plain-v1` / `fixed-char-v1`)**: `indexing` 권한이 승인된 문서만 파싱합니다. 각 문서의 검증된 `CitationLocation` marker 구간에서 `<script>`·`<style>`·주석·태그를 제거하고 고정 크기(600자, 100자 중첩)로 분할합니다. 각 `Chunk`는 `version_id`, `location_id`, `chunk_index`, 문자 오프셋, 파서/청커 버전, 텍스트 SHA-256을 결합한 결정론적 `chunk_id`를 갖습니다.
- **불변 지식 스냅샷과 동일 재생**: 카탈로그와 전체 청크 해시를 결합해 `snapshot_id`를 부여하고 `.local/knowledge/snapshots/{snapshot_id}.json`에 보존합니다. `--replay-snapshot`은 네트워크 없이 로컬 원문에서 스냅샷을 재구성해 전체 문서·청크 일치(`integrity=passed`, `replay=identical`)를 검증합니다.
- **시점·권한·정정 필터 검색**: `search_knowledge`는 질의 시점에 `available_at <= decision_time`, 요청된 `purpose`(기본 `model_context`) 허용 여부, 그리고 `decision_time` 이전에 도착한 정정본(`supersedes`) 존재 여부를 먼저 필터링합니다. 부적격 문서는 사유와 함께 `excluded_documents`에 기록되고 검색 후보에서 제외됩니다.
- **문서 지시 격리 (`untrusted_data_only=True`)**: 모든 청크와 검색 결과는 데이터로만 취급되며 어떤 툴 실행·주문·프롬프트 변경 권한도 갖지 않습니다. 본문 내 프롬프트 삽입 의심 패턴(`ignore ... instructions`, `submit a trade`, `system prompt` 등)은 실행하지 않고 `instruction_like=True`로 표시해 후속 검토 게이트에서 식별할 수 있게 합니다.

## 시점 규칙

기본 `available_at`은 최초 관측 시각입니다. 발행일만 알려진 논문을 그날 자정으로 소급하지 않으며, EDGAR 접수 시각을 실제 배포 시각으로 취급하지 않습니다. 정확한 공개 시각과 증거 URL이 함께 있을 때만 `public_available_at`을 지정할 수 있습니다. 회계 대상일은 이용 가능 시점이 아닙니다.

현재 XML·SEC 공시 본문·원칙 문서는 모두 2026-10-16에 최초 관측했습니다. 논문의 2024년 발행일이나 공시의 2026년 7–9월 접수 시각은 현재 파일의 당시 가용성을 입증하지 않으므로 그 이전 의사결정에는 부적격입니다. 나중 정정이 도착해도 그 이전 시점의 원문 판본은 보존하며 미래 정정으로 과거 근거를 덮어쓰지 않습니다. 이는 지식 계약·색인 검사이며 PIT 데이터·LLM 역사 지식 오염·백테스트·거래 승인은 별도입니다.

## 검증·스냅샷·검색 실행

저장소 루트에서 시간대를 포함한 **실제 평가 기준 시각**을 지정합니다.

```bash
uv run --frozen ai-trader knowledge --catalog docs/knowledge/catalog.json \
  --as-of 2026-10-16T23:59:59+09:00
uv run --frozen ai-trader knowledge --catalog docs/knowledge/public-catalog.json \
  --as-of 2026-10-16T23:59:59+09:00
uv run --frozen ai-trader knowledge --catalog docs/knowledge/catalog.json --build-snapshot
uv run --frozen ai-trader knowledge --replay-snapshot <snapshot_id>
uv run --frozen ai-trader knowledge --snapshot-id <snapshot_id> \
  --query "cash flow valuation leverage" --as-of 2026-10-16T23:59:59+09:00 --purpose model_context
```

## 외부 근거 — 확인일 2026-10-16

- [출판사 원문·저자·발행일·CC BY 고지](https://journals.plos.org/plosone/article?id=10.1371/journal.pone.0300781), [CC BY 4.0 조건](https://creativecommons.org/licenses/by/4.0/). 저자·제목·출처·라이선스 및 추후 가공 사실을 보존합니다. 이 기록은 논문의 연구 결과를 검증했다는 뜻이 아닙니다.
- [SEC 재사용 FAQ](https://www.sec.gov/files/about/webmaster-faq.htm)와 [배포 정책](https://www.sec.gov/about/privacy-information#dissemination): 공시 텍스트와 예외 자료를 구분하는 출처 검토 근거로만 사용합니다. 접근 가능하다는 이유만으로 임의 첨부물·그림·개인정보까지 일괄 승인하지 않습니다.
- [SEC 개발자 안내](https://www.sec.gov/about/developer-resources), [접수와 웹 공개 사이 지연 안내](https://www.sec.gov/files/about/webmaster-faq.htm): 접수 시각만으로 실제 전달 시각을 인증하지 않습니다. 자동 수집에는 기존 프로젝트의 식별 정보·속도 제한을 유지합니다.

## 다음 단계 (WBS 2.3)

고정된 검색·인용 평가 세트를 구성하여 검색 적중률, 인용 위치 일치, 수치 보존, 시점 경계 위반 차단, 프롬프트 삽입 격리를 정량 점검하는 **WBS 2.3 검색·인용 품질 게이트**를 수행합니다.


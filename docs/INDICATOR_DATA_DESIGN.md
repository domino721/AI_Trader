# 지표·데이터·Agent 근거 설계 — 계획 v1.3.0

2026-10-18 / CR-0003. **설계·우선순위이며 아래 신규 기능은 미구현이다.** 미국 주식/ETF·일봉·일간/주간 리밸런싱 목표를 유지한다. 투자 성과·실거래 승인·유료 데이터 구매/모델 호출을 뜻하지 않는다. 실행 순서와 상태는 WBS 원본을 따른다.

## 현재 사실과 첫 목표

현재 market 모듈은 Yahoo OHLCV/조정종가·배당/분할, SEC 공시 목록/시각/문서 링크를 연구용 표본으로 수집·검수·저장·재생한다. 재무제표 수치/XBRL·PER/ROE/FCF·장기 feature 이력은 없다. 지식 카탈로그의 공시 본문 표본은 정규화된 재무 데이터셋이 아니다. 기존 데이터 실적은 과거 환경의 기록이며 현재 체크아웃의 원자료 보유·최신성 증거가 아니다. 첫 작업은 실물 목록과 고정 스냅샷 복원/재생이다.

현재 ops DAG는 원칙 문서 검증→색인→고정 검색 평가→모의 모델이다. 시장 데이터 정기 적재를 수행하지 않는다. 이 문서의 DAG·저장 경로·Agent 패킷은 앞으로 구현할 설계이다.

첫 목표는 많은 지표의 일괄 완성이 아니라 (1) 시점/가격 정의 (2) 충분한 원천 (3) 작은 핵심 지표 (4) 실패 시 보류되는 재현 가능한 근거 묶음이다. 가격으로 계산한 RSI·MACD·MA를 독립된 세 증거/투표로 취급하지 않는다. ETF에는 기업 재무 비율을 억지로 적용하지 않는다.

## 원천과 지표 우선순위 — 첨부 목록 전체 항목의 매핑

| 등급 / WBS | 항목 | 요구·판정 |
| --- | --- | --- |
| 선행 / 1.9–1.10 | price_basis, history_days, is_warmup_252 | 가격·배당·분할·거래일·유효 관측 수·산식 버전부터 정의. 단순 252행 확보를 모든 지표의 준비 완료로 간주하지 않음 |
| 원천 / 1.11 | Open/Close/High/Low/Volume, Shares, Dollar Volume | 장기 가격·기업행위·벤치마크. Shares의 종류는 1.12 재무 원천과 연계. Price×Volume은 거래대금 근사이며 실제 체결 합계가 아님 |
| 핵심 / 1.13 | return_1d/5d/21d/63d/126d/252d, log_return_1d, momentum_12_1 | 단순/로그/총수익·직전 1개월 제외·끝점과 warm-up을 계약으로 고정 |
| 핵심 / 1.13 | Volatility 60, downside_volatility_60, drawdown_from_60d_high, distance_from_52w_high, dollar_volume_20 | 가격 기준·ddof·연율화·최소 관측 수·0 거래량 처리를 명시 |
| 핵심 / 1.13 | beta_60, beta_252, corr_60, residual_vol_60 | 종목과 SPY의 같은 시점·같은 수익률 기준·정렬/결측/회귀 정의. 충분한 기존 가격이 있으면 별도 API가 필수인 것은 아님 |
| 핵심 원천 / 1.12 | Shares, EPS, CFO, CAPEX, 매출·영업이익·순이익·자산·자본·현금·부채·이자비용 | 공시 판본/시각·단위·기간·희석/가중평균 주식수·분기/누적 구분. 발표한 값과 단순 재계산 EPS를 구분 |
| 핵심 / 1.14 | PER/PBR/PSR, earnings_yield/book_yield/sales_yield/fcf_yield, log_market_cap | 일별 가격과 그때 공개된 재무·주식수를 결합. 적자·음수 자본·0 분모는 지표별 invalid/not_applicable 사유 보존 |
| 핵심 / 1.14 | ROE/roe, ROIC/roic, Operating Margin, CFO/FCF, sales_growth/eps_growth/asset_growth/capex_growth | 중복 별칭 통합. 평균/기말 자본·TTM·전년 동기·세율/NOPAT·CAPEX 부호 정의를 사전 고정 |
| 핵심 / 1.14 | Debt Ratio, Current Ratio/liquidity, interest_coverage, net_debt_to_ebitda, dividend_yield | Debt Ratio의 부채 범위/분모와 liquidity 산식 명시. 업종별 적용성·현금/리스·비경상 EBITDA·배당 기간 구분 |
| 핵심 이벤트 / 1.15 | 실적 발표·가이던스·중요 공시·정정 | 사실·원문 인용·공개/수신 시각·중복/정정·영향/재검토 조건. 일반 뉴스 감성 없이도 필요 |
| 최소 맥락 / 1.16 | sector_relative_return, 2y_yield, 10y_yield/10Y Rate, yield_curve, VIX/vix, hy_spread | SPY 비교부터. 추가 섹터/거시 데이터는 출처·이용권·판본·갱신 합의 후 최소 세트 선택; 제외 시 미사용 사유를 기록하며 숫자를 만들어 채우지 않음 |
| 선택 비교 / 4.3 | RSI14, MACD, Bollinger, MA Cross, Multi SMA, Disparity, Stochastic, CCI, Volume Ratio 30 | 전부 초기 필수는 아님. 대표 추세 지표를 가설로 선택하고 핵심 대비 중복/기여·비용을 비교 |
| 선택 비교 / 4.3 | gap_return_1d, intraday_return_1d, atr_14/natr_14, return_skew_60, amihud_illiquidity_20 | 가격 조정의 일관성·0 거래대금·관측 수/이상치 정책을 먼저 정의하고 필요 역할에만 제공 |
| 범위 확보 후 / 4.1·4.3 | sector_rank, breadth_200sma, cs_momentum_12_1_rank, cs_volatility_60_rank, cs_dollar_volume_20_rank | 당시 전체 종목군/섹터 편입·상장폐지·상장 기간이 필요. 7개 고정 표본의 순위를 시장 전체 순위로 표시하지 않음 |
| 선택 비교 / 4.3 | gross_profitability, accrual_quality, Altman Z, net_buyback_yield | 자산/평균 자산·현금흐름 정의, Z 모델/업종 적용성, 매입·발행/희석을 구분. 부실 확률로 단정하지 않음 |
| 추가 공급자 검토 후 / 4.3 | Forward PER, earnings_surprise, short_interest, Put-Call Ratio/put_call_ratio | 당시 컨센서스·예상치 수정/발표 시각·공매도 보고/공개 지연·옵션 모집단과 거래량/미결제 구분. 현재값으로 과거를 채우지 않음 |
| 선택 비교 / 4.3 | GDELT/News/gdelt, GPR/gpr, GSCPI, Fear & Greed | 뉴스 이용권·중복·언어/분류 편향·발표/수정·원문 인용 검증. 종합 심리지수와 그 구성요소를 독립 신호로 중복 집계하지 않음 |
| 선택 비교 / 4.3 | real_yield, dxy, WTI/wti, sector_interaction | 원천별 단위·시차·수정·섹터 효과 가설과 추가 기여 검증. 상호작용항을 결과를 보고 무제한 추가하지 않음 |
| 현재 제외 | S&P 1분봉, ±30% Limit | 일봉 전략의 필수 아님. 미국 주식에 고정 ±30% 규칙을 적용하지 않음. 거래정지/LULD는 향후 실행·위험 게이트 5.2–5.3에서 검토; 분봉/국내 시장은 별도 범위 변경 |

선택 비교 항목은 미구현 backlog이며 모두 4.3 완료의 강제 구현 체크리스트가 아니다. 후보·선택/제외 이유·실험 비용/횟수와 결과를 남긴다. 새 공급자/유료 구매/개인 인증이 필요하면 허용 범위와 계약을 확인하고 미확정을 차단으로 표시한다. 처음부터 입력을 늘리는 대신 핵심→섹터/거시→뉴스·선택 지표의 추가 기여를 비교한다.

## 지표 계약 — 수집 전에 확정할 것 (1.10)

지표 사전에 feature_id·별칭·역할·원천 필드·산식/버전·단위·회계/거래 기간·갱신 정책·lookback/최소 유효 관측 수·가격 기준·결측/부적격 사유·수치 테스트 예제를 둔다. 기간별 수익률은 끝점 가격이 추가로 필요할 수 있고, EMA와 회귀는 별도 준비 조건이 있으므로 is_warmup_252 하나로 모두 승인하지 않는다. 12–1의 월/거래일 근사 여부도 버전으로 구분한다.

주식수는 발행/유통/free float/기본·희석 가중평균을 구분한다. 주식수의 공시 주기와 분할 이벤트를 일별로 정렬하며, 가격의 분할 기준과 일치시킨다. EPS·평균 자본·TTM·누적 현금흐름의 분기 분해·적자/음수 자본·업종별 적용성을 명시한다. 은행/보험/REIT/ETF에 같은 ROIC·EBITDA·Altman 산식을 무조건 적용하지 않는다.

원주가/분할 조정/배당 재투자 총수익 기준을 구분한다. 수익률용 시계열과 실제 주문 체결용 가격을 분리하고 Yahoo OHLC를 거래 당시 원주가로 자동 인증하지 않는다. 계산은 결정적인 코드가 하고 Agent가 숫자/과거 데이터를 기억으로 생성·보충하지 않는다.

## 원천·시점 계약과 저장 설계 (1.11–1.17)

안정적인 instrument_id·issuer_id·share_class와 당시 ticker/sector/universe membership을 분리한다. 각 원천 행에는 회계 대상 기간/거래 세션, 원문 accession/위치·단위·원문 해시, 공개 시각, 최초 관측/수신 시각, 정정/판본을 연결한다. 공시일만으로 장 시작 시각 가용성을 추정하지 않는다. 일자만 있으면 보수적 가용 규칙과 근거를 기록한다. observed_at을 과거로 소급하지 않는다.

과거 피처는 decision_time 이전에 실제 이용 가능했던 판본만 as-of join한다. 관측 시각 이후 확보한 재무·현재 컨센서스·최신 수정 거시값을 과거에 끼워 넣지 않는다. 공시의 기간 종료일과 실제 공개 시각을 구분하고 원문에서 판본을 재구성할 수 없는 구간은 PIT 미검증으로 남긴다. 현재 SEC companyfacts/frames 응답을 받았다는 이유만으로 역사적 PIT를 통과시키지 않는다.

기존 `<state>/market/{raw,receipts.db,snapshots,quarantine,normalized}` 구조는 유지한다. 현재 기본 state는 `.local/dev`, prod는 별도 절대 경로다. 새 자료의 아래 경로는 **제안이며 아직 생성되지 않는다**:

| 제안 경로 | 내용 |
| --- | --- |
| `<state>/fundamentals/raw/<hash>` | 허용된 XBRL/공시 원본과 수신 영수증 |
| `<state>/fundamentals/snapshots/<id>.json` 및 `normalized/<id>/*.parquet` | 판본/단위/기간이 고정된 재무 원천·정규화·품질 |
| `<state>/features/snapshots/<id>.json` 및 `normalized/<id>/*.parquet` | decision_time·종목군·가격/재무/이벤트 snapshot ID·산식 버전·피처별 값/단위/상태·원천 lineage |
| `<state>/features/quarantine/<id>.json` | 결측/오염/신선도/정의 불일치 등 거부 사유 |

단순 DB upsert로 과거 판본을 덮어쓰지 않는다. Snapshot ID는 canonical 데이터·정의·원천 참조의 해시로 계산하고 파일/Parquet 해시와 오프라인 동일 재생을 검증한다. 원문·실데이터·DB·비밀은 Git 제외한다. 제안 schema/경로가 기존 Archive와 충돌하면 구현 전 호환/마이그레이션 결정을 남기며 기존 스냅샷을 조용히 재해석하지 않는다.

## 품질·Agent 입력 수용 (1.17–1.19)

- 시계열: 거래소 캘린더·연속/중복·휴장/거래정지·누락·0 거래량·가격 기준·기업행위·변경 ticker·SPY 정렬·lookback/warm-up을 검증한다.
- 재무: 단위/통화·주식 종류·분기/누적·연결/개별·정정·필드 누락·0/음수 분모·섹터 적용성·미래 판본·가용 시각을 검증한다. 모르는 값을 0으로 채워 통과시키지 않는다.
- 피처: 손계산 가능한 합성 예제·독립 산식 비교·극단/결측·스케일 변화·재시작/정정 재생·오염된 미래 판본을 넣은 거부 테스트를 둔다. 같은 날짜/종목군에서만 순위를 비교한다.
- 실제 소스 수용: 작은 허용 표본을 별도 검증해 원천 필드·시각·단위·권한과 재현을 확인한다. 합성 통과를 실제 공급자/PIT·거래 승인의 증거로 대체하지 않는다. 1.19는 core 연구 입력 수용이며 전체 역사적 검증은 4.1에 남는다.
- Agent 패킷: decision_time·역할·시장/지식/재무/feature snapshot ID·값/단위/상태·근거/공개 시각·반증 정보·현재 포지션/위험 예산의 별도 참조·결측/한계·해시를 포함한다. 미연결 계좌값은 가상 값으로 명시하고 실제값처럼 제공하지 않는다.
- 가치/모멘텀/퀀트는 같은 시점의 허용 근거를 역할별로 검토하고 주장·인용·가정·반론·보류 이유를 제출한다. 정성 공시와 숫자를 함께 제공하며 여러 파생 기술지표의 일치를 독립 증거 수로 세지 않는다. 실제 모델 호출은 3.1/3.2 게이트에서 별도 검증한다.
- 필수 입력 실패는 해당 분석/신규 위험 증가를 보류한다. 선택 맥락의 미사용은 명시하고 필수 입력으로 슬쩍 바꾸지 않는다. 모델 출력이나 원문 명령이 위험 한도를 변경하거나 주문을 발행할 수 없다.

## 시장 데이터 운영 DAG 설계 (1.18)

`collect_price_actions + collect_financials_events → validate_sources → build_features → validate_feature_snapshot → publish_research_packet`을 영속 단계로 연결한다. +는 독립 수집 가지이며 완료 조건은 실제 입력별로 추적한다. 기존 원칙 점검 DAG를 시장 수집 성공으로 이름만 바꾸지 않는다.

완료 세션·공시 가용 시각에 맞는 명시적 refresh 정책, 원천별 재시도/한도·누락 보충·신선도 한도·정정 판본을 둔다. 한도 수치는 운용 주기/공급자 조건에 맞춰 사전 결정하며 현재 확정값처럼 하드코딩하지 않는다. 누락을 이전 캐시로 숨기지 않는다. 중복 수집/재시작은 원본·단계 상태를 보존하고 불확실한 작업을 자동 재발행하지 않는다. 최신 성공/실패·종목/기간 커버리지·마지막 원천 수신 시각·누락·격리 건수와 영향 범위를 현황판에 표시한다. PC 자체 장애 외부 감시는 0.6, 실제 주문/계좌 신선도는 5.3에서 수용한다.

## 검증된 사실과 계획을 구분하는 근거

- 기존 실제 표본: `management/DATA_VALIDATION_2026-10-15.md`; 최신 앱 CI 183개 통과는 데이터 실물 보유/정기 적재의 증거가 아니다.
- [SEC 데이터 API](https://www.sec.gov/search-filings/edgar-application-programming-interfaces): submissions와 XBRL facts, 단위·기간·필드 범위가 구분됨.
- [FRED/ALFRED 판본 시점](https://fred.stlouisfed.org/docs/api/fred/realtime_period.html): 최신 수정값과 당시 알려진 값을 구분.
- [French 모멘텀 정의](https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/Data_Library/det_mom_factor.html): 직전 월을 제외한 기간 정의의 참고이지 이 전략의 수익성 보증이 아님.
- [미국 LULD](https://www.luldplan.com/): 미국 시장에 고정 ±30%를 적용하지 않는 검토 근거.

외부 원천의 최신 필드/이용권/제한과 정확한 산식은 실제 구현 시 다시 확인한다. 현재 문서의 우선순위는 승인된 기술 작업 순서이며 투자 종목·수익 목표·금액/손실 한도·유료 계약의 확정이 아니다.

## PM의 포트폴리오 입력 연결 — CR-0004

[포트폴리오·최종 결정 백테스트 설계](PORTFOLIO_BACKTEST.md)의 PM은 위 패킷과 현재 가상 계좌를 사용합니다. 종목-SPY 상관 `corr_60`만으로 전체 자산 공분산·ETF 중복·섹터/팩터 분산을 계산했다고 보지 않습니다. PM에 필요한 공동 관측 수익률·추정 구간·공분산/노출 판본과 이용 가능 시점·누락 상태를 별도 계산 참조로 연결하고 3.3에서 검증합니다. 현재 지표 개발 완료를 주장하지 않으며 1.19의 입력 수용·4.1의 역사적 시점 검증은 유지합니다.

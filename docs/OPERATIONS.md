# 단일 Windows 호스트 연구 운영 지침 — 계획 1.2.0

2026-10-18. 공통 운영 기반 0.3–0.5의 **코드/로컬 검증**과 실제 대상 PC의 **외부 수용 0.6**을 분리합니다. 실제 AI 분석·브로커·주문·실거래 준비는 별도 게이트이며 현재 미구현/미검증입니다.

## 환경 경계

`AI_TRADER_ENVIRONMENT=dev|test|prod`를 사용합니다. 새 기본 상태 경로는 `.local/dev`이며 기존 `.local` 자료를 자동으로 이동하지 않습니다. 기존 자료 조회 시 해당 경로를 명시적으로 지정하고 먼저 환경 소유권을 검토합니다.

prod는 절대 상태 경로와 최소 32자 API 토큰을 요구합니다. 상태 경로의 `.environment.db`는 해당 경로를 처음 사용한 환경을 저장하며 다른 환경에서 열면 거부합니다. dev/prod의 비밀·상태·백업 경로를 별도로 둡니다. `simulation`은 거래 실행 모드이며 환경 이름과 독립적입니다. 현재 live 설정은 허용되지 않습니다.

운영 데이터/API는 Bearer 토큰으로 보호하고 prod의 자동 API 문서는 비활성화합니다. `/health`는 기본 프로세스 응답, 인증된 `/ready`는 DB 쓰기/무결성·실행기 생존 확인입니다. `/ops/readiness`는 실행기 준비와 실거래 미충족 조건을 구분합니다. 외부 브로커·시세 준비 상태를 확인했다고 표시하지 않습니다. 운영 토큰 파일은 상태 디렉터리 바깥에 두며 Windows 시작 스크립트가 상태 안의 토큰 경로를 거부합니다. 토큰은 응답/화면 저장소/URL/로그에 넣지 않으며 화면에서는 열린 페이지의 메모리에서만 사용합니다.

Python의 chmod만으로 Windows ACL을 보장하지 않습니다. 아래 Windows 시작/토큰 스크립트로 NTFS 접근 권한을 제한하고 실제 대상 PC에서 접근 실패 테스트를 해야 합니다. 외부 노출은 구현하지 않았으며 기본 바인딩은 127.0.0.1입니다. 원격 접근이 필요하면 별도로 인증된 접근 경계와 암호화된 전송을 검증합니다.

## Windows 준비와 실행

Python 3.12와 uv가 설치된 데스크탑에서 저장소 루트 기준으로 실행합니다. 경로는 예시이며 투자금·계좌·실제 API 키를 입력하지 않습니다.

```powershell
uv sync --locked --dev --python 3.12
$state = Join-Path $env:LOCALAPPDATA 'AITrader\prod'
$token = Join-Path $env:LOCALAPPDATA 'AITrader\secrets\ops-token'
.\scripts\windows\New-OpsToken.ps1 -TokenFile $token
.\scripts\windows\Start-Research.ps1 -Environment prod -StateDir $state -TokenFile $token
```

이것은 **직접 실행 절차**이며 이번 개발 환경에서 대상 Windows PC에 실행한 것이 아닙니다. PowerShell 정책을 우회하거나 계정 암호를 스크립트에 저장하지 않습니다. 조직/PC 정책이 서명된 스크립트만 허용하면 해당 정책에 맞춰 검토·서명해야 합니다.

브라우저에서 `http://127.0.0.1:8000/ops`를 열고 보호된 로컬 토큰 파일의 값을 입력합니다. 상태/계좌 API 키와는 다른 운영 화면용 토큰입니다. ‘점검 시작’은 원칙 문서 검증→검색 색인→고정 평가→**합성 근거의 모의 모델**만 실행합니다. 외부 모델 호출·실제 RAG 분석·매매 신호·주문을 생성하지 않습니다.

## 로그온 자동 시작·재시작

```powershell
.\scripts\windows\Install-ResearchTask.ps1 -StateDir $state -TokenFile $token
Start-ScheduledTask -TaskName 'AITrader-Research-Prod'
```

현재 사용자의 로그온 작업으로 등록하며 관리자 권한·계정 암호 저장을 요구하지 않습니다. 실패 시 최대 3회, 1분 간격 재시작을 설정하고 중복 작업을 막습니다. **로그온 전 무인 기동을 보장하지 않습니다.** 로그온 없이 부팅만으로 운영할 필요가 있으면 Windows 서비스/작업 계정과 접근권한을 별도로 설계·수용해야 합니다. 절전/전원 정책도 이 스크립트가 임의로 바꾸지 않습니다.

앱 내부 주기 실행은 기본 0(비활성)입니다. 시작 스크립트의 `-ScheduleSeconds 86400`처럼 60–86400초 주기를 명시하면 해당 UTC 시간 구간마다 하나의 연구 점검을 큐에 넣습니다. 재시작 시 같은 구간은 재생성하지 않고, 놓친 구간은 과거 주문처럼 소급 실행하지 않으며 로컬 경보를 기록합니다. 이 기능은 미국 거래소 마감 기반 매매 스케줄러가 아닙니다. 거래 일정/신선도는 WBS 5.3에서 별도 검증합니다.

## 상태와 장애 처리

운영 화면/API는 실행 ID별 queued/running/succeeded/failed/interrupted와 단계별 pending/running/succeeded/failed/blocked를 표시합니다. 같은 ID의 요청은 저장된 실행을 조회하고, 다른 평가 시각으로 같은 ID를 재사용하면 거부합니다. 새 실험/재실행은 새 ID를 사용합니다. 과거 성공 단계만 건너뛰는 부분 재시작은 아직 제공하지 않습니다.

OS 잠금으로 실행기/백업의 호스트 동시 사용을 막고, SQLite 원자적 claim으로 중복 실행을 막습니다. 실행 소유권·heartbeat를 기록합니다. 프로세스가 죽거나 절전 뒤 heartbeat가 만료되면 진행 중 실행은 interrupted, 후속 단계는 blocked가 되며 자동으로 재발행하지 않습니다. 이전 실행기의 늦은 결과는 상태 전이를 갱신할 수 없습니다. 이 보호는 현재 연구 작업의 상태 제어이며 미래 브로커의 외부 주문 중복 방지를 구현한 것은 아닙니다.

오류 코드는 input_missing/validation_failed/io_failed/step_failed 등으로 저장하고 원문·예외 문자열은 노출하지 않습니다. 모니터링 화면은 로컬 경보를 조회하며 외부 이메일/메신저 알림은 미연결입니다. PC 자체가 꺼졌을 때 그 PC만으로 경보를 보낼 수 없으므로 외부 heartbeat 감시/알림은 실제 운영 수용에 필수 잔여 항목입니다.

## 백업·복원

현재 백업은 **실행기와 그 밖의 CLI 쓰기 작업을 모두 중지한 상태**에서 수행합니다. 실행기가 활성 상태이면 OS 잠금으로 거부합니다. SQLite backup API와 파일 체크섬 목록을 사용하며 원문·DB를 보존하고 비밀 설정 파일·일시 journal/lock은 제외합니다. 백업은 암호화/외부 저장/자동 순환을 구현하지 않았으므로 보관 위치·접근 통제·보존/폐기는 별도로 운영해야 합니다.

```powershell
Stop-ScheduledTask -TaskName 'AITrader-Research-Prod'
$env:AI_TRADER_ENVIRONMENT = 'prod'
$env:AI_TRADER_STATE_DIR = $state
# API 토큰은 기존 보호된 로컬 런타임에서 제공. 채팅/저장소에 넣지 않습니다.
uv run --frozen ai-trader ops recover
uv run --frozen ai-trader ops backup --target 'D:\AITraderBackups\new-backup-directory'
```

`recover`는 heartbeat가 만료된 실행만 중단으로 확정합니다. 방금 강제 종료했다면 기본 lease 30초가 지나야 합니다. 복원은 원래 상태를 덮어쓰지 않고 **존재하지 않는 새 상태 경로**에만 허용합니다. 환경·파일 경로·체크섬·SQLite 무결성이 맞지 않으면 거부합니다. 백업/복원용 CLI도 prod 설정 검증이 적용됩니다. 토큰 파일은 백업에 포함하지 않으며 별도 보관·복구 절차가 필요합니다.

```powershell
$env:AI_TRADER_STATE_DIR = 'D:\AITraderRestore\new-prod-state'
uv run --frozen ai-trader ops restore --source 'D:\AITraderBackups\new-backup-directory'
```

새 경로에서 점검한 뒤 시작 스크립트의 상태 경로를 명시적으로 바꿉니다. 기존 디렉터리를 삭제하거나 환경 소유권 DB를 임의 수정하는 방법을 복원 절차로 사용하지 않습니다.

## 대상 PC 수용 체크 — WBS 0.6 미완료

Windows 설치·PowerShell 문법/NTFS ACL, 운영 토큰 없는 조회/실행 거부, 로그온·재부팅·프로세스 종료·절전/복귀·네트워크 단절, 예약 누락 경보, 백업→새 경로 복원, 원자료 복구, 외부 heartbeat 알림을 실제 대상 PC에서 관찰해야 합니다. Windows CI와 현재 개발 호스트의 테스트도 해당 PC 관찰을 대체하지 않습니다.

실행 환경 준비를 통과하더라도 실제 모델·전략/백테스트·브로커 모의매매·계좌 접근권한·투자금/손실 한도·실거래 승인은 별도 게이트입니다.

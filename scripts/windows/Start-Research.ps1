param(
  [ValidateSet('dev','test','prod')][string]$Environment = 'dev',
  [Parameter(Mandatory=$true)][string]$StateDir,
  [string]$TokenFile,
  [ValidateRange(0,86400)][int]$ScheduleSeconds = 0,
  [ValidateRange(1024,65535)][int]$Port = 8000
)
$ErrorActionPreference = 'Stop'
$repo = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..'))
$python = Join-Path $repo '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $python)) { throw 'Run uv sync --locked --dev --python 3.12 in the repository first.' }
if (-not [IO.Path]::IsPathRooted($StateDir)) { throw 'StateDir must be absolute.' }
if ($Environment -eq 'prod' -and -not $TokenFile) { throw 'Production requires TokenFile.' }
if ($ScheduleSeconds -gt 0 -and $ScheduleSeconds -lt 60) { throw 'Schedule interval must be zero or at least 60 seconds.' }
$statePath = [IO.Path]::GetFullPath($StateDir).TrimEnd('\','/')
if ($TokenFile) {
  $tokenPath = [IO.Path]::GetFullPath($TokenFile)
  if ($tokenPath.Equals($statePath,[StringComparison]::OrdinalIgnoreCase) -or $tokenPath.StartsWith($statePath+'\',[StringComparison]::OrdinalIgnoreCase)) { throw 'TokenFile must be outside StateDir so state backups exclude the credential.' }
}
New-Item -ItemType Directory -Path $StateDir -Force | Out-Null
$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
$stateItems = @((Get-Item -LiteralPath $StateDir)) + @(Get-ChildItem -LiteralPath $StateDir -Force -Recurse)
foreach ($item in $stateItems) {
  if ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) { throw 'State directory must not contain reparse points.' }
}
& icacls.exe $StateDir /inheritance:r /grant:r "*$($identity.User.Value):(OI)(CI)F" '*S-1-5-18:(OI)(CI)F' /T /Q | Out-Null
if ($LASTEXITCODE -ne 0) { throw 'Cannot protect state directory ACL.' }
$allowed = @($identity.User.Value,'S-1-5-18','S-1-5-32-544')
foreach ($item in $stateItems) {
  foreach ($rule in (Get-Acl -LiteralPath $item.FullName).Access) {
    if ($rule.AccessControlType -eq 'Allow') {
      $sid = $rule.IdentityReference.Translate([Security.Principal.SecurityIdentifier]).Value
      if ($allowed -notcontains $sid) { throw 'State directory grants access beyond owner/SYSTEM/administrators.' }
    }
  }
}
$env:AI_TRADER_ENVIRONMENT = $Environment
$env:AI_TRADER_STATE_DIR = $statePath
$env:AI_TRADER_KNOWLEDGE_ROOT = $repo
$env:AI_TRADER_OPS_SCHEDULE_SECONDS = [string]$ScheduleSeconds
$env:AI_TRADER_EXECUTION_MODE = 'simulation'
if ($TokenFile) {
  foreach ($rule in (Get-Acl -LiteralPath $TokenFile).Access) {
    if ($rule.AccessControlType -eq 'Allow') {
      $sid = $rule.IdentityReference.Translate([Security.Principal.SecurityIdentifier]).Value
      if ($allowed -notcontains $sid) { throw 'Token file grants access beyond owner/SYSTEM/administrators.' }
    }
  }
  $env:AI_TRADER_API_TOKEN = [IO.File]::ReadAllText([IO.Path]::GetFullPath($TokenFile)).Trim()
}
Push-Location $repo
try {
  & $python -m uvicorn ai_trader.api:create_app --factory --host 127.0.0.1 --port $Port --workers 1
  $exitCode = $LASTEXITCODE
} finally {
  Pop-Location
  Remove-Item Env:AI_TRADER_API_TOKEN -ErrorAction SilentlyContinue
}
exit $exitCode

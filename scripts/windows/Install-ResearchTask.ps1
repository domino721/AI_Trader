param(
  [Parameter(Mandatory=$true)][string]$StateDir,
  [Parameter(Mandatory=$true)][string]$TokenFile,
  [string]$TaskName = 'AITrader-Research-Prod',
  [ValidateRange(0,86400)][int]$ScheduleSeconds = 0
)
$ErrorActionPreference = 'Stop'
$start = Join-Path $PSScriptRoot 'Start-Research.ps1'
foreach ($value in @($start,$StateDir,$TokenFile)) {
  if ($value.Contains('"') -or $value.Contains("`r") -or $value.Contains("`n")) { throw 'Unsafe path.' }
  if (-not [IO.Path]::IsPathRooted($value)) { throw 'All paths must be absolute.' }
}
if (Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue) { throw 'Task already exists; review it before replacement.' }
$identity = [Security.Principal.WindowsIdentity]::GetCurrent().Name
$arguments = '-NoProfile -File "{0}" -Environment prod -StateDir "{1}" -TokenFile "{2}" -ScheduleSeconds {3}' -f $start,$StateDir,$TokenFile,$ScheduleSeconds
$action = New-ScheduledTaskAction -Execute 'powershell.exe' -Argument $arguments -WorkingDirectory ([IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..')))
$trigger = New-ScheduledTaskTrigger -AtLogOn -User $identity
$principal = New-ScheduledTaskPrincipal -UserId $identity -LogonType Interactive -RunLevel Limited
$settings = New-ScheduledTaskSettingsSet -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1) -ExecutionTimeLimit ([TimeSpan]::Zero) -StartWhenAvailable -MultipleInstances IgnoreNew
Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Principal $principal -Settings $settings | Out-Null
Write-Output 'Registered research task for user logon. It does not run before logon or place live orders.'

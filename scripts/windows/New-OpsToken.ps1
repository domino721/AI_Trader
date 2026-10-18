param([Parameter(Mandatory=$true)][string]$TokenFile)
$ErrorActionPreference = 'Stop'
if (Test-Path -LiteralPath $TokenFile) { throw 'Token file already exists; preserve the existing credential.' }
$parent = Split-Path -Parent ([IO.Path]::GetFullPath($TokenFile))
New-Item -ItemType Directory -Path $parent -Force | Out-Null
if ((Get-Item -LiteralPath $parent).Attributes -band [IO.FileAttributes]::ReparsePoint) { throw 'Secret directory must not be a reparse point.' }
$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
$grant = "*$($identity.User.Value):(F)"
& icacls.exe $parent /inheritance:r /grant:r "*$($identity.User.Value):(OI)(CI)F" '*S-1-5-18:(OI)(CI)F' | Out-Null
if ($LASTEXITCODE -ne 0) { throw 'Cannot protect secret directory ACL.' }
$allowed = @($identity.User.Value,'S-1-5-18','S-1-5-32-544')
foreach ($rule in (Get-Acl -LiteralPath $parent).Access) {
  if ($rule.AccessControlType -eq 'Allow') {
    $sid = $rule.IdentityReference.Translate([Security.Principal.SecurityIdentifier]).Value
    if ($allowed -notcontains $sid) { throw 'Secret directory grants access beyond owner/SYSTEM/administrators.' }
  }
}
$bytes = New-Object byte[] 48
$rng = [Security.Cryptography.RandomNumberGenerator]::Create()
try { $rng.GetBytes($bytes) } finally { $rng.Dispose() }
$encoded = [Text.Encoding]::UTF8.GetBytes([Convert]::ToBase64String($bytes))
$stream = [IO.File]::Open([IO.Path]::GetFullPath($TokenFile), [IO.FileMode]::CreateNew, [IO.FileAccess]::Write, [IO.FileShare]::None)
try { $stream.Write($encoded,0,$encoded.Length) } finally { $stream.Dispose() }
& icacls.exe $TokenFile /inheritance:r /grant:r $grant '*S-1-5-18:(F)' | Out-Null
if ($LASTEXITCODE -ne 0) { Remove-Item -LiteralPath $TokenFile; throw 'Cannot protect token ACL.' }
Write-Output 'Created protected token file. Its value was not printed.'

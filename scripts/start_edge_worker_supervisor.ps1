param(
    [int]$MaxRestarts = 3,
    [int]$RestartDelaySeconds = 30,
    [string]$HealthFile = $env:BROWSER_WORKER_HEALTH_FILE
)

$ErrorActionPreference = 'Stop'
if ($MaxRestarts -lt 0) { throw 'MaxRestarts must not be negative.' }
if ($RestartDelaySeconds -lt 1) { throw 'RestartDelaySeconds must be positive.' }
if (-not $HealthFile) { throw 'BROWSER_WORKER_HEALTH_FILE is required.' }
$repositoryRoot = (Get-Item -LiteralPath (Join-Path $PSScriptRoot '..')).FullName
$healthPath = [IO.Path]::GetFullPath($HealthFile)
if ($healthPath.StartsWith($repositoryRoot, [System.StringComparison]::OrdinalIgnoreCase)) { throw 'BROWSER_WORKER_HEALTH_FILE must be outside the repository root.' }

for ($attempt = 0; $attempt -le $MaxRestarts; $attempt++) {
    $startedAt = (Get-Date).ToUniversalTime().ToString('o')
    Set-Content -LiteralPath $healthPath -Value "{`"status`":`"starting`",`"started_at`":`"$startedAt`",`"restart_attempt`":$attempt}" -Encoding UTF8
    $worker = Start-Process -FilePath powershell.exe -ArgumentList '-NoProfile', '-File', (Join-Path $PSScriptRoot 'run_browser_worker.ps1') -PassThru -Wait -WindowStyle Hidden
    $finishedAt = (Get-Date).ToUniversalTime().ToString('o')
    Set-Content -LiteralPath $healthPath -Value "{`"status`":`"stopped`",`"finished_at`":`"$finishedAt`",`"exit_code`":$($worker.ExitCode),`"restart_attempt`":$attempt}" -Encoding UTF8
    if ($worker.ExitCode -eq 0) { exit 0 }
    if ($attempt -eq $MaxRestarts) { exit $worker.ExitCode }
    Start-Sleep -Seconds $RestartDelaySeconds
}

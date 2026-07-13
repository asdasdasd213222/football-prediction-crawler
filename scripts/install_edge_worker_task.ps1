param(
    [Parameter(Mandatory = $true)]
    [string]$HealthFile,
    [int]$RestartCount = 3,
    [int]$RestartIntervalMinutes = 1
)

$ErrorActionPreference = 'Stop'
if ($RestartCount -lt 1) { throw 'RestartCount must be positive.' }
if ($RestartIntervalMinutes -lt 1) { throw 'RestartIntervalMinutes must be positive.' }

$repositoryRoot = (Get-Item -LiteralPath (Join-Path $PSScriptRoot '..')).FullName
$healthPath = [IO.Path]::GetFullPath($HealthFile)
if ($healthPath.StartsWith($repositoryRoot, [System.StringComparison]::OrdinalIgnoreCase)) {
    throw 'HealthFile must be outside the repository root.'
}

$supervisor = Join-Path $PSScriptRoot 'start_edge_worker_supervisor.ps1'
$argument = "-NoProfile -File `"$supervisor`" -HealthFile `"$healthPath`""
$action = New-ScheduledTaskAction -Execute 'powershell.exe' -Argument $argument
$trigger = New-ScheduledTaskTrigger -AtLogOn
$settings = New-ScheduledTaskSettingsSet -RestartCount $RestartCount -RestartInterval (New-TimeSpan -Minutes $RestartIntervalMinutes) -StartWhenAvailable
$description = 'Dedicated local Edge crawler worker. The runtime environment and health-file path must be configured outside the repository.'
Register-ScheduledTask -TaskName 'MultisiteCrawlerEdgeWorker' -Action $action -Trigger $trigger -Settings $settings -Description $description -Force

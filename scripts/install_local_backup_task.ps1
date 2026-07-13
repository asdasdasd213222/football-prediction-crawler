param(
    [Parameter(Mandatory = $true)]
    [string]$BackupDirectory,
    [string]$Time = '02:00'
)

$ErrorActionPreference = 'Stop'
$repositoryRoot = (Get-Item -LiteralPath (Join-Path $PSScriptRoot '..')).FullName
$backupRoot = [IO.Path]::GetFullPath($BackupDirectory)
if ($backupRoot.StartsWith($repositoryRoot, [System.StringComparison]::OrdinalIgnoreCase)) { throw 'BackupDirectory must be outside the repository root.' }
$scriptPath = Join-Path $PSScriptRoot 'backup_local_postgres.ps1'
$action = New-ScheduledTaskAction -Execute 'powershell.exe' -Argument "-NoProfile -File `"$scriptPath`" -BackupDirectory `"$backupRoot`""
$trigger = New-ScheduledTaskTrigger -Daily -At $Time
Register-ScheduledTask -TaskName 'MultisiteCrawlerLocalBackup' -Action $action -Trigger $trigger -Description 'Local-only crawler backup; runtime secret resolution required.' -Force

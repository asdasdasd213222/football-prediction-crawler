param(
    [Parameter(Mandatory = $true)]
    [string]$BackupPath
)

$ErrorActionPreference = 'Stop'
$repositoryRoot = (Get-Item -LiteralPath (Join-Path $PSScriptRoot '..')).FullName
$databaseUrl = $env:DATABASE_URL
if (-not $databaseUrl) { throw 'DATABASE_URL is required.' }
$uri = [Uri]$databaseUrl
if ($uri.Host -notin @('127.0.0.1', 'localhost')) { throw 'DATABASE_URL must target localhost or 127.0.0.1.' }
$resolvedBackup = [IO.Path]::GetFullPath($BackupPath)
if ($resolvedBackup.StartsWith($repositoryRoot, [System.StringComparison]::OrdinalIgnoreCase)) { throw 'BackupPath must be outside the repository root.' }
if (-not (Test-Path -LiteralPath $resolvedBackup -PathType Leaf)) { throw 'BackupPath does not exist.' }
& pg_restore --clean --if-exists --no-owner --dbname=$databaseUrl $resolvedBackup
if ($LASTEXITCODE -ne 0) { throw 'pg_restore failed.' }
Write-Output 'restore_completed=true'

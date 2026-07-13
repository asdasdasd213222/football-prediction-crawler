param(
    [Parameter(Mandatory = $true)]
    [string]$BackupDirectory
)

$ErrorActionPreference = 'Stop'
$repositoryRoot = (Get-Item -LiteralPath (Join-Path $PSScriptRoot '..')).FullName
$databaseUrl = $env:DATABASE_URL
if (-not $databaseUrl) { throw 'DATABASE_URL is required.' }
$uri = [Uri]$databaseUrl
if ($uri.Host -notin @('127.0.0.1', 'localhost')) { throw 'DATABASE_URL must target localhost or 127.0.0.1.' }
$backupRoot = [IO.Path]::GetFullPath($BackupDirectory)
if ($backupRoot.StartsWith($repositoryRoot, [System.StringComparison]::OrdinalIgnoreCase)) { throw 'BackupDirectory must be outside the repository root.' }
New-Item -ItemType Directory -Force -Path $backupRoot | Out-Null
$stamp = (Get-Date).ToUniversalTime().ToString('yyyyMMddTHHmmssZ')
$path = Join-Path $backupRoot "crawler_$stamp.dump"
& pg_dump --dbname=$databaseUrl --format=custom --file=$path
if ($LASTEXITCODE -ne 0) { throw 'pg_dump failed.' }
Write-Output "backup_path=$path"

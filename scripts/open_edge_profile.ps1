param(
    [switch]$Open,
    [switch]$RecordRefresh
)

if ($Open -eq $RecordRefresh) {
    throw 'Specify exactly one of -Open or -RecordRefresh.'
}

if ($Open) {
    foreach ($name in 'BROWSER_EDGE_EXECUTABLE_PATH', 'BROWSER_USER_DATA_DIR') {
        if (-not [Environment]::GetEnvironmentVariable($name)) {
            throw "$name is required."
        }
    }
    $repositoryRoot = (Get-Item -LiteralPath (Join-Path $PSScriptRoot '..')).FullName
    $profileDirectory = (Get-Item -LiteralPath $env:BROWSER_USER_DATA_DIR).FullName
    $repositoryPrefix = $repositoryRoot.TrimEnd('\\', '/') + '\\'
    if (
        $profileDirectory.Equals(
            $repositoryRoot,
            [System.StringComparison]::OrdinalIgnoreCase
        ) -or $profileDirectory.StartsWith(
            $repositoryPrefix,
            [System.StringComparison]::OrdinalIgnoreCase
        )
    ) {
        throw 'BROWSER_USER_DATA_DIR must be outside the repository root.'
    }
    Start-Process -FilePath $env:BROWSER_EDGE_EXECUTABLE_PATH -ArgumentList @(
        "--user-data-dir=$env:BROWSER_USER_DATA_DIR",
        'about:blank'
    )
    exit 0
}

if (-not $env:REDIS_URL) { throw 'REDIS_URL is required.' }
if (-not $env:BROWSER_PROFILE_REFERENCE) { throw 'BROWSER_PROFILE_REFERENCE is required.' }
& .\.venv\Scripts\python.exe -m multisite_crawler.browser_session_cli record-refresh
exit $LASTEXITCODE

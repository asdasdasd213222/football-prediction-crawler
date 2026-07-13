$ErrorActionPreference = 'Stop'
if (-not $env:REDIS_URL) { throw 'REDIS_URL is required.' }
$repositoryRoot = (Get-Item -LiteralPath (Join-Path $PSScriptRoot '..')).FullName
$python = Join-Path $repositoryRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $python)) {
    throw "Python virtual environment was not found at $python."
}

Push-Location $repositoryRoot
try {
    & $python -m multisite_crawler.browser_worker
    exit $LASTEXITCODE
}
finally {
    Pop-Location
}

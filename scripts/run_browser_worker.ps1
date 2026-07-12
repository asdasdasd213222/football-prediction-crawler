if (-not $env:REDIS_URL) { throw 'REDIS_URL is required.' }
& .\.venv\Scripts\python.exe -m multisite_crawler.browser_worker
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

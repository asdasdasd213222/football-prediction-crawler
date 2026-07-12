param([switch]$Run)

if (-not $Run) {
    Write-Output 'Pass -Run to start the local fixture and run the opt-in Edge probe.'
    exit 0
}

$portFile = [System.IO.Path]::GetTempFileName()
$fixtureScript = [System.IO.Path]::GetTempFileName()
$fixtureCode = @'
import pathlib
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer
class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        body = b"<html><head><title>local-edge-fixture</title></head><body>fixture</body></html>"
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)
    def log_message(self, format, *args):
        return
server = HTTPServer(("127.0.0.1", 0), Handler)
pathlib.Path(sys.argv[1]).write_text(str(server.server_port), encoding="utf-8")
server.serve_forever()
'@
[System.IO.File]::WriteAllText($fixtureScript, $fixtureCode, [System.Text.UTF8Encoding]::new($false))
$fixture = Start-Process -FilePath .\.venv\Scripts\python.exe -ArgumentList $fixtureScript, $portFile -PassThru -WindowStyle Hidden
try {
    $fixturePort = $null
    for ($attempt = 0; $attempt -lt 50; $attempt++) {
        if (Test-Path $portFile) {
            $publishedPort = Get-Content -Raw $portFile -ErrorAction SilentlyContinue
            if (-not [string]::IsNullOrWhiteSpace($publishedPort)) {
                $fixturePort = $publishedPort.Trim()
                break
            }
        }
        Start-Sleep -Milliseconds 100
    }
    if (-not $fixturePort) {
        throw 'The local fixture did not publish its port.'
    }
    $env:BROWSER_RUNTIME_PROBE_URL = "http://127.0.0.1:$fixturePort/"
    & .\.venv\Scripts\python.exe -c 'from multisite_crawler.tasks import run_browser_runtime_probe, _browser_runtime, _redis_lease_store; print(run_browser_runtime_probe(_browser_runtime(), _redis_lease_store()))'
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}
finally {
    if (-not $fixture.HasExited) { Stop-Process -Id $fixture.Id -Force }
    Remove-Item -LiteralPath $portFile -ErrorAction SilentlyContinue
    Remove-Item -LiteralPath $fixtureScript -ErrorAction SilentlyContinue
}

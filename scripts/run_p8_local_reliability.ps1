param(
    [ValidateRange(300, 1800)]
    [int]$DurationSeconds = 300,
    [switch]$KeepEnvironment
)

$ErrorActionPreference = 'Stop'
$repositoryRoot = (Get-Item -LiteralPath (Join-Path $PSScriptRoot '..')).FullName
$executionRoot = $null

function Invoke-Compose {
    param([Parameter(ValueFromRemainingArguments = $true)][string[]]$Arguments)

    & docker compose @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "docker compose $($Arguments -join ' ') failed."
    }
}

function Wait-Service {
    param(
        [Parameter(Mandatory = $true)][string]$Service,
        [Parameter(Mandatory = $true)][ValidateSet('running', 'healthy')][string]$ExpectedState,
        [int]$TimeoutSeconds = 90
    )

    $deadline = [DateTime]::UtcNow.AddSeconds($TimeoutSeconds)
    while ([DateTime]::UtcNow -lt $deadline) {
        $containerId = (& docker compose ps -q $Service | Out-String).Trim()
        if ($LASTEXITCODE -eq 0 -and $containerId) {
            $state = (& docker inspect --format '{{.State.Status}}' $containerId).Trim()
            $health = (& docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' $containerId).Trim()
            if ($ExpectedState -eq 'running' -and $state -eq 'running') { return }
            if ($ExpectedState -eq 'healthy' -and $health -eq 'healthy') { return }
        }
        Start-Sleep -Seconds 2
    }
    throw "$Service did not reach $ExpectedState within $TimeoutSeconds seconds."
}

function Write-Stage {
    param([Parameter(Mandatory = $true)][string]$Name)

    $beijing = [TimeZoneInfo]::FindSystemTimeZoneById('China Standard Time')
    $timestamp = [TimeZoneInfo]::ConvertTimeFromUtc([DateTime]::UtcNow, $beijing).ToString('o')
    Write-Output "p8_stage=$Name timestamp=$timestamp"
}

function New-AsciiBuildContext {
    $temporaryRoot = [IO.Path]::GetTempPath()
    $destination = Join-Path $temporaryRoot ("multisite-crawler-p8-" + [Guid]::NewGuid().ToString('N'))
    $skipDirectories = @('.git', '.venv', '.mypy_cache', '.ruff_cache', '.pytest_cache')
    $skipDirectories += Get-ChildItem -LiteralPath $repositoryRoot -Force -Directory |
        Where-Object Name -like '.pytest*' |
        Select-Object -ExpandProperty Name
    New-Item -ItemType Directory -Path $destination | Out-Null
    $copyArguments = @($repositoryRoot, $destination, '/E', '/XD') + $skipDirectories
    & robocopy @copyArguments | Out-Host
    if ($LASTEXITCODE -gt 7) {
        throw 'Unable to create the disposable ASCII build context.'
    }
    return $destination
}

function Remove-AsciiBuildContext {
    param([string]$Path)

    if (-not $Path) { return }
    $temporaryRoot = [IO.Path]::GetFullPath([IO.Path]::GetTempPath()).TrimEnd(
        [IO.Path]::DirectorySeparatorChar,
        [IO.Path]::AltDirectorySeparatorChar
    )
    $resolvedPath = [IO.Path]::GetFullPath($Path)
    $prefix = $temporaryRoot + [IO.Path]::DirectorySeparatorChar
    if (-not $resolvedPath.StartsWith($prefix, [System.StringComparison]::OrdinalIgnoreCase) -or
        -not [IO.Path]::GetFileName($resolvedPath).StartsWith('multisite-crawler-p8-', [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "Unsafe temporary build context: $resolvedPath"
    }
    Remove-Item -LiteralPath $resolvedPath -Recurse -Force
}

$executionRoot = New-AsciiBuildContext
Push-Location $executionRoot
try {
    $existing = (& docker compose ps --status running --services).Trim()
    if ($existing) {
        throw 'The local Compose stack is already running; stop it before the disposable P8 exercise.'
    }

    Write-Stage 'start'
    Invoke-Compose up --build --detach
    Wait-Service redis healthy
    Wait-Service postgres healthy
    Wait-Service worker-http running
    Wait-Service scheduler running

    $observationDeadline = [DateTime]::UtcNow.AddSeconds($DurationSeconds)
    while ([DateTime]::UtcNow -lt $observationDeadline) {
        Wait-Service redis healthy 5
        Wait-Service postgres healthy 5
        Wait-Service worker-http running 5
        Wait-Service scheduler running 5
        Start-Sleep -Seconds 5
    }

    Write-Stage 'redis_restart'
    Invoke-Compose restart redis
    Wait-Service redis healthy
    Wait-Service worker-http running
    Wait-Service scheduler running

    Write-Stage 'postgres_transient_unavailable'
    Invoke-Compose stop postgres
    Start-Sleep -Seconds 3
    Invoke-Compose start postgres
    Wait-Service postgres healthy
    Wait-Service worker-http running
    Wait-Service scheduler running

    Write-Stage 'worker_restart_recovery'
    Invoke-Compose restart worker-http
    Wait-Service worker-http running

    Write-Stage 'scheduler_restart'
    Invoke-Compose restart scheduler
    Wait-Service scheduler running

    Write-Output 'p8_local_reliability=passed'
}
finally {
    if (-not $KeepEnvironment) {
        Invoke-Compose down --volumes --remove-orphans
    }
    Pop-Location
    Remove-AsciiBuildContext $executionRoot
}

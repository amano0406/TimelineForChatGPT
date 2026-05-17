[CmdletBinding()]
param(
    [int]$Port = 0,
    [switch]$Foreground
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$utf8NoBom = [System.Text.UTF8Encoding]::new($false)
[Console]::InputEncoding = $utf8NoBom
[Console]::OutputEncoding = $utf8NoBom
$OutputEncoding = $utf8NoBom

$repoRoot = $PSScriptRoot
. (Join-Path $repoRoot "scripts\common.ps1")

$runtimeDir = Join-Path $repoRoot ".runtime"
$apiPidFile = Join-Path $runtimeDir "api.pid"
$apiProject = Join-Path $repoRoot "api\TimelineForChatGPT.HealthApi.csproj"

New-Item -ItemType Directory -Force -Path $runtimeDir | Out-Null
if ($Port -gt 0) {
    $env:TIMELINE_FOR_CHATGPT_API_PORT = [string]$Port
}

function Test-TfcgApiCommandLine {
    param([string]$CommandLine)

    if (-not $CommandLine) {
        return $false
    }

    $escapedRepoRoot = [regex]::Escape($repoRoot)
    return (
        ($CommandLine -match "TimelineForChatGPT\.HealthApi(\.csproj|\.dll|\.exe)?") -and
        ($CommandLine -match $escapedRepoRoot)
    )
}

function Get-TfcgApiProcess {
    try {
        $matches = @(
            Get-CimInstance Win32_Process -ErrorAction Stop |
                Where-Object { Test-TfcgApiCommandLine -CommandLine ([string]$_.CommandLine) }
        )
    }
    catch {
        return $null
    }

    if ($matches.Count -eq 0) {
        return $null
    }

    $projectHost = @($matches | Where-Object { [string]$_.CommandLine -match "TimelineForChatGPT\.HealthApi\.csproj" } | Select-Object -First 1)
    if ($projectHost.Count -gt 0) {
        return $projectHost[0]
    }

    return ($matches | Select-Object -First 1)
}

function Start-TfcgNativeApi {
    param(
        [int]$ApiPort,
        [switch]$RunInForeground
    )

    if (-not (Test-Path -LiteralPath $apiProject -PathType Leaf)) {
        throw "TimelineForChatGPT API project was not found: $apiProject"
    }

    if (Test-Path -LiteralPath $apiPidFile) {
        $existingPidText = (Get-Content -LiteralPath $apiPidFile -Raw).Trim()
        $existingPid = 0
        if ([int]::TryParse($existingPidText, [ref]$existingPid)) {
            $existing = Get-Process -Id $existingPid -ErrorAction SilentlyContinue
            if ($null -ne $existing) {
                $commandLine = ""
                try {
                    $cim = Get-CimInstance Win32_Process -Filter "ProcessId = $existingPid"
                    if ($null -ne $cim) {
                        $commandLine = [string]$cim.CommandLine
                    }
                }
                catch {
                    $commandLine = ""
                }
                if (Test-TfcgApiCommandLine -CommandLine $commandLine) {
                    Write-Host "TimelineForChatGPT API is already running. pid=$existingPid"
                    return
                }
            }
        }
        Remove-Item -LiteralPath $apiPidFile -Force
    }

    $running = Get-TfcgApiProcess
    if ($null -ne $running) {
        Set-Content -LiteralPath $apiPidFile -Value ([string]$running.ProcessId) -Encoding ASCII
        Write-Host "TimelineForChatGPT API is already running. pid=$($running.ProcessId)"
        return
    }

    $apiArgs = @(
        "run",
        "--project",
        $apiProject,
        "--no-launch-profile",
        "--",
        "--product-root",
        $repoRoot,
        "--port",
        [string]$ApiPort
    )

    if ($RunInForeground) {
        & dotnet @apiArgs
        exit $LASTEXITCODE
    }

    $process = Start-Process -FilePath "dotnet" -ArgumentList $apiArgs -WorkingDirectory $repoRoot -WindowStyle Hidden -PassThru
    Set-Content -LiteralPath $apiPidFile -Value ([string]$process.Id) -Encoding ASCII
    Write-Host "TimelineForChatGPT API started. pid=$($process.Id)"
}

Initialize-TimelineForChatGPTSettings
$runtime = Get-TimelineForChatGPTRuntimeSettings
$docker = Get-TimelineForChatGPTDockerCommand
Assert-TimelineForChatGPTDockerReady -Docker $docker
$composeArgs = Get-TimelineForChatGPTComposeArguments

Invoke-TimelineForChatGPTWithFileLock -LockName "docker-compose.lock" -ScriptBlock {
    Write-Host "Starting TimelineForChatGPT worker..."
    $startResult = Invoke-TimelineForChatGPTHiddenProcess `
        -FilePath $docker `
        -Arguments (@($composeArgs) + @("up", "-d", "--build", "--remove-orphans", "worker")) `
        -WriteOutput
    if ($startResult.ExitCode -ne 0) {
        throw "docker compose failed."
    }
}

Start-TfcgNativeApi -ApiPort ([int]$runtime.ApiPort) -RunInForeground:$Foreground

Write-Host ""
Write-Host "TimelineForChatGPT worker and API are running."
Write-Host "API: http://127.0.0.1:$($runtime.ApiPort)/health"
Write-Host ""
Write-Host "API examples:"
Write-Host "  curl.exe http://127.0.0.1:$($runtime.ApiPort)/health"
Write-Host "  Invoke-RestMethod -Method Post -Uri http://127.0.0.1:$($runtime.ApiPort)/settings/status -Body '{}'"
Write-Host "  Invoke-RestMethod -Method Post -Uri http://127.0.0.1:$($runtime.ApiPort)/items/list -Body '{}'"
Write-Host "  Invoke-RestMethod -Method Post -Uri http://127.0.0.1:$($runtime.ApiPort)/items/refresh -Body '{""file"":""C:\\path\\chatgpt-export.zip""}'"
Write-Host ""
Write-Host "Docker status:"
$statusResult = Invoke-TimelineForChatGPTHiddenProcess `
    -FilePath $docker `
    -Arguments (@($composeArgs) + @("ps")) `
    -WriteOutput
if ($statusResult.ExitCode -ne 0) {
    Write-Warning "TimelineForChatGPT worker started, but Docker status could not be displayed."
}

exit 0

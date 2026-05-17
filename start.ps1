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

New-Item -ItemType Directory -Force -Path $runtimeDir | Out-Null
if ($Port -gt 0) {
    $env:TIMELINE_FOR_CHATGPT_API_PORT = [string]$Port
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

Write-Host ""
Write-Host "TimelineForChatGPT worker API is running in the worker container."
Write-Host "API: http://127.0.0.1:$($runtime.ApiPort)/health"
Write-Host ""
Write-Host "API examples:"
Write-Host "  curl.exe http://127.0.0.1:$($runtime.ApiPort)/health"
Write-Host "  Invoke-RestMethod -Method Post -Uri http://127.0.0.1:$($runtime.ApiPort)/settings/status -Body '{}'"
Write-Host "  Invoke-RestMethod -Method Post -Uri http://127.0.0.1:$($runtime.ApiPort)/items/list -Body '{}'"
Write-Host "  Invoke-RestMethod -Method Post -Uri http://127.0.0.1:$($runtime.ApiPort)/items/refresh -Body '{""file"":""C:\\path\\chatgpt-export.zip""}'"
Write-Host ""

if ($Foreground) {
    Write-Host "Foreground mode follows worker logs. Press Ctrl+C to stop following logs."
    $logResult = Invoke-TimelineForChatGPTHiddenProcess `
        -FilePath $docker `
        -Arguments (@($composeArgs) + @("logs", "-f", "worker")) `
        -WriteOutput
    exit $logResult.ExitCode
}

Write-Host "Docker status:"
$statusResult = Invoke-TimelineForChatGPTHiddenProcess `
    -FilePath $docker `
    -Arguments (@($composeArgs) + @("ps")) `
    -WriteOutput
if ($statusResult.ExitCode -ne 0) {
    Write-Warning "TimelineForChatGPT worker started, but Docker status could not be displayed."
}

exit 0

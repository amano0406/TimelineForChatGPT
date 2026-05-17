[CmdletBinding()]
param()

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$utf8NoBom = [System.Text.UTF8Encoding]::new($false)
[Console]::InputEncoding = $utf8NoBom
[Console]::OutputEncoding = $utf8NoBom
$OutputEncoding = $utf8NoBom

$repoRoot = $PSScriptRoot
. (Join-Path $repoRoot "scripts\common.ps1")

$apiPidFile = Join-Path $repoRoot ".runtime\api.pid"

function Stop-TfcgNativeApi {
    if (-not (Test-Path -LiteralPath $apiPidFile)) {
        return
    }

    $pidText = (Get-Content -LiteralPath $apiPidFile -Raw).Trim()
    $pidValue = 0
    if ([int]::TryParse($pidText, [ref]$pidValue)) {
        $process = Get-Process -Id $pidValue -ErrorAction SilentlyContinue
        if ($null -ne $process) {
            Stop-Process -Id $pidValue -Force -ErrorAction SilentlyContinue
        }
    }

    Remove-Item -LiteralPath $apiPidFile -Force -ErrorAction SilentlyContinue
}

Stop-TfcgNativeApi

Initialize-TimelineForChatGPTSettings
$docker = Get-TimelineForChatGPTDockerCommand
Assert-TimelineForChatGPTDockerReady -Docker $docker
$composeArgs = Get-TimelineForChatGPTComposeArguments

$script:stopExitCode = 0
Invoke-TimelineForChatGPTWithFileLock -LockName "docker-compose.lock" -ScriptBlock {
    Write-Host "Stopping TimelineForChatGPT worker..."
    $stopResult = Invoke-TimelineForChatGPTHiddenProcess `
        -FilePath $docker `
        -Arguments (@($composeArgs) + @("stop", "worker")) `
        -WriteOutput
    $script:stopExitCode = $stopResult.ExitCode
}

exit $script:stopExitCode

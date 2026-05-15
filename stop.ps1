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

Initialize-TimelineForChatGPTSettings
$docker = Get-TimelineForChatGPTDockerCommand
Assert-TimelineForChatGPTDockerReady -Docker $docker
$composeArgs = Get-TimelineForChatGPTComposeArguments

$script:stopExitCode = 0
Invoke-TimelineForChatGPTWithFileLock -LockName "docker-compose.lock" -ScriptBlock {
    Write-Host "Stopping TimelineForChatGPT health API and worker..."
    $stopResult = Invoke-TimelineForChatGPTHiddenProcess `
        -FilePath $docker `
        -Arguments (@($composeArgs) + @("stop", "api", "worker")) `
        -WriteOutput
    $script:stopExitCode = $stopResult.ExitCode
}

exit $script:stopExitCode

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

Invoke-TimelineForChatGPTWithFileLock -LockName "docker-compose.lock" -ScriptBlock {
    Write-Host "Starting TimelineForChatGPT worker..."
    $startResult = Invoke-TimelineForChatGPTHiddenProcess `
        -FilePath $docker `
        -Arguments (@($composeArgs) + @("up", "-d", "--remove-orphans", "worker")) `
        -WriteOutput
    if ($startResult.ExitCode -ne 0) {
        throw "docker compose failed."
    }

    Write-Host ""
    Write-Host "TimelineForChatGPT worker is running."
    Write-Host "CLI commands execute inside this persistent Compose service container."
    Write-Host ""
    Write-Host "CLI examples:"
    Write-Host "  .\cli.bat settings status"
    Write-Host "  .\cli.bat items refresh --file C:\path\chatgpt-export.zip --json"
    Write-Host "  .\cli.bat items list --json"
    Write-Host "  .\cli.bat items download --to C:\path\handoff"
    Write-Host ""
    Write-Host "Docker status:"
    $statusResult = Invoke-TimelineForChatGPTHiddenProcess `
        -FilePath $docker `
        -Arguments (@($composeArgs) + @("ps")) `
        -WriteOutput
    if ($statusResult.ExitCode -ne 0) {
        Write-Warning "TimelineForChatGPT worker started, but Docker status could not be displayed."
    }
}

exit 0

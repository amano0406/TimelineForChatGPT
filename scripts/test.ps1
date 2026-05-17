[CmdletBinding()]
param(
    [Parameter()]
    [switch]$IncludeLocalApiSmoke
)

. "$PSScriptRoot\common.ps1"
Initialize-TimelineForChatGPTSettings
$docker = Get-TimelineForChatGPTDockerCommand
$composeArgs = Get-TimelineForChatGPTComposeArguments
$upArgs = @($composeArgs) + @("up", "-d", "--build", "worker")
& $docker @upArgs
if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}
$testArgs = @($composeArgs) + @("exec", "-T", "worker", "python", "-m", "unittest", "discover", "-s", "/app/worker/tests", "-v")
& $docker @testArgs
$testExitCode = $LASTEXITCODE
if ($testExitCode -ne 0) {
    exit $testExitCode
}

if ($IncludeLocalApiSmoke) {
    Test-TimelineForChatGPTApi | Out-Host
    Invoke-TimelineForChatGPTApi -Path "settings/status" -Body @{} | Out-Host
}

exit 0

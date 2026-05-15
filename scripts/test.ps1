[CmdletBinding()]
param(
    [Parameter()]
    [switch]$IncludeLocalCliDownload
)

. "$PSScriptRoot\common.ps1"
Initialize-TimelineForChatGPTSettings
dotnet build .\api\TimelineForChatGPT.HealthApi.csproj
if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}
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

if ($IncludeLocalCliDownload) {
    python tests/smoke/run_cli_ps1_download.py
    if ($LASTEXITCODE -ne 0) {
        exit $LASTEXITCODE
    }
}

exit 0

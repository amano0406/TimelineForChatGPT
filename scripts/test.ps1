[CmdletBinding()]
param(
    [Parameter()]
    [switch]$IncludeLocalCliDownload
)

. "$PSScriptRoot\common.ps1"
Initialize-TimelineForChatGPTSettings
& docker compose up -d --build worker
if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}
& docker compose exec -T worker python -m unittest discover -s /app/worker/tests -v
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

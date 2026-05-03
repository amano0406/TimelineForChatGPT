. "$PSScriptRoot\common.ps1"
Initialize-TimelineForChatGPTSettings
& docker compose up -d --build worker
if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}
& docker compose exec -T worker python -m unittest discover -s /app/worker/tests -v
Exit-TimelineForChatGPTNativeCommand

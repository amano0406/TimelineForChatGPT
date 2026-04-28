. "$PSScriptRoot\common.ps1"
Initialize-TimelineForChatGPTSettings
& docker compose up worker
Exit-TimelineForChatGPTNativeCommand

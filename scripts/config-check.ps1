. "$PSScriptRoot\common.ps1"
Initialize-TimelineForChatGPTSettings
& docker compose run --rm worker config-check @args
Exit-TimelineForChatGPTNativeCommand

. "$PSScriptRoot\common.ps1"
Initialize-TimelineForChatGPTSettings
& docker compose run --rm worker refresh @args
Exit-TimelineForChatGPTNativeCommand

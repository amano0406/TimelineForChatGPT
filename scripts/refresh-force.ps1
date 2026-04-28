. "$PSScriptRoot\common.ps1"
Initialize-TimelineForChatGPTSettings
& docker compose run --rm worker refresh --force @args
Exit-TimelineForChatGPTNativeCommand
